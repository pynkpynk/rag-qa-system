from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.models import Base, Document, Run, run_documents
import app.api.routes.docs as docs_router
import app.api.routes.runs as runs_router

client = TestClient(app)


def _dev_headers(sub: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-token",
        "x-dev-sub": sub,
    }


def _tables_subset(*tables: Iterable):
    # Helper to collect SQLAlchemy Table objects (ignoring None)
    subset: list = []
    for table in tables:
        if table is None:
            continue
        subset.append(table)
    return subset


@pytest.fixture(autouse=True)
def _set_default_auth_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_MODE", "dev")
    yield


@pytest.fixture()
def sqlite_docs_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    tables = _tables_subset(Document.__table__, Run.__table__, run_documents)
    Base.metadata.create_all(bind=engine, tables=tables)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[docs_router.get_db] = override_get_db
    app.dependency_overrides[runs_router.get_db] = override_get_db
    try:
        yield SessionLocal
    finally:
        app.dependency_overrides.pop(docs_router.get_db, None)
        app.dependency_overrides.pop(runs_router.get_db, None)
        Base.metadata.drop_all(bind=engine, tables=tables)
        engine.dispose()


def _seed_document(session_factory, *, document_id: str, owner_sub: str):
    with session_factory() as db:
        doc = Document(
            id=document_id,
            filename="doc.pdf",
            status="indexed",
            owner_sub=owner_sub,
            created_at=datetime.now(timezone.utc),
        )
        db.add(doc)
        db.commit()


def test_docs_list_filters_by_owner(sqlite_docs_db):
    _seed_document(sqlite_docs_db, document_id="doc-owned", owner_sub="user-a")

    resp_owner = client.get("/api/docs", headers=_dev_headers("user-a"))
    assert resp_owner.status_code == 200
    assert len(resp_owner.json()) == 1

    resp_other = client.get("/api/docs", headers=_dev_headers("user-b"))
    assert resp_other.status_code == 200
    assert resp_other.json() == []


def test_docs_delete_requires_owner(sqlite_docs_db):
    _seed_document(sqlite_docs_db, document_id="doc-delete", owner_sub="user-a")

    resp_other = client.delete("/api/docs/doc-delete", headers=_dev_headers("user-b"))
    assert resp_other.status_code == 404

    resp_owner = client.delete("/api/docs/doc-delete", headers=_dev_headers("user-a"))
    assert resp_owner.status_code == 204


def test_docs_list_requires_auth_in_dev_mode(sqlite_docs_db):
    resp = client.get("/api/docs")
    assert resp.status_code == 401


def test_docs_list_requires_auth_in_auth0_mode(monkeypatch: pytest.MonkeyPatch, sqlite_docs_db):
    monkeypatch.setenv("AUTH_MODE", "auth0")
    resp = client.get("/api/docs")
    assert resp.status_code == 401


def test_doc_detail_hidden_from_non_owner(sqlite_docs_db):
    _seed_document(sqlite_docs_db, document_id="doc-detail", owner_sub="user-a")

    res = client.get("/api/docs/doc-detail", headers=_dev_headers("user-b"))
    assert res.status_code == 404


def test_attach_docs_rejects_foreign_documents(sqlite_docs_db):
    _seed_document(sqlite_docs_db, document_id="doc-owned", owner_sub="user-a")

    run_resp = client.post(
        "/api/runs",
        headers=_dev_headers("user-b"),
        json={"config": {}, "document_ids": None},
    )
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]

    attach_resp = client.post(
        f"/api/runs/{run_id}/attach_docs",
        headers=_dev_headers("user-b"),
        json={"document_ids": ["doc-owned"]},
    )
    assert attach_resp.status_code == 400
