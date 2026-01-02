from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.models import Base, Document, Run, run_documents
from app.db.session import get_db
import app.api.routes.chat as chat

client = TestClient(app)
TOKEN = "dev-token"

pytestmark = pytest.mark.usefixtures("force_dev_auth")


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "x-dev-sub": os.getenv("DEV_SUB", "test-user"),
        "Content-Type": "application/json",
    }


@pytest.fixture(autouse=True)
def _sqlite_contract_db(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    tables = [Document.__table__, Run.__table__, run_documents]
    Base.metadata.create_all(bind=engine, tables=tables)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(chat, "fetch_chunks", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(chat, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(
        chat, "answer_with_contract", lambda *args, **kwargs: ("contract answer", [])
    )

    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine, tables=tables)
        engine.dispose()


def test_health_contract_shape():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    for key in (
        "app",
        "version",
        "status",
        "time_utc",
        "llm_enabled",
        "openai_offline",
        "openai_key_present",
    ):
        assert key in data
    assert isinstance(data["llm_enabled"], bool)
    assert isinstance(data["openai_offline"], bool)
    assert isinstance(data["openai_key_present"], bool)


def test_docs_list_contract():
    resp = client.get("/api/docs", headers=_auth_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_runs_list_contract():
    resp = client.get("/api/runs", headers=_auth_headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_chat_ask_contract():
    payload = {"question": "API契約テスト", "debug": False}
    resp = client.post("/api/chat/ask", headers=_auth_headers(), json=payload)
    assert resp.status_code in (200, 201)
    data = resp.json()
    for key in ("answer", "citations", "request_id"):
        assert key in data


def test_runs_requires_auth_in_auth0_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_MODE", "auth0")
    resp = client.get("/api/runs")
    assert resp.status_code == 401
