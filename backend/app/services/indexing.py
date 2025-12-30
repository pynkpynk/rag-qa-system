import hashlib
import os
from typing import List, Tuple

from pypdf import PdfReader
from openai import OpenAI

EMBED_DIM = int(os.getenv("EMBED_DIM", "1536") or "1536")


def _truthy_env(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def _offline_embedding(text: str) -> List[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [(byte / 255.0) * 2 - 1 for byte in digest]
    if not vec:
        vec = [0.0]
    while len(vec) < EMBED_DIM:
        need = EMBED_DIM - len(vec)
        vec.extend(vec[:need])
    return vec[:EMBED_DIM]


def extract_pdf_pages(path: str) -> List[Tuple[int, str]]:
    reader = PdfReader(path)
    out = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            out.append((i + 1, text))
    return out


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
