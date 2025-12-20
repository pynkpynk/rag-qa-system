from typing import List, Tuple
from pypdf import PdfReader
from openai import OpenAI

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
    # 複数入力をまとめて投げられる（高速＆安い）。:contentReference[oaicite:3]{index=3}
    client = OpenAI()
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in resp.data]
