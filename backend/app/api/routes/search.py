from __future__ import annotations

import logging
import os
import re
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.authz import Principal, is_admin, require_permissions
from app.core.text_utils import strip_control_chars
from app.db.hybrid_search import hybrid_search_chunks_rrf
from app.db.session import get_db
from app.db.models import Document
from app.schemas.api_contract import SearchMode, SearchRequest

router = APIRouter()
logger = logging.getLogger(__name__)


# ----------------------------
# Request/Response models
# ----------------------------
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
    used_mode: str
    doc_filter_reason: Optional[str] = None

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
    # Reuse the chat route helpers so OPENAI_OFFLINE logic (and future stubs)
    # stay consistent across endpoints. Import locally to avoid circular imports.
    from app.api.routes.chat import embed_query as _chat_embed_query  # noqa

    emb = _chat_embed_query(q)
    if not isinstance(emb, list) or not emb:
        raise RuntimeError("Embedding response is empty")
    return emb


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


def _ensure_document_scope(
    db: Session, document_ids: list[str], principal: Principal
) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in document_ids or []:
        doc_id = (raw or "").strip()
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        cleaned.append(doc_id)
    if not cleaned:
        raise HTTPException(
            status_code=422, detail="document_ids must contain at least one id."
        )

    stmt = select(Document.id).where(Document.id.in_(cleaned))
    if not is_admin(principal):
        if not principal.sub:
            raise HTTPException(status_code=404, detail="document not found")
        stmt = stmt.where(Document.owner_sub == principal.sub)

    rows = [row[0] for row in db.execute(stmt)]
    missing = [doc_id for doc_id in cleaned if doc_id not in rows]
    if missing:
        raise HTTPException(status_code=404, detail="document not found")
    return cleaned


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
    if req.mode == SearchMode.selected_docs:
        if not doc_ids_list:
            raise HTTPException(
                status_code=422,
                detail="document_ids is required when mode=selected_docs",
            )
        doc_ids_list = _ensure_document_scope(db, doc_ids_list, p)

    use_doc_filter = bool(doc_ids_list)
    doc_filter_reason = f"mode={req.mode.value}"
    if req.mode == SearchMode.selected_docs and not doc_ids_list:
        doc_filter_reason = "document_ids empty"

    owner_sub_used, owner_sub_alt = _owner_sub_pair(getattr(p, "sub", "") or "")
    if not owner_sub_used:
        raise HTTPException(status_code=401, detail="Missing principal sub")

    # embedding
    try:
        qvec_list = _embed_query(q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding error: {e}")

    # trgm
    trgm_enabled = bool(
        req.trgm_enabled and (os.getenv("SEARCH_TRGM_ENABLED", "1") == "1")
    )
    used_trgm_limit = _auto_trgm_limit(q, req.trgm_limit)
    q_terms = _split_terms(q)
    trgm_like_patterns = [f"%{t}%" for t in q_terms]  # ILIKE ANY patterns

    debug_enabled = req.debug or (os.getenv("SEARCH_DEBUG") == "1")

    db_info = {"db_name": None, "db_host": None, "db_port": None}
    if debug_enabled:
        try:
            info = (
                db.execute(
                    text(
                        "select current_database() as db_name, inet_server_addr()::text as db_host, inet_server_port() as db_port"
                    )
                )
                .mappings()
                .one()
            )
            db_info = dict(info)
        except Exception:
            pass

    try:
        hits_raw, meta = hybrid_search_chunks_rrf(
            db,
            owner_sub=owner_sub_used,
            owner_sub_alt=owner_sub_alt,
            document_ids=doc_ids_list if use_doc_filter else None,
            query_text=q,
            query_embedding=qvec_list,
            top_k=req.limit,
            fts_k=req.k_fts,
            vec_k=req.k_vec,
            rrf_k=req.rrf_k,
            trgm_k=req.k_trgm if trgm_enabled else 0,
            trgm_limit=used_trgm_limit,
            trgm_like_patterns=trgm_like_patterns,
            use_fts=True,
            use_trgm=trgm_enabled,
            allow_all_without_owner=is_admin(p),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("hybrid search failed")
        raise HTTPException(status_code=500, detail=f"Search error: {exc}")

    hit_rows = [
        {
            "chunk_id": hit.chunk_id,
            "document_id": hit.document_id,
            "page": hit.page,
            "chunk_index": hit.chunk_index,
            "text": strip_control_chars(hit.text),
            "score": hit.score,
            "vec_distance": hit.vec_distance,
            "fts_rank": hit.rank_fts,
            "vec_rank": hit.rank_vec,
            "trgm_rank": hit.rank_trgm,
            "trgm_sim": hit.trgm_sim,
        }
        for hit in hits_raw
    ]

    fts_count = meta.fts_count
    vec_count = meta.vec_count
    trgm_count = meta.trgm_count
    vec_min = meta.vec_min_distance
    vec_max = meta.vec_max_distance
    vec_avg = meta.vec_avg_distance
    trgm_min = meta.trgm_min_sim
    trgm_max = meta.trgm_max_sim
    trgm_avg = meta.trgm_avg_sim

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
                used_mode=req.mode.value,
                doc_filter_reason=doc_filter_reason,
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
                used_k_trgm=req.k_trgm if trgm_enabled else 0,
                used_trgm_limit=used_trgm_limit,
            )
            if debug_enabled
            else None,
        )

    # Filter by score
    filtered = [r for r in hit_rows if float(r["score"]) >= used_min_score]

    # Optional vec distance cutoff
    if used_max_vec_distance is not None:
        m = float(used_max_vec_distance)
        filtered = [
            r
            for r in filtered
            if (r.get("vec_distance") is None) or (float(r.get("vec_distance")) <= m)
        ]

    if req.return_empty_on_low_confidence and not filtered:
        return SearchResponse(
            hits=[],
            debug=SearchDebug(
                principal_sub=getattr(p, "sub", "") or "",
                owner_sub_used=owner_sub_used,
                owner_sub_alt=owner_sub_alt,
                used_mode=req.mode.value,
                doc_filter_reason=doc_filter_reason,
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
                used_k_trgm=req.k_trgm if trgm_enabled else 0,
                used_trgm_limit=used_trgm_limit,
            )
            if debug_enabled
            else None,
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
            vec_distance=(
                float(r["vec_distance"]) if r.get("vec_distance") is not None else None
            ),
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
            used_mode=req.mode.value,
            doc_filter_reason=doc_filter_reason,
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
            used_k_trgm=req.k_trgm if trgm_enabled else 0,
            used_trgm_limit=used_trgm_limit,
        )
        if debug_enabled
        else None,
    )
