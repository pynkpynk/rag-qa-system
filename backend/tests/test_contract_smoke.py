from __future__ import annotations

from datetime import datetime, timezone

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.models import Base, Document
from app.db.session import get_db
import app.api.routes.chat as chat_module

# Ensure tests default to offline/dev auth.
os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("OPENAI_OFFLINE", "1")

client = TestClient(app)


def _dev_headers(sub: str = "dev|local") -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-token",
        "x-dev-sub": sub,
    }


@pytest.fixture()
def sqlite_app_db(monkeypatch: pytest.MonkeyPatch):
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
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    try:
        yield SessionLocal
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _insert_document(session_factory, *, document_id: str = "doc-contract", owner_sub: str = "dev|local"):
    with session_factory() as db:
        doc = Document(
            id=document_id,
            filename="contract.pdf",
            status="indexed",
            owner_sub=owner_sub,
            created_at=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.commit()


def test_contract_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    for key in ("app", "version", "time_utc"):
        assert key in payload


def test_contract_docs_list_and_detail(sqlite_app_db):
    _insert_document(sqlite_app_db)

    list_resp = client.get("/api/docs", headers=_dev_headers())
    assert list_resp.status_code == 200
    docs = list_resp.json()
    assert isinstance(docs, list) and docs
    assert docs[0]["document_id"] == "doc-contract"

    detail_resp = client.get("/api/docs/doc-contract", headers=_dev_headers())
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    for key in ("document_id", "filename", "status", "created_at"):
        assert key in detail


def test_contract_create_run(sqlite_app_db):
    payload = {"config": {"mode": "library"}}
    resp = client.post("/api/runs", headers=_dev_headers(), json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body and body["config"] == {"mode": "library"}


def test_contract_chat_ask(monkeypatch: pytest.MonkeyPatch, sqlite_app_db):
    def fake_fetch_chunks(*_args, **_kwargs):
        rows = [
            {
                "id": "chunk-1",
                "page": 1,
                "document_id": "doc-contract",
                "filename": "contract.pdf",
                "text": "Stakeholders Alice and Bob require clear evidence.",
            }
        ]
        debug = {
            "strategy": "stub",
            "vec_count": 1,
            "used_fts": False,
            "used_trgm": False,
            "fts_skipped": False,
            "trgm_available": True,
        }
        return rows, debug

    monkeypatch.setattr(chat_module, "fetch_chunks", fake_fetch_chunks)

    resp = client.post(
        "/api/chat/ask",
        headers=_dev_headers(),
        json={"question": "Provide a short summary of the stakeholders for this project."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    citations = body.get("citations")
    assert isinstance(citations, list) and len(citations) > 0
    lower_answer = body["answer"].lower()
    assert "alice" in lower_answer or "bob" in lower_answer
