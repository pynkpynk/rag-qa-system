from __future__ import annotations

import logging
import os
import re
from enum import Enum
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.authz import Principal, require_permissions
from app.db.session import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


# ----------------------------
# Request/Response models
# ----------------------------
class SearchMode(str, Enum):
    selected_docs = "selected_docs"
    library = "library"


class SearchRequest(BaseModel):
    q: str = Field(..., min_length=1, description="Search query text")

    mode: SearchMode = Field(
        SearchMode.selected_docs,
        description="selected_docs requires document_ids; library searches all user's docs",
    )
    document_ids: Optional[List[str]] = Field(
        None,
        description="Filter to these doc IDs (required for selected_docs mode)",
    )

    limit: int = Field(20, ge=1, le=100, description="Final number of chunks to return")
    k_fts: int = Field(50, ge=1, le=500, description="Candidate count from FTS")
    k_vec: int = Field(50, ge=1, le=500, description="Candidate count from vector search")
    k_trgm: int = Field(50, ge=1, le=500, description="Candidate count from trigram search")
    rrf_k: int = Field(60, ge=1, le=500, description="RRF constant")

    min_score: float = Field(0.02, ge=0.0, description="Drop hits below this RRF score.")
    max_vec_distance: Optional[float] = Field(None, ge=0.0, description="Optional vec distance cutoff.")
    return_empty_on_low_confidence: bool = Field(True, description="If filtering removes all hits, return hits=[]")

    # NOTE: this is a *threshold* for pg_trgm similarity operator (%).
    # For CJK queries, code will auto-lower this value to avoid "always zero" behavior on long chunks.
    trgm_limit: float = Field(0.12, ge=0.0, le=1.0, description="Trigram similarity threshold (pg_trgm).")
    trgm_enabled: bool = Field(True, description="Enable trigram fallback (pg_trgm).")

    debug: bool = Field(False, description="Include debug stats in response.")

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, v):
        if isinstance(v, str) and v.strip() == "all_docs":
            return SearchMode.library
        return v


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    page: Optional[int] = None
    chunk_index: int
    text: str
    score: float
    vec_distance: Optional[float] = None
    fts_rank: Optional[int] = None
    vec_rank: Optional[int] = None
    trgm_rank: Optional[int] = None
    trgm_sim: Optional[float] = None


class SearchDebug(BaseModel):
    principal_sub: str
    owner_sub_used: str
    owner_sub_alt: Optional[str] = None

    db_name: Optional[str] = None
    db_host: Optional[str] = None
    db_port: Optional[int] = None

    fts_count: int
    vec_count: int
    trgm_count: int
    trgm_enabled: bool

    vec_min_distance: Optional[float] = None
    vec_max_distance: Optional[float] = None
    vec_avg_distance: Optional[float] = None

    trgm_min_sim: Optional[float] = None
    trgm_max_sim: Optional[float] = None
    trgm_avg_sim: Optional[float] = None

    used_min_score: float
    used_max_vec_distance: Optional[float] = None
    used_use_doc_filter: bool
    used_k_trgm: int
    used_trgm_limit: float


class SearchResponse(BaseModel):
    hits: List[SearchHit]
    debug: Optional[SearchDebug] = None


# ----------------------------
# Helpers
# ----------------------------
def _embed_query(q: str) -> List[float]:
    api_key = os.getenv("OPENAI_API_KEY") or ""
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small"

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(model=model, input=q)
    emb = resp.data[0].embedding
    if not isinstance(emb, list) or not emb:
        raise RuntimeError("Embedding response is empty")
    return emb


def _to_pgvector_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{float(x):.10f}" for x in vec) + "]"


def _get_default_max_vec_distance() -> Optional[float]:
    v = (os.getenv("SEARCH_DEFAULT_MAX_VEC_DISTANCE") or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        logger.warning("Invalid SEARCH_DEFAULT_MAX_VEC_DISTANCE=%r; ignoring", v)
        return None


def _owner_sub_pair(sub: str) -> Tuple[str, Optional[str]]:
    """
    Accept both:
      - auth0|xxxxx
      - xxxxx
    Because you already saw both patterns in your DB logs.
    """
    s = (sub or "").strip()
    if not s:
        return "", None
    if "|" not in s:
        return s, f"auth0|{s}"
    if s.startswith("auth0|"):
        return s, s.split("|", 1)[1]
    return s, None


_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")  # Hiragana/Katakana/CJK Unified


def _split_terms(q: str, max_terms: int = 8) -> List[str]:
    # split by whitespace; keep >=2 chars to reduce noise
    parts = [p.strip() for p in re.split(r"\s+", q) if p.strip()]
    parts = [p for p in parts if len(p) >= 2]
    # dedupe preserving order
    seen = set()
    out: List[str] = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= max_terms:
            break
    return out


def _auto_trgm_limit(q: str, requested: float) -> float:
    """
    pg_trgm similarity on long Japanese chunks can be ~0.003-0.01 even when substring exists.
    If query contains CJK, cap threshold down to SEARCH_TRGM_LIMIT_CJK (default 0.003).
    """
    lim = float(requested)
    if _CJK_RE.search(q):
        cap_raw = (os.getenv("SEARCH_TRGM_LIMIT_CJK") or "0.003").strip()
        try:
            cap = float(cap_raw)
        except ValueError:
            cap = 0.003
        lim = min(lim, cap)
    return max(0.0, min(1.0, lim))


# ----------------------------
# Hybrid SQL (FTS + Vec + Trgm + RRF)
# ----------------------------
_HYBRID_SQL = """
WITH
params AS (
  SELECT
    websearch_to_tsquery('simple', :q) AS tsq,
    CAST(:qvec AS vector) AS qvec,
    CAST(:rrf_k AS int) AS rrf_k,
    CAST(:trgm_enabled AS boolean) AS trgm_enabled,
    -- IMPORTANT: set pg_trgm threshold locally for this statement
    set_config('pg_trgm.similarity_threshold', CAST(:trgm_limit AS text), true) AS _trgm_limit_set
),
fts AS (
  SELECT
    c.id AS chunk_id,
    row_number() OVER (ORDER BY ts_rank_cd(c.fts, p.tsq) DESC) AS rnk
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE
    (
      d.owner_sub = :owner_sub
      OR (
        CAST(:owner_sub_alt AS text) IS NOT NULL
        AND d.owner_sub = CAST(:owner_sub_alt AS text)
      )
    )
    AND (
      :use_doc_filter = false
      OR CAST(c.document_id AS text) = ANY(CAST(:doc_ids AS text[]))
    )
    AND c.fts @@ p.tsq
  ORDER BY ts_rank_cd(c.fts, p.tsq) DESC
  LIMIT :k_fts
),
vec AS (
  SELECT
    c.id AS chunk_id,
    row_number() OVER (ORDER BY (c.embedding <=> p.qvec) ASC) AS rnk,
    (c.embedding <=> p.qvec) AS dist
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE
    (
      d.owner_sub = :owner_sub
      OR (
        CAST(:owner_sub_alt AS text) IS NOT NULL
        AND d.owner_sub = CAST(:owner_sub_alt AS text)
      )
    )
    AND (
      :use_doc_filter = false
      OR CAST(c.document_id AS text) = ANY(CAST(:doc_ids AS text[]))
    )
    AND c.embedding IS NOT NULL
  ORDER BY (c.embedding <=> p.qvec) ASC
  LIMIT :k_vec
),
trgm AS (
  SELECT
    c.id AS chunk_id,
    row_number() OVER (ORDER BY similarity(c.text, :q) DESC) AS rnk,
    similarity(c.text, :q) AS sim
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE
    p.trgm_enabled = true
    AND (
      d.owner_sub = :owner_sub
      OR (
        CAST(:owner_sub_alt AS text) IS NOT NULL
        AND d.owner_sub = CAST(:owner_sub_alt AS text)
      )
    )
    AND (
      :use_doc_filter = false
      OR CAST(c.document_id AS text) = ANY(CAST(:doc_ids AS text[]))
    )
    -- Reduce junk: require at least one term literal-hit (pg_trgm GIN can accelerate ILIKE)
    AND (
      cardinality(CAST(:trgm_like_patterns AS text[])) = 0
      OR c.text ILIKE ANY(CAST(:trgm_like_patterns AS text[]))
    )
    -- Now apply similarity operator (%) with locally-set threshold
    AND c.text % :q
  ORDER BY similarity(c.text, :q) DESC
  LIMIT :k_trgm
),
rrf AS (
  SELECT
    chunk_id,
    SUM(1.0 / ((SELECT rrf_k FROM params) + rnk)) AS score
  FROM (
    SELECT chunk_id, rnk FROM fts
    UNION ALL
    SELECT chunk_id, rnk FROM vec
    UNION ALL
    SELECT chunk_id, rnk FROM trgm
  ) s
  GROUP BY chunk_id
),
picked AS (
  SELECT
    c.id AS chunk_id,
    c.document_id,
    c.page,
    c.chunk_index,
    c.text,
    r.score,
    vf.dist AS vec_distance,
    ff.rnk AS fts_rank,
    vf.rnk AS vec_rank,
    tf.rnk AS trgm_rank,
    tf.sim AS trgm_sim
  FROM rrf r
  JOIN chunks c ON c.id = r.chunk_id
  LEFT JOIN vec vf ON vf.chunk_id = c.id
  LEFT JOIN fts ff ON ff.chunk_id = c.id
  LEFT JOIN trgm tf ON tf.chunk_id = c.id
  ORDER BY r.score DESC
  LIMIT :limit
),
meta AS (
  SELECT
    (SELECT count(*) FROM fts) AS fts_count,
    (SELECT count(*) FROM vec) AS vec_count,
    (SELECT count(*) FROM trgm) AS trgm_count,
    (SELECT min(dist) FROM vec) AS vec_min_distance,
    (SELECT max(dist) FROM vec) AS vec_max_distance,
    (SELECT avg(dist) FROM vec) AS vec_avg_distance,
    (SELECT min(sim) FROM trgm) AS trgm_min_sim,
    (SELECT max(sim) FROM trgm) AS trgm_max_sim,
    (SELECT avg(sim) FROM trgm) AS trgm_avg_sim
)
SELECT
  p.chunk_id, p.document_id, p.page, p.chunk_index, p.text, p.score,
  p.vec_distance, p.fts_rank, p.vec_rank, p.trgm_rank, p.trgm_sim,
  m.fts_count, m.vec_count, m.trgm_count,
  m.vec_min_distance, m.vec_max_distance, m.vec_avg_distance,
  m.trgm_min_sim, m.trgm_max_sim, m.trgm_avg_sim
FROM meta m
LEFT JOIN picked p ON true;
"""


def _extract_meta(rows: list[dict[str, Any]]) -> tuple[int, int, int, Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
    r0 = rows[0] if rows else {}
    fts_count = int(r0.get("fts_count") or 0)
    vec_count = int(r0.get("vec_count") or 0)
    trgm_count = int(r0.get("trgm_count") or 0)

    vmin = r0.get("vec_min_distance")
    vmax = r0.get("vec_max_distance")
    vavg = r0.get("vec_avg_distance")

    tmin = r0.get("trgm_min_sim")
    tmax = r0.get("trgm_max_sim")
    tavg = r0.get("trgm_avg_sim")

    vec_min = float(vmin) if vmin is not None else None
    vec_max = float(vmax) if vmax is not None else None
    vec_avg = float(vavg) if vavg is not None else None

    trgm_min = float(tmin) if tmin is not None else None
    trgm_max = float(tmax) if tmax is not None else None
    trgm_avg = float(tavg) if tavg is not None else None

    return fts_count, vec_count, trgm_count, vec_min, vec_max, vec_avg, trgm_min, trgm_max, trgm_avg


@router.post("/search", response_model=SearchResponse)
def search(
    req: SearchRequest,
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("read:docs")),
) -> SearchResponse:
    q = (req.q or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="q must not be empty")

    doc_ids_list = req.document_ids or []
    if req.mode == SearchMode.selected_docs and not doc_ids_list:
        raise HTTPException(status_code=422, detail="document_ids is required when mode=selected_docs")

    use_doc_filter = bool(doc_ids_list)

    owner_sub_used, owner_sub_alt = _owner_sub_pair(getattr(p, "sub", "") or "")
    if not owner_sub_used:
        raise HTTPException(status_code=401, detail="Missing principal sub")

    # embedding
    try:
        qvec_list = _embed_query(q)
        qvec = _to_pgvector_literal(qvec_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding error: {e}")

    # trgm
    trgm_enabled = bool(req.trgm_enabled and (os.getenv("SEARCH_TRGM_ENABLED", "1") == "1"))
    used_trgm_limit = _auto_trgm_limit(q, req.trgm_limit)
    q_terms = _split_terms(q)
    trgm_like_patterns = [f"%{t}%" for t in q_terms]  # ILIKE ANY patterns

    params: dict[str, Any] = {
        "q": q,
        "qvec": qvec,
        "rrf_k": req.rrf_k,
        "owner_sub": owner_sub_used,
        "owner_sub_alt": owner_sub_alt,
        "use_doc_filter": use_doc_filter,
        "doc_ids": doc_ids_list,  # always list
        "k_fts": req.k_fts,
        "k_vec": req.k_vec,
        "k_trgm": req.k_trgm,
        "limit": req.limit,
        "trgm_enabled": trgm_enabled,
        "trgm_limit": used_trgm_limit,
        "trgm_like_patterns": trgm_like_patterns,
    }

    debug_enabled = req.debug or (os.getenv("SEARCH_DEBUG") == "1")

    db_info = {"db_name": None, "db_host": None, "db_port": None}
    if debug_enabled:
        try:
            info = db.execute(
                text("select current_database() as db_name, inet_server_addr()::text as db_host, inet_server_port() as db_port")
            ).mappings().one()
            db_info = dict(info)
        except Exception:
            pass

    try:
        rows = db.execute(text(_HYBRID_SQL), params).mappings().all()
        rows_list = [dict(r) for r in rows]
    except Exception as e:
        logger.exception("search sql failed")
        raise HTTPException(status_code=500, detail=f"Search SQL error: {type(e).__name__}: {e}")

    # meta is always present as 1 row (even if no hits)
    (
        fts_count,
        vec_count,
        trgm_count,
        vec_min,
        vec_max,
        vec_avg,
        trgm_min,
        trgm_max,
        trgm_avg,
    ) = _extract_meta(rows_list)

    hit_rows = [r for r in rows_list if r.get("chunk_id") is not None]

    present_sources = int(fts_count > 0) + int(vec_count > 0) + int(trgm_count > 0)

    used_min_score = float(req.min_score)
    if present_sources <= 1:
        # single-source only: don't nuke results by RRF threshold
        used_min_score = 0.0

    used_max_vec_distance = req.max_vec_distance
    if used_max_vec_distance is None:
        used_max_vec_distance = _get_default_max_vec_distance()

    if not hit_rows:
        return SearchResponse(
            hits=[],
            debug=SearchDebug(
                principal_sub=getattr(p, "sub", "") or "",
                owner_sub_used=owner_sub_used,
                owner_sub_alt=owner_sub_alt,
                db_name=db_info.get("db_name"),
                db_host=db_info.get("db_host"),
                db_port=db_info.get("db_port"),
                fts_count=fts_count,
                vec_count=vec_count,
                trgm_count=trgm_count,
                trgm_enabled=trgm_enabled,
                vec_min_distance=vec_min,
                vec_max_distance=vec_max,
                vec_avg_distance=vec_avg,
                trgm_min_sim=trgm_min,
                trgm_max_sim=trgm_max,
                trgm_avg_sim=trgm_avg,
                used_min_score=used_min_score,
                used_max_vec_distance=used_max_vec_distance,
                used_use_doc_filter=use_doc_filter,
                used_k_trgm=req.k_trgm,
                used_trgm_limit=used_trgm_limit,
            ) if debug_enabled else None,
        )

    # Filter by score
    filtered = [r for r in hit_rows if float(r["score"]) >= used_min_score]

    # Optional vec distance cutoff
    if used_max_vec_distance is not None:
        m = float(used_max_vec_distance)
        filtered = [r for r in filtered if (r.get("vec_distance") is None) or (float(r.get("vec_distance")) <= m)]

    if req.return_empty_on_low_confidence and not filtered:
        return SearchResponse(
            hits=[],
            debug=SearchDebug(
                principal_sub=getattr(p, "sub", "") or "",
                owner_sub_used=owner_sub_used,
                owner_sub_alt=owner_sub_alt,
                db_name=db_info.get("db_name"),
                db_host=db_info.get("db_host"),
                db_port=db_info.get("db_port"),
                fts_count=fts_count,
                vec_count=vec_count,
                trgm_count=trgm_count,
                trgm_enabled=trgm_enabled,
                vec_min_distance=vec_min,
                vec_max_distance=vec_max,
                vec_avg_distance=vec_avg,
                trgm_min_sim=trgm_min,
                trgm_max_sim=trgm_max,
                trgm_avg_sim=trgm_avg,
                used_min_score=used_min_score,
                used_max_vec_distance=used_max_vec_distance,
                used_use_doc_filter=use_doc_filter,
                used_k_trgm=req.k_trgm,
                used_trgm_limit=used_trgm_limit,
            ) if debug_enabled else None,
        )

    out = filtered if filtered else hit_rows

    hits = [
        SearchHit(
            chunk_id=str(r["chunk_id"]),
            document_id=str(r["document_id"]),
            page=r.get("page"),
            chunk_index=int(r["chunk_index"]),
            text=str(r["text"]),
            score=float(r["score"]),
            vec_distance=(float(r["vec_distance"]) if r.get("vec_distance") is not None else None),
            fts_rank=(int(r["fts_rank"]) if r.get("fts_rank") is not None else None),
            vec_rank=(int(r["vec_rank"]) if r.get("vec_rank") is not None else None),
            trgm_rank=(int(r["trgm_rank"]) if r.get("trgm_rank") is not None else None),
            trgm_sim=(float(r["trgm_sim"]) if r.get("trgm_sim") is not None else None),
        )
        for r in out
    ]

    return SearchResponse(
        hits=hits,
        debug=SearchDebug(
            principal_sub=getattr(p, "sub", "") or "",
            owner_sub_used=owner_sub_used,
            owner_sub_alt=owner_sub_alt,
            db_name=db_info.get("db_name"),
            db_host=db_info.get("db_host"),
            db_port=db_info.get("db_port"),
            fts_count=fts_count,
            vec_count=vec_count,
            trgm_count=trgm_count,
            trgm_enabled=trgm_enabled,
            vec_min_distance=vec_min,
            vec_max_distance=vec_max,
            vec_avg_distance=vec_avg,
            trgm_min_sim=trgm_min,
            trgm_max_sim=trgm_max,
            trgm_avg_sim=trgm_avg,
            used_min_score=used_min_score,
            used_max_vec_distance=used_max_vec_distance,
            used_use_doc_filter=use_doc_filter,
            used_k_trgm=req.k_trgm,
            used_trgm_limit=used_trgm_limit,
        ) if debug_enabled else None,
    )
