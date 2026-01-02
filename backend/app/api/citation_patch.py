from __future__ import annotations

from typing import Any

from app.api.routes import chat


def _build_sources_with_chunk_meta(
    rows: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    sources: list[dict[str, Any]] = []
    parts: list[str] = []
    for i, r in enumerate(rows, start=1):
        sid = f"S{i}"
        chunk_id = r.get("id")
        entry: dict[str, Any] = {
            "source_id": sid,
            "chunk_id": chunk_id,
            "document_id": r.get("document_id"),
            "page": r.get("page"),
            "filename": r.get("filename"),
        }
        if chunk_id is None:
            entry["chunk_id_missing_reason"] = "chunk_id_missing"
        sources.append(entry)
        parts.append(f"[{sid}]\n{chat.guard_source_text(r['text'])}")
    context = "\n\n---\n\n".join(parts)
    return context, sources


def _public_citations_with_chunk_meta(
    citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in citations or []:
        chunk_id = c.get("chunk_id")
        entry = {
            "source_id": c.get("source_id"),
            "page": c.get("page"),
            "filename": c.get("filename"),
            "document_id": c.get("document_id"),
            "chunk_id": chunk_id,
            "drilldown_blocked_reason": c.get("drilldown_blocked_reason"),
        }
        missing_reason = c.get("chunk_id_missing_reason")
        if chunk_id is None and missing_reason:
            entry["chunk_id_missing_reason"] = missing_reason
        out.append(entry)
    return out


if not getattr(chat, "_CITATION_PATCHED", False):
    chat.build_sources = _build_sources_with_chunk_meta
    chat.public_citations = _public_citations_with_chunk_meta
    setattr(chat, "_CITATION_PATCHED", True)
