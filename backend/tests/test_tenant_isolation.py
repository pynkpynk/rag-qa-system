from __future__ import annotations

import hashlib
import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.hybrid_search import HybridHit, HybridMeta
from app.db.models import Base, Chunk, Document, EMBEDDING_DIM
from app.db.session import get_db
from app.api.routes import docs as docs_module
from app.api.routes import search as search_module
import app.api.routes.chat as chat_module


client = TestClient(app)

SAMPLE_PDF = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"2 0 obj\n<< /Length 44 >>\nstream\n"
    b"Hello tenant isolation world!\n"
    b"endstream\nendobj\nxref\n0 3\n"
    b"0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n"
    b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n120\n%%EOF"
)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def demo_tokens() -> tuple[str, str]:
    return ("demo-alpha", "demo-bravo")


@pytest.fixture
def tenant_env(monkeypatch: pytest.MonkeyPatch, demo_tokens: tuple[str, str]):
    hashes = [
        hashlib.sha256(token.encode("utf-8")).hexdigest() for token in demo_tokens
    ]
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DEMO_TOKEN_SHA256_LIST", ",".join(hashes))
    monkeypatch.delenv("DEMO_TOKEN_PLAINTEXT", raising=False)
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    yield demo_tokens


@pytest.fixture
def sqlite_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(docs_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(docs_module, "AWS_REGION", None)
    monkeypatch.setattr(docs_module, "S3_BUCKET", None)
    monkeypatch.setattr(docs_module, "_s3_client", None)
    monkeypatch.setattr(docs_module, "_s3_configured", lambda: False)
    local_dir = tmp_path / "uploads"
    local_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(docs_module, "LOCAL_STORAGE_DIR", local_dir)
    monkeypatch.setattr(docs_module, "index_document", lambda doc_id: None)

    try:
        yield SessionLocal
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def stub_pdf_processing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        docs_module,
        "_extract_pdf_pages_with_normalization",
        lambda *args, **kwargs: [(1, "tenant isolation sample text")],
    )


def _upload_doc(token: str) -> str:
    resp = client.post(
        "/api/docs/upload",
        headers=_auth_headers(token),
        files={"file": ("sample.pdf", BytesIO(SAMPLE_PDF), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["document_id"]


def _mark_doc_indexed(session_factory, doc_id: str) -> None:
    with session_factory() as db:
        doc = db.get(Document, doc_id)
        assert doc is not None
        doc.status = "indexed"
        db.commit()


def test_docs_are_isolated(tenant_env, sqlite_env):
    token_a, token_b = tenant_env
    doc_id = _upload_doc(token_a)

    resp_a = client.get("/api/docs", headers=_auth_headers(token_a))
    assert resp_a.status_code == 200
    ids_a = {item["document_id"] for item in resp_a.json()}
    assert doc_id in ids_a

    resp_b = client.get("/api/docs", headers=_auth_headers(token_b))
    assert resp_b.status_code == 200
    ids_b = {item["document_id"] for item in resp_b.json()}
    assert doc_id not in ids_b

    resp = client.delete(f"/api/docs/{doc_id}", headers=_auth_headers(token_b))
    assert resp.status_code == 404


def test_runs_are_isolated(tenant_env, sqlite_env):
    token_a, token_b = tenant_env
    doc_id = _upload_doc(token_a)
    _mark_doc_indexed(sqlite_env, doc_id)

    run_resp = client.post(
        "/api/runs",
        headers=_auth_headers(token_a),
        json={"config": {"label": "demo"}, "document_ids": [doc_id]},
    )
    assert run_resp.status_code == 200, run_resp.text
    run_id = run_resp.json()["run_id"]

    list_b = client.get("/api/runs", headers=_auth_headers(token_b))
    assert list_b.status_code == 200
    assert list_b.json() == []

    attach = client.post(
        f"/api/runs/{run_id}/attach_docs",
        headers=_auth_headers(token_b),
        json={"document_ids": [doc_id]},
    )
    assert attach.status_code == 404

    detail = client.get(f"/api/runs/{run_id}", headers=_auth_headers(token_b))
    assert detail.status_code == 404


def test_chat_rejects_foreign_docs(tenant_env, sqlite_env):
    token_a, token_b = tenant_env
    doc_id = _upload_doc(token_a)
    payload = {"question": "test", "document_ids": [doc_id]}
    resp = client.post(
        "/api/chat/ask",
        headers=_auth_headers(token_b),
        json=payload,
    )
    assert resp.status_code == 404


def test_chat_returns_citations_for_owner(
    tenant_env, sqlite_env, monkeypatch: pytest.MonkeyPatch
):
    token_a, _ = tenant_env
    doc_id = _upload_doc(token_a)
    fake_hit = HybridHit(
        chunk_id="fake-chunk",
        document_id=doc_id,
        filename="sample.pdf",
        page=1,
        chunk_index=0,
        text="tenant isolation chunk",
        score=1.0,
        rank_fts=1,
        rank_vec=1,
        vec_distance=0.1,
        rank_trgm=None,
        trgm_sim=None,
    )
    fake_meta = HybridMeta(
        fts_count=1,
        vec_count=1,
        trgm_count=0,
        vec_min_distance=0.1,
        vec_max_distance=0.1,
        vec_avg_distance=0.1,
        trgm_min_sim=None,
        trgm_max_sim=None,
        trgm_avg_sim=None,
    )

    def fake_hybrid(*args, **kwargs):
        return [fake_hit], fake_meta

    monkeypatch.setattr(chat_module, "hybrid_search_chunks_rrf", fake_hybrid)
    payload = {
        "question": "Return one bullet citing the uploaded PDF.",
        "document_ids": [doc_id],
        "k": 2,
    }
    first = client.post("/api/chat/ask", headers=_auth_headers(token_a), json=payload)
    second = client.post("/api/chat/ask", headers=_auth_headers(token_a), json=payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    for resp in (first.json(), second.json()):
        assert resp["citations"], "Expected at least one citation"
        assert resp["citations"][0].get("chunk_id") == "fake-chunk"


def test_chunks_and_search_are_isolated(tenant_env, sqlite_env, monkeypatch):
    token_a, token_b = tenant_env
    doc_id = _upload_doc(token_a)
    chunk_id = str(uuid.uuid4())
    text = "tenant isolation \x0bchunk text"

    with sqlite_env() as db:
        doc = db.get(Document, doc_id)
        assert doc is not None
        doc.status = "indexed"
        chunk = Chunk(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            page=1,
            text=text,
            embedding=[0.0] * EMBEDDING_DIM,
        )
        db.add(chunk)
        db.commit()

    search_b = client.post(
        "/api/search",
        headers=_auth_headers(token_b),
        json={
            "q": "tenant isolation",
            "mode": "selected_docs",
            "document_ids": [doc_id],
            "limit": 5,
        },
    )
    assert search_b.status_code == 404

    chunk_b = client.get(
        f"/api/chunks/{chunk_id}",
        headers=_auth_headers(token_b),
    )
    assert chunk_b.status_code == 404

    chunk_a = client.get(
        f"/api/chunks/{chunk_id}",
        headers=_auth_headers(token_a),
    )
    assert chunk_a.status_code == 200
    chunk_payload = chunk_a.json()
    assert "\x0b" not in chunk_payload["text"]

    fake_hit = HybridHit(
        chunk_id=chunk_id,
        document_id=doc_id,
        filename="owner.pdf",
        page=1,
        chunk_index=0,
        text="tenant isolation \x0bchunk text",
        score=1.0,
        rank_fts=1,
        rank_vec=1,
        vec_distance=0.05,
        rank_trgm=None,
        trgm_sim=None,
    )
    fake_meta = HybridMeta(
        fts_count=1,
        vec_count=1,
        trgm_count=0,
        vec_min_distance=0.05,
        vec_max_distance=0.05,
        vec_avg_distance=0.05,
        trgm_min_sim=None,
        trgm_max_sim=None,
        trgm_avg_sim=None,
    )

    def fake_search_hybrid(*args, **kwargs):
        return [fake_hit], fake_meta

    monkeypatch.setattr(
        search_module, "hybrid_search_chunks_rrf", fake_search_hybrid
    )

    search_a = client.post(
        "/api/search",
        headers=_auth_headers(token_a),
        json={
            "q": "tenant isolation",
            "mode": "selected_docs",
            "document_ids": [doc_id],
            "limit": 5,
        },
    )
    assert search_a.status_code == 200
    hits = search_a.json()["hits"]
    assert hits, "Expected search hits for owner"
    assert "\x0b" not in hits[0]["text"]
