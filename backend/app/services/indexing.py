import hashlib
import logging
import os
import re
from typing import List, Tuple

from openai import OpenAI
from pypdf import PdfReader

from app.services.ocr import get_ocr_backend

logger = logging.getLogger(__name__)

EMBED_DIM = int(os.getenv("EMBED_DIM", "1536") or "1536")


def _truthy_env(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _offline_embedding(text: str) -> List[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [(byte / 255.0) * 2 - 1 for byte in digest]
    if not vec:
        vec = [0.0]
    while len(vec) < EMBED_DIM:
        need = EMBED_DIM - len(vec)
        vec.extend(vec[:need])
    return vec[:EMBED_DIM]


def _extract_pdf_pages_pypdf(path: str) -> List[Tuple[int, str]]:
    reader = PdfReader(path)
    out = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            out.append((i + 1, text))
    return out


_TABLE_LINE_RE = re.compile(r"\S\s{2,}\S")


def normalize_table_like_text(text: str) -> str:
    lines = text.splitlines()
    normalized: list[str] = []
    for line in lines:
        if _TABLE_LINE_RE.search(line):
            normalized.append(re.sub(r"\s{2,}", "\t", line.rstrip()))
        else:
            normalized.append(line)
    return "\n".join(normalized)


def extract_pdf_pages_with_ocr_fallback(
    path: str,
    *,
    request_id: str | None = None,
    min_total_chars: int = 80,
) -> List[Tuple[int, str]]:
    pages = _extract_pdf_pages_pypdf(path)
    pages = [(num, normalize_table_like_text(text)) for num, text in pages]
    total_chars = sum(len(text) for _, text in pages)
    if total_chars >= min_total_chars or not os.path.exists(path):
        return pages

    try:
        backend = get_ocr_backend()
    except RuntimeError as exc:  # noqa: BLE001
        logger.info(
            "ocr_backend_unavailable",
            extra={"request_id": request_id, "error": str(exc)},
        )
        return pages

    try:
        ocr_pages = backend.extract(path, request_id=request_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "ocr_backend_failed",
            extra={"request_id": request_id, "error": str(exc)},
        )
        return pages

    if not ocr_pages:
        logger.info(
            "ocr_no_text_found",
            extra={"request_id": request_id},
        )
        return pages

    ocr_pages = [(num, normalize_table_like_text(text)) for num, text in ocr_pages]
    return ocr_pages


def extract_pdf_pages(path: str) -> List[Tuple[int, str]]:
    return extract_pdf_pages_with_ocr_fallback(path)


def simple_chunk(text: str, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        chunks.append(text[start:end].strip())
        if end == n:
            break
        start = max(0, end - overlap)
    return [c for c in chunks if c]


def embed_texts(texts: List[str]) -> List[List[float]]:
    if _truthy_env("OPENAI_OFFLINE", "0"):
        return [_offline_embedding(text) for text in texts]
    client = OpenAI()
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in resp.data]
