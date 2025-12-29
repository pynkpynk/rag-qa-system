from typing import Any, Dict

DEBUG_ALLOWLIST_TOP = {
    "retrieval": {"vec_count", "trgm_count", "fts_count", "used_fts", "rrf_k", "query_class", "elapsed_ms"},
    "sources": {"sid", "doc_id", "chunk_id", "page", "score"},
}

def sanitize_debug(debug: Dict[str, Any]) -> Dict[str, Any]:
    """
    Allowlist-based sanitizer. Drop everything else.
    """
    out: Dict[str, Any] = {}

    retrieval = debug.get("retrieval") or {}
    out["retrieval"] = {k: retrieval.get(k) for k in DEBUG_ALLOWLIST_TOP["retrieval"] if k in retrieval}

    sources = debug.get("sources") or []
    sanitized_sources = []
    for s in sources:
        sanitized_sources.append({k: s.get(k) for k in DEBUG_ALLOWLIST_TOP["sources"] if k in s})
    out["sources"] = sanitized_sources

    return out
