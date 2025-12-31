from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient
from io import BytesIO
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import get_db
import app.api.routes.chat as chat
import app.api.routes.docs as docs_module
from app.db.models import Base


client = TestClient(app)


@pytest.fixture
def demo_token() -> str:
    return "demo-secret-token"


@pytest.fixture
def demo_env(monkeypatch: pytest.MonkeyPatch, demo_token: str):
    digest = hashlib.sha256(demo_token.encode("utf-8")).hexdigest()
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("DEMO_TOKEN_SHA256_LIST", digest)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    yield demo_token


def test_demo_mode_requires_bearer_token(demo_env: str):
    resp = client.get("/api/docs")
    assert resp.status_code == 401


def test_demo_mode_rejects_invalid_token(demo_env: str):
    resp = client.get("/api/docs", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


@pytest.fixture
def stub_chat(monkeypatch: pytest.MonkeyPatch):
    class DummySession:
        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    dummy = DummySession()

    def override_db():
        yield dummy

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(chat, "fetch_chunks", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(chat, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(chat, "answer_with_contract", lambda *args, **kwargs: ("demo answer", []))

    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def demo_docs_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
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
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_demo_token_allows_chat(monkeypatch: pytest.MonkeyPatch, demo_env: str, stub_chat):
    digest = hashlib.sha256(demo_env.encode("utf-8")).hexdigest()
    monkeypatch.setenv("DEMO_TOKEN_SHA256_LIST", digest)
    resp = client.post(
        "/api/chat/ask",
        headers={"Authorization": f"Bearer {demo_env}", "Content-Type": "application/json"},
        json={"question": "demo question"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "answer" in data
    assert "debug_meta" not in data
    assert "retrieval_debug" not in data


def test_demo_docs_upload_not_forbidden(demo_env: str, demo_docs_env):
    resp = client.post(
        "/api/docs/upload",
        headers={"Authorization": f"Bearer {demo_env}"},
        files={"file": ("sample.pdf", BytesIO(b"not a pdf"), "application/pdf")},
    )
    assert resp.status_code in {400, 415, 422}
    body = resp.json()
    assert resp.status_code != 403
    assert "error" in body
