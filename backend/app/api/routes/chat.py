from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.core.authz import Principal, is_admin, require_permissions
from app.core.run_access import ensure_run_access
from app.db.models import Run
from app.db.session import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================
# Request model
# ============================================================

class AskPayload(BaseModel):
    question: str = Field(..., min_length=1)
    k: int = Field(6, ge=1, le=50)
    run_id: str | None = None


# ============================================================
# Settings (tune here)
# ============================================================

EMBED_MODEL = "text-embedding-3-small"
DEFAULT_CHAT_MODEL = "gpt-5-mini"

CONTRACT_RETRIES = 2
UNSUPPORTED_PARAM_RETRIES = 2

ALLOWED_GEN_KEYS: set[str] = {
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "seed",
}

KNOWN_UNSUPPORTED_PARAMS: dict[str, set[str]] = {
    "gpt-5-mini": {"temperature"},
}

# "要約/要点" 系はベクトル検索より「先頭から取る」方が安定することが多い
SUMMARY_Q_RE = re.compile(r"(要約|要点|まとめ|概要|サマリ|summary|summarize)", re.I)

# ユーザーが「[S? p.?]形式」と書いても、LLMには見せない（serverで付与するため）
_CITATION_FORMAT_HINT_RE = re.compile(r"\[S\?\s*p\.\?\]")
_FORMAT_SENTENCE_RE = re.compile(r"形式は[「\"']?\[S\?\s*p\.\?\][」\"']?とする。?")

# ============================================================
# Optional: Hybrid retrieval knobs (Postgres FTS + Vector + RRF)
# ============================================================

ENABLE_HYBRID = os.getenv("ENABLE_HYBRID", "0") == "1"
HYBRID_VEC_K = int(os.getenv("HYBRID_VEC_K", "30"))
HYBRID_FTS_K = int(os.getenv("HYBRID_FTS_K", "30"))
RRF_K = int(os.getenv("RRF_K", "60"))

# Debug
ENABLE_RETRIEVAL_DEBUG = os.getenv("ENABLE_RETRIEVAL_DEBUG", "1") == "1"

# FTS config/mode
# NOTE: fts column was created with to_tsvector('simple', ...) so default is "simple"
_FTS_CONFIG_RAW = os.getenv("FTS_CONFIG", "simple")
FTS_CONFIG = _FTS_CONFIG_RAW if re.fullmatch(r"[A-Za-z_]+", _FTS_CONFIG_RAW or "") else "simple"

# plainto (strict-ish) / websearch (forgiving)
FTS_QUERY_MODE = (os.getenv("FTS_QUERY_MODE", "plainto") or "plainto").strip().lower()
if FTS_QUERY_MODE not in {"plainto", "websearch"}:
    FTS_QUERY_MODE = "plainto"

TSQUERY_FN = "websearch_to_tsquery" if FTS_QUERY_MODE == "websearch" else "plainto_tsquery"
TSQUERY_EXPR = f"{TSQUERY_FN}('{FTS_CONFIG}', :q)"


# ============================================================
# SQL (Retrieval)
# ============================================================

SQL_TOPK_ALL_DOCS_ADMIN = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <=> (:qvec)::vector
LIMIT :k
"""

SQL_TOPK_ALL_DOCS_USER = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE d.owner_sub = :owner_sub
ORDER BY c.embedding <=> (:qvec)::vector
LIMIT :k
"""

SQL_TOPK_BY_RUN_ADMIN = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
JOIN run_documents rd ON rd.document_id = c.document_id
WHERE rd.run_id = :run_id
ORDER BY c.embedding <=> (:qvec)::vector
LIMIT :k
"""

SQL_TOPK_BY_RUN_USER = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
JOIN run_documents rd ON rd.document_id = c.document_id
WHERE rd.run_id = :run_id
  AND d.owner_sub = :owner_sub
ORDER BY c.embedding <=> (:qvec)::vector
LIMIT :k
"""

# 要約系：文書の「先頭から」取る（ページ→chunk順）
SQL_FIRSTK_BY_RUN_ADMIN = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
JOIN run_documents rd ON rd.document_id = c.document_id
WHERE rd.run_id = :run_id
ORDER BY c.document_id, c.page, c.chunk_index
LIMIT :k
"""

SQL_FIRSTK_BY_RUN_USER = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
JOIN run_documents rd ON rd.document_id = c.document_id
WHERE rd.run_id = :run_id
  AND d.owner_sub = :owner_sub
ORDER BY c.document_id, c.page, c.chunk_index
LIMIT :k
"""

# ★追加：run_idなしでも要約系FIRST-K（あなたの仕様説明と一致させる）
SQL_FIRSTK_ALL_DOCS_ADMIN = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
ORDER BY c.document_id, c.page, c.chunk_index
LIMIT :k
"""

SQL_FIRSTK_ALL_DOCS_USER = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE d.owner_sub = :owner_sub
ORDER BY c.document_id, c.page, c.chunk_index
LIMIT :k
"""

# Optional: FTS queries (requires chunks.fts tsvector column)
# NOTE: use TSQUERY_EXPR built from env (plainto/websearch + config)
SQL_FTS_BY_RUN_ADMIN = f"""
WITH q AS (SELECT {TSQUERY_EXPR} AS query)
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text,
       ts_rank_cd(c.fts, q.query) AS rank
FROM chunks c
JOIN documents d ON d.id = c.document_id
JOIN run_documents rd ON rd.document_id = c.document_id
CROSS JOIN q
WHERE rd.run_id = :run_id
  AND c.fts @@ q.query
ORDER BY rank DESC
LIMIT :k
"""

SQL_FTS_BY_RUN_USER = f"""
WITH q AS (SELECT {TSQUERY_EXPR} AS query)
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text,
       ts_rank_cd(c.fts, q.query) AS rank
FROM chunks c
JOIN documents d ON d.id = c.document_id
JOIN run_documents rd ON rd.document_id = c.document_id
CROSS JOIN q
WHERE rd.run_id = :run_id
  AND d.owner_sub = :owner_sub
  AND c.fts @@ q.query
ORDER BY rank DESC
LIMIT :k
"""

SQL_FTS_ALL_DOCS_ADMIN = f"""
WITH q AS (SELECT {TSQUERY_EXPR} AS query)
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text,
       ts_rank_cd(c.fts, q.query) AS rank
FROM chunks c
JOIN documents d ON d.id = c.document_id
CROSS JOIN q
WHERE c.fts @@ q.query
ORDER BY rank DESC
LIMIT :k
"""

SQL_FTS_ALL_DOCS_USER = f"""
WITH q AS (SELECT {TSQUERY_EXPR} AS query)
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text,
       ts_rank_cd(c.fts, q.query) AS rank
FROM chunks c
JOIN documents d ON d.id = c.document_id
CROSS JOIN q
WHERE d.owner_sub = :owner_sub
  AND c.fts @@ q.query
ORDER BY rank DESC
LIMIT :k
"""

SQL_RUN_DOC_COUNT_ADMIN = """
SELECT COUNT(*) AS cnt
FROM run_documents
WHERE run_id = :run_id
"""

SQL_RUN_DOC_COUNT_USER = """
SELECT COUNT(*) AS cnt
FROM run_documents rd
JOIN documents d ON d.id = rd.document_id
WHERE rd.run_id = :run_id
  AND d.owner_sub = :owner_sub
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_summary_question(q: str) -> bool:
    return bool(SUMMARY_Q_RE.search(q or ""))


def sanitize_question_for_llm(question: str) -> str:
    q = (question or "").strip()
    q = _FORMAT_SENTENCE_RE.sub("", q)
    q = _CITATION_FORMAT_HINT_RE.sub("", q)
    q = re.sub(r"\s{2,}", " ", q).strip()
    return q


def _preview(rows: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows[:n], start=1):
        txt = (r.get("text") or "")
        out.append(
            {
                "rank": i,
                "chunk_id": str(r.get("id")),
                "doc_id": str(r.get("document_id")),
                "filename": r.get("filename"),
                "page": r.get("page"),
                "chunk_index": r.get("chunk_index"),
                "preview": txt[:120],
            }
        )
    return out


def _rrf_merge(
    vec_rows: list[dict[str, Any]],
    fts_rows: list[dict[str, Any]],
    k: int,
) -> list[dict[str, Any]]:
    """
    Reciprocal Rank Fusion (RRF) merge.
    score(d) = sum( 1 / (RRF_K + rank_i(d)) )
    Adds debug fields:
      - _rrf_vec_rank, _rrf_fts_rank, _rrf_score
    """
    score: dict[str, float] = {}
    row_by_id: dict[str, dict[str, Any]] = {}
    vec_rank_by_id: dict[str, int] = {}
    fts_rank_by_id: dict[str, int] = {}

    for rank, r in enumerate(vec_rows, start=1):
        cid = str(r["id"])
        row_by_id.setdefault(cid, dict(r))
        vec_rank_by_id[cid] = rank
        score[cid] = score.get(cid, 0.0) + (1.0 / (RRF_K + rank))

    for rank, r in enumerate(fts_rows, start=1):
        cid = str(r["id"])
        row_by_id.setdefault(cid, dict(r))
        fts_rank_by_id[cid] = rank
        score[cid] = score.get(cid, 0.0) + (1.0 / (RRF_K + rank))

    merged_ids = sorted(score.keys(), key=lambda cid: score[cid], reverse=True)
    merged: list[dict[str, Any]] = []
    for cid in merged_ids[:k]:
        rr = row_by_id[cid]
        rr["_rrf_vec_rank"] = vec_rank_by_id.get(cid)
        rr["_rrf_fts_rank"] = fts_rank_by_id.get(cid)
        rr["_rrf_score"] = score.get(cid, 0.0)
        merged.append(rr)
    return merged


def fetch_chunks(
    db: Session,
    qvec_lit: str,
    q_text: str,
    k: int,
    run_id: str | None,
    p: Principal,
    question: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """
    Fetch chunks.
    - If run_id is provided: restrict to documents attached to the run (and owned by user if non-admin)
    - If run_id is not provided: restrict to user's documents if non-admin
    - For summary-like questions: prefer FIRST-K chunks by page order (run_idあり/なし両方)
    - Optional: Hybrid (FTS + Vector) with RRF, controlled by ENABLE_HYBRID
    """
    q_text = (q_text or "").strip()

    debug: dict[str, Any] | None = None
    if ENABLE_RETRIEVAL_DEBUG:
        debug = {
            "enable_hybrid": ENABLE_HYBRID,
            "fts_query_mode": FTS_QUERY_MODE,
            "fts_config": FTS_CONFIG,
            "hybrid_vec_k": HYBRID_VEC_K,
            "hybrid_fts_k": HYBRID_FTS_K,
            "rrf_k": RRF_K,
            "requested_k": k,
            "scope": {"run_id": run_id, "is_admin": is_admin(p), "owner_sub": None if is_admin(p) else p.sub},
            "strategy": None,
        }

    # --------------------
    # run_id scope
    # --------------------
    if run_id:
        if is_admin(p):
            cnt_row = db.execute(sql_text(SQL_RUN_DOC_COUNT_ADMIN), {"run_id": run_id}).mappings().first()
            if not cnt_row or int(cnt_row["cnt"]) == 0:
                raise HTTPException(status_code=400, detail="This run_id has no attached documents. Attach docs first.")

            if _is_summary_question(question):
                k_eff = min(max(k, 20), 50)
                rows = [dict(r) for r in db.execute(sql_text(SQL_FIRSTK_BY_RUN_ADMIN), {"run_id": run_id, "k": k_eff}).mappings().all()]
                if debug is not None:
                    debug["strategy"] = "firstk_by_run_admin"
                    debug["count"] = len(rows)
                    debug["top5"] = _preview(rows)
                return rows, debug

            if ENABLE_HYBRID and q_text:
                vec = [dict(r) for r in db.execute(sql_text(SQL_TOPK_BY_RUN_ADMIN), {"qvec": qvec_lit, "k": HYBRID_VEC_K, "run_id": run_id}).mappings().all()]
                fts = [dict(r) for r in db.execute(sql_text(SQL_FTS_BY_RUN_ADMIN), {"q": q_text, "k": HYBRID_FTS_K, "run_id": run_id}).mappings().all()]
                merged = _rrf_merge(vec, fts, k)

                if debug is not None:
                    debug["strategy"] = "hybrid_rrf_by_run_admin"
                    debug["vec_count"] = len(vec)
                    debug["fts_count"] = len(fts)
                    debug["merged_count"] = len(merged)
                    debug["vec_top5"] = _preview(vec)
                    debug["fts_top5"] = _preview(fts)
                    debug["merged_top5"] = _preview(merged)

                return (merged if merged else vec[:k]), debug

            rows = [dict(r) for r in db.execute(sql_text(SQL_TOPK_BY_RUN_ADMIN), {"qvec": qvec_lit, "k": k, "run_id": run_id}).mappings().all()]
            if debug is not None:
                debug["strategy"] = "vector_by_run_admin"
                debug["count"] = len(rows)
                debug["top5"] = _preview(rows)
            return rows, debug

        # non-admin
        cnt_row = db.execute(sql_text(SQL_RUN_DOC_COUNT_USER), {"run_id": run_id, "owner_sub": p.sub}).mappings().first()
        if not cnt_row or int(cnt_row["cnt"]) == 0:
            raise HTTPException(status_code=400, detail="This run_id has no attached documents. Attach docs first.")

        if _is_summary_question(question):
            k_eff = min(max(k, 20), 50)
            rows = [dict(r) for r in db.execute(sql_text(SQL_FIRSTK_BY_RUN_USER), {"run_id": run_id, "k": k_eff, "owner_sub": p.sub}).mappings().all()]
            if debug is not None:
                debug["strategy"] = "firstk_by_run_user"
                debug["count"] = len(rows)
                debug["top5"] = _preview(rows)
            return rows, debug

        if ENABLE_HYBRID and q_text:
            vec = [dict(r) for r in db.execute(sql_text(SQL_TOPK_BY_RUN_USER), {"qvec": qvec_lit, "k": HYBRID_VEC_K, "run_id": run_id, "owner_sub": p.sub}).mappings().all()]
            fts = [dict(r) for r in db.execute(sql_text(SQL_FTS_BY_RUN_USER), {"q": q_text, "k": HYBRID_FTS_K, "run_id": run_id, "owner_sub": p.sub}).mappings().all()]
            merged = _rrf_merge(vec, fts, k)

            if debug is not None:
                debug["strategy"] = "hybrid_rrf_by_run_user"
                debug["vec_count"] = len(vec)
                debug["fts_count"] = len(fts)
                debug["merged_count"] = len(merged)
                debug["vec_top5"] = _preview(vec)
                debug["fts_top5"] = _preview(fts)
                debug["merged_top5"] = _preview(merged)

            return (merged if merged else vec[:k]), debug

        rows = [dict(r) for r in db.execute(sql_text(SQL_TOPK_BY_RUN_USER), {"qvec": qvec_lit, "k": k, "run_id": run_id, "owner_sub": p.sub}).mappings().all()]
        if debug is not None:
            debug["strategy"] = "vector_by_run_user"
            debug["count"] = len(rows)
            debug["top5"] = _preview(rows)
        return rows, debug

    # --------------------
    # no run_id scope
    # --------------------
    if _is_summary_question(question):
        k_eff = min(max(k, 20), 50)
        if is_admin(p):
            rows = [dict(r) for r in db.execute(sql_text(SQL_FIRSTK_ALL_DOCS_ADMIN), {"k": k_eff}).mappings().all()]
            if debug is not None:
                debug["strategy"] = "firstk_all_docs_admin"
                debug["count"] = len(rows)
                debug["top5"] = _preview(rows)
            return rows, debug

        rows = [dict(r) for r in db.execute(sql_text(SQL_FIRSTK_ALL_DOCS_USER), {"k": k_eff, "owner_sub": p.sub}).mappings().all()]
        if debug is not None:
            debug["strategy"] = "firstk_all_docs_user"
            debug["count"] = len(rows)
            debug["top5"] = _preview(rows)
        return rows, debug

    if is_admin(p):
        if ENABLE_HYBRID and q_text:
            vec = [dict(r) for r in db.execute(sql_text(SQL_TOPK_ALL_DOCS_ADMIN), {"qvec": qvec_lit, "k": HYBRID_VEC_K}).mappings().all()]
            fts = [dict(r) for r in db.execute(sql_text(SQL_FTS_ALL_DOCS_ADMIN), {"q": q_text, "k": HYBRID_FTS_K}).mappings().all()]
            merged = _rrf_merge(vec, fts, k)

            if debug is not None:
                debug["strategy"] = "hybrid_rrf_all_docs_admin"
                debug["vec_count"] = len(vec)
                debug["fts_count"] = len(fts)
                debug["merged_count"] = len(merged)
                debug["vec_top5"] = _preview(vec)
                debug["fts_top5"] = _preview(fts)
                debug["merged_top5"] = _preview(merged)

            return (merged if merged else vec[:k]), debug

        rows = [dict(r) for r in db.execute(sql_text(SQL_TOPK_ALL_DOCS_ADMIN), {"qvec": qvec_lit, "k": k}).mappings().all()]
        if debug is not None:
            debug["strategy"] = "vector_all_docs_admin"
            debug["count"] = len(rows)
            debug["top5"] = _preview(rows)
        return rows, debug

    # non-admin: user's docs only
    if ENABLE_HYBRID and q_text:
        vec = [dict(r) for r in db.execute(sql_text(SQL_TOPK_ALL_DOCS_USER), {"qvec": qvec_lit, "k": HYBRID_VEC_K, "owner_sub": p.sub}).mappings().all()]
        fts = [dict(r) for r in db.execute(sql_text(SQL_FTS_ALL_DOCS_USER), {"q": q_text, "k": HYBRID_FTS_K, "owner_sub": p.sub}).mappings().all()]
        merged = _rrf_merge(vec, fts, k)

        if debug is not None:
            debug["strategy"] = "hybrid_rrf_all_docs_user"
            debug["vec_count"] = len(vec)
            debug["fts_count"] = len(fts)
            debug["merged_count"] = len(merged)
            debug["vec_top5"] = _preview(vec)
            debug["fts_top5"] = _preview(fts)
            debug["merged_top5"] = _preview(merged)

        return (merged if merged else vec[:k]), debug

    rows = [dict(r) for r in db.execute(sql_text(SQL_TOPK_ALL_DOCS_USER), {"qvec": qvec_lit, "k": k, "owner_sub": p.sub}).mappings().all()]
    if debug is not None:
        debug["strategy"] = "vector_all_docs_user"
        debug["count"] = len(rows)
        debug["top5"] = _preview(rows)
    return rows, debug


# ============================================================
# Embedding helpers
# ============================================================

_openai_client = OpenAI()


def embed_query(question: str) -> list[float]:
    r = _openai_client.embeddings.create(model=EMBED_MODEL, input=question)
    return r.data[0].embedding


def to_pgvector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


# ============================================================
# Sources / Citations
# ============================================================

# LLMは [S1] だけ出す想定。返却前にサーバが [S1 p.1] にする。
SOURCE_ID_RE = re.compile(r"\[S(\d+)\]")
FORBIDDEN_INLINE_PAGE_RE = re.compile(r"\[S\d+\s+p\.\d+\]")
FORBIDDEN_PLACEHOLDER_RE = re.compile(r"\[S\?\s*p\.\?\]|\?")

FORBIDDEN_CITATION_PATTERNS = [
    r"\([0-9a-fA-F-]{16,}\s*,\s*page\s*\d+\)",
    r"\[[0-9a-fA-F-]{16,}\s*,\s*page\s*=?\s*\d+\]",
    r"\(chunk_id\s*=\s*[0-9a-fA-F-]{16,}.*?\)",
    r"\[chunk_id\s*=\s*[0-9a-fA-F-]{16,}.*?\]",
]


def clean_forbidden_citations(text: str) -> str:
    if not text:
        return text
    cleaned = text
    for pat in FORBIDDEN_CITATION_PATTERNS:
        cleaned = re.sub(pat, "", cleaned)
    cleaned = re.sub(r"\]\[S", "] [S", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def build_sources(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    sources: list[dict[str, Any]] = []
    parts: list[str] = []
    for i, r in enumerate(rows, start=1):
        sid = f"S{i}"
        sources.append(
            {
                "source_id": sid,
                "chunk_id": r["id"],
                "page": r["page"],
                "document_id": r["document_id"],
                "filename": r.get("filename"),
            }
        )
        parts.append(f"[{sid}]\n{r['text']}")
    context = "\n\n---\n\n".join(parts)
    return context, sources


def extract_used_source_ids(answer: str) -> list[str]:
    seen: set[str] = set()
    used: list[str] = []
    for m in SOURCE_ID_RE.finditer(answer or ""):
        sid = f"S{m.group(1)}"
        if sid not in seen:
            seen.add(sid)
            used.append(sid)
    return used


def filter_sources(sources: list[dict[str, Any]], used_ids: Iterable[str]) -> list[dict[str, Any]]:
    used_set = set(used_ids)
    return [s for s in sources if s["source_id"] in used_set]


def _split_citable_units(text: str) -> list[str]:
    """
    契約検証の単位。
    - 複数行なら「行」単位（各要点=各行を想定）
    - 1行なら句点などで分割（最低限）
    """
    t = (text or "").strip()
    if not t:
        return []
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if len(lines) >= 2:
        return lines
    return [s.strip() for s in re.split(r"(?<=[.!?。！？])\s*", t) if s.strip()]


def validate_citations(answer: str, used_ids: list[str], allowed_ids: set[str]) -> tuple[bool, str]:
    if not used_ids:
        return False, "missing_citations"

    if FORBIDDEN_INLINE_PAGE_RE.search(answer or ""):
        return False, "inline_page_numbers_forbidden"

    # 変なプレースホルダや ? を混ぜるのを抑止
    if FORBIDDEN_PLACEHOLDER_RE.search(answer or ""):
        return False, "placeholder_or_questionmark_forbidden"

    invalid = [sid for sid in used_ids if sid not in allowed_ids]
    if invalid:
        return False, f"invalid_source_ids:{','.join(invalid)}"

    units = _split_citable_units(answer)
    if units:
        for i, u in enumerate(units, start=1):
            if not SOURCE_ID_RE.search(u):
                return False, f"unit_missing_citation:{i}"

    return True, "ok"


def add_page_to_inline_citations(answer: str, citations: list[dict[str, Any]]) -> str:
    """
    返却前に [S#] を [S# p.#] に変換。
    すでに p. が付いているものは触らない。
    """
    if not answer:
        return answer

    page_by_sid: dict[str, Any] = {
        c.get("source_id"): c.get("page")
        for c in (citations or [])
        if c.get("source_id")
    }

    pattern = re.compile(r"\[(S\d+)\](?!\s*p\.)")

    def repl(m: re.Match) -> str:
        sid = m.group(1)
        page = page_by_sid.get(sid)
        return f"[{sid} p.{page}]" if page is not None else f"[{sid}]"

    return pattern.sub(repl, answer)


# ============================================================
# Run config (model/gen)
# ============================================================

def get_model_and_gen_from_run(run: Run | None) -> tuple[str, dict[str, Any]]:
    if not run:
        return DEFAULT_CHAT_MODEL, {}
    cfg = run.config or {}
    model = cfg.get("model") or DEFAULT_CHAT_MODEL
    gen = cfg.get("gen") or {}
    if not isinstance(gen, dict):
        gen = {}
    return model, gen


# ============================================================
# OpenAI call (model-compatible)
# ============================================================

SYSTEM_PROMPT = (
    "You are a QA assistant.\n"
    "Use ONLY the provided sources.\n"
    "If the answer is not in the sources, say you don't know.\n"
    "\n"
    "CITATION RULES (STRICT):\n"
    "- Cite sources ONLY using this format: [S1], [S2], ...\n"
    "- Never include page numbers, '?', chunk_id, document_id, or any other citation format.\n"
    "- Each bullet/line must contain at least one citation like [S1].\n"
    "- Do NOT cite any source ID that is not provided.\n"
    "\n"
    "Output plain text (no JSON)."
)


def _extract_unsupported_param(err_text: str) -> str | None:
    patterns = [
        r"param[\"']\s*:\s*[\"'](\w+)[\"']",
        r'"param"\s*:\s*"(\w+)"',
        r"Unsupported value:\s*'(\w+)'",
        r"Unsupported parameter:\s*'(\w+)'",
    ]
    for pat in patterns:
        m = re.search(pat, err_text or "")
        if m:
            return m.group(1)
    return None


def _chat_create_with_fallback(client: OpenAI, kwargs: dict[str, Any]) -> str:
    last_err: Exception | None = None
    attempt_kwargs = dict(kwargs)

    for _ in range(UNSUPPORTED_PARAM_RETRIES + 1):
        try:
            resp = client.chat.completions.create(**attempt_kwargs)
            return resp.choices[0].message.content
        except Exception as e:
            last_err = e
            text = str(e)

            param = _extract_unsupported_param(text)
            if param and param in attempt_kwargs:
                attempt_kwargs.pop(param, None)
                continue

            raise

    raise last_err if last_err else RuntimeError("Unknown error in chat completion")


def build_chat_kwargs(
    model: str,
    gen: dict[str, Any],
    question: str,
    sources_context: str,
    repair_note: str | None,
) -> dict[str, Any]:
    note = f"\n\nREPAIR NOTE:\n{repair_note}\n" if repair_note else ""

    q_llm = sanitize_question_for_llm(question)

    guard = (
        "\n\nIMPORTANT:\n"
        "- Even if the user asks for page-number citations, you MUST cite only as [S#].\n"
        "- Do NOT output '?' placeholders.\n"
        "- Use bullet points, one per line, and include at least one [S#] per line.\n"
    )

    user = f"Question:\n{q_llm}{guard}\n\nSources:\n{sources_context}{note}"

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    }

    blocked = KNOWN_UNSUPPORTED_PARAMS.get(model, set())
    for key in ALLOWED_GEN_KEYS:
        if key in blocked:
            continue
        if key in gen and gen[key] is not None:
            kwargs[key] = gen[key]

    return kwargs


def call_llm(model: str, gen: dict[str, Any], question: str, sources_context: str, repair_note: str | None) -> str:
    kwargs = build_chat_kwargs(model, gen, question, sources_context, repair_note)
    return _chat_create_with_fallback(_openai_client, kwargs)


def answer_with_contract(
    model: str,
    gen: dict[str, Any],
    question: str,
    sources_context: str,
    allowed_ids: set[str],
) -> tuple[str, list[str]]:
    repair_note: str | None = None

    for attempt in range(CONTRACT_RETRIES + 1):
        raw = call_llm(model, gen, question, sources_context, repair_note)
        cleaned = clean_forbidden_citations(raw)
        used = extract_used_source_ids(cleaned)

        ok, reason = validate_citations(cleaned, used, allowed_ids)
        if ok:
            return cleaned, used

        if attempt < CONTRACT_RETRIES:
            repair_note = (
                f"Your previous answer violated citation rules ({reason}). "
                "Rewrite as 3 bullet points (one per line). "
                "Each line MUST include at least one valid [S#] citation. "
                "Use ONLY [S#] citations; do not include page numbers or '?' placeholders."
            )

    return "I don't know based on the provided sources.", []


# ============================================================
# Route
# ============================================================

@router.post("/chat/ask")
def ask(
    payload: AskPayload,
    request: Request,
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("read:docs")),
):
    req_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")

    run: Run | None = None
    if payload.run_id:
        ensure_run_access(db, payload.run_id, p)

        run = db.get(Run, payload.run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")

        run.t0 = _utcnow()
        db.commit()

    try:
        # サニタイズした質問を embedding/fts/llm に使う
        q_clean = sanitize_question_for_llm(payload.question)

        qvec = embed_query(q_clean)
        qvec_lit = to_pgvector_literal(qvec)

        rows, retrieval_debug = fetch_chunks(
            db,
            qvec_lit=qvec_lit,
            q_text=q_clean,
            k=payload.k,
            run_id=payload.run_id,
            p=p,
            question=payload.question,
        )

        if not rows:
            if run:
                run.t3 = _utcnow()
                db.commit()
            resp = {
                "answer": "I don't know based on the provided sources.",
                "citations": [],
                "run_id": payload.run_id,
                "request_id": req_id,
            }
            if ENABLE_RETRIEVAL_DEBUG:
                resp["retrieval_debug"] = retrieval_debug
            return resp

        context, sources = build_sources(rows)
        allowed_ids = {s["source_id"] for s in sources}

        model, gen = get_model_and_gen_from_run(run)

        if run:
            run.t1 = _utcnow()
            db.commit()

        # ① LLMは [S#] のみ
        answer, used_ids = answer_with_contract(model, gen, payload.question, context, allowed_ids)

        if run:
            run.t2 = _utcnow()
            db.commit()

        used_sources = filter_sources(sources, used_ids)

        # ② サーバで [S#] -> [S# p.#]
        answer = add_page_to_inline_citations(answer, used_sources)

        if run:
            run.t3 = _utcnow()
            db.commit()

        resp = {
            "answer": answer,
            "citations": used_sources,
            "run_id": payload.run_id,
            "request_id": req_id,
        }
        if ENABLE_RETRIEVAL_DEBUG:
            resp["retrieval_debug"] = retrieval_debug
        return resp

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ask failed", extra={"request_id": req_id, "run_id": payload.run_id})
        raise HTTPException(status_code=500, detail=str(e))
