from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

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

# 1) “引用契約”を満たすための修復リトライ回数
CONTRACT_RETRIES = 2

# 2) “モデルが受け付けないパラメータ”を外して再試行する回数
UNSUPPORTED_PARAM_RETRIES = 2

# run.config["gen"] から受け付ける生成パラメータ（増やすならここ）
ALLOWED_GEN_KEYS: set[str] = {
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "seed",
}

# 既知の「モデル × 非対応パラメータ」(分かったら増やす)
KNOWN_UNSUPPORTED_PARAMS: dict[str, set[str]] = {
    # 例：あなたのログで確定した挙動
    "gpt-5-mini": {"temperature"},
}

# ============================================================
# SQL (Retrieval) - include filename to help UI/debug
# ============================================================

SQL_TOPK_ALL_DOCS = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
ORDER BY c.embedding <=> (:qvec)::vector
LIMIT :k
"""

SQL_TOPK_BY_RUN = """
SELECT c.id, c.document_id, d.filename AS filename, c.page, c.chunk_index, c.text
FROM chunks c
JOIN documents d ON d.id = c.document_id
JOIN run_documents rd ON rd.document_id = c.document_id
WHERE rd.run_id = :run_id
ORDER BY c.embedding <=> (:qvec)::vector
LIMIT :k
"""

SQL_RUN_DOC_COUNT = """
SELECT COUNT(*) AS cnt
FROM run_documents
WHERE run_id = :run_id
"""

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def fetch_topk_chunks(db: Session, qvec_lit: str, k: int, run_id: str | None):
    """
    Fetch top-k chunks.
    - If run_id is provided: restrict to documents attached to the run.
    """
    if run_id:
        cnt_row = db.execute(sql_text(SQL_RUN_DOC_COUNT), {"run_id": run_id}).mappings().first()
        if not cnt_row or int(cnt_row["cnt"]) == 0:
            raise HTTPException(
                status_code=400,
                detail="This run_id has no attached documents. Attach docs first via /api/runs/{run_id}/attach_docs.",
            )

        return db.execute(
            sql_text(SQL_TOPK_BY_RUN),
            {"qvec": qvec_lit, "k": k, "run_id": run_id},
        ).mappings().all()

    return db.execute(
        sql_text(SQL_TOPK_ALL_DOCS),
        {"qvec": qvec_lit, "k": k},
    ).mappings().all()


# ============================================================
# Embedding helpers
# ============================================================

_openai_client = OpenAI()

def embed_query(question: str) -> list[float]:
    r = _openai_client.embeddings.create(model=EMBED_MODEL, input=question)
    return r.data[0].embedding

def to_pgvector_literal(vec: list[float]) -> str:
    # pgvectorは文字列 '[0.1,0.2,...]' を vector にcastできる
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


# ============================================================
# Sources / Citations
# ============================================================

SOURCE_ID_RE = re.compile(r"\[S(\d+)\]")

FORBIDDEN_CITATION_PATTERNS = [
    r"\([0-9a-fA-F-]{16,}\s*,\s*page\s*\d+\)",
    r"\[[0-9a-fA-F-]{16,}\s*,\s*page\s*=?\s*\d+\]",
    r"\(chunk_id\s*=\s*[0-9a-fA-F-]{16,}.*?\)",
    r"\[chunk_id\s*=\s*[0-9a-fA-F-]{16,}.*?\]",
]

def clean_forbidden_citations(text: str) -> str:
    """Remove any non-[S#] citation formats from the answer."""
    if not text:
        return text
    cleaned = text
    for pat in FORBIDDEN_CITATION_PATTERNS:
        cleaned = re.sub(pat, "", cleaned)
    cleaned = re.sub(r"\]\[S", "] [S", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned

def build_sources(rows) -> tuple[str, list[dict[str, Any]]]:
    """
    Build context with stable source IDs: [S1], [S2], ...
    Returns:
      - context string for the LLM
      - sources metadata list in the same order
    """
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
    """Extract [S#] tokens from model answer. Unique ids in appearance order."""
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

def _split_sentences(text: str) -> list[str]:
    """
    Very lightweight sentence splitter (good enough for enforcement).
    Splits on . ! ? followed by whitespace/newline.
    """
    t = (text or "").strip()
    if not t:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]

def validate_citations(answer: str, used_ids: list[str], allowed_ids: set[str]) -> tuple[bool, str]:
    """
    Contract:
      - must contain at least one [S#]
      - all cited ids must exist in allowed_ids
      - each sentence must include at least one [S#]
    """
    if not used_ids:
        return False, "missing_citations"

    invalid = [sid for sid in used_ids if sid not in allowed_ids]
    if invalid:
        return False, f"invalid_source_ids:{','.join(invalid)}"

    sentences = _split_sentences(answer)
    if sentences:
        for i, s in enumerate(sentences, start=1):
            if not SOURCE_ID_RE.search(s):
                return False, f"sentence_missing_citation:{i}"

    return True, "ok"


# ============================================================
# Run config (model/gen)
# ============================================================

def get_model_and_gen_from_run(run: Run | None) -> tuple[str, dict[str, Any]]:
    """
    If run exists:
      - model := run.config["model"] or default
      - gen   := run.config["gen"]   or {}
    Otherwise returns default model and empty gen.
    """
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
    "- Do NOT include chunk_id, document_id, page numbers, or any other citation format.\n"
    "- Every sentence must include at least one citation like [S1].\n"
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
    user = f"Question:\n{question}\n\nSources:\n{sources_context}{note}"

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
                "Rewrite the answer so that every sentence includes valid [S#] citations only."
            )

    return "I don't know based on the provided sources.", []


# ============================================================
# Route
# ============================================================

@router.post("/chat/ask")
def ask(payload: AskPayload, request: Request, db: Session = Depends(get_db)):
    req_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")

    run: Run | None = None
    if payload.run_id:
        run = db.get(Run, payload.run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")

        # best-effort: store latest timing markers on the run (debug/profiling)
        run.t0 = _utcnow()
        db.commit()

    try:
        qvec = embed_query(payload.question)
        qvec_lit = to_pgvector_literal(qvec)

        rows = fetch_topk_chunks(db, qvec_lit=qvec_lit, k=payload.k, run_id=payload.run_id)
        if not rows:
            if run:
                run.t3 = _utcnow()
                db.commit()
            return {
                "answer": "I don't know based on the provided sources.",
                "citations": [],
                "run_id": payload.run_id,
                "request_id": req_id,
            }

        context, sources = build_sources(rows)
        allowed_ids = {s["source_id"] for s in sources}

        model, gen = get_model_and_gen_from_run(run)

        if run:
            run.t1 = _utcnow()
            db.commit()

        answer, used_ids = answer_with_contract(model, gen, payload.question, context, allowed_ids)

        if run:
            run.t2 = _utcnow()
            db.commit()

        used_sources = filter_sources(sources, used_ids)

        if run:
            run.t3 = _utcnow()
            db.commit()

        return {
            "answer": answer,
            "citations": used_sources,
            "run_id": payload.run_id,
            "request_id": req_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ask failed", extra={"request_id": req_id, "run_id": payload.run_id})
        raise HTTPException(status_code=500, detail=str(e))
