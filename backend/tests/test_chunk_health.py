from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.models import Base
from app.db.session import get_db

client = TestClient(app)


def _dev_headers(sub: str = "dev|local") -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-token",
        "x-dev-sub": sub,
    }


@pytest.fixture()
def sqlite_db():
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
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_chunks_health_includes_db_block(sqlite_db):
    resp = client.get("/api/chunks/health", headers=_dev_headers())
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    db_status = payload.get("db")
    assert isinstance(db_status, dict)
    for key in [
        "dialect",
        "alembic_revision",
        "alembic_head",
        "is_alembic_head",
        "chunks_fts_column",
        "fts_gin_index",
        "pg_trgm_installed",
        "text_trgm_index",
    ]:
        assert key in db_status
    for leak_key in ("host", "port", "url"):
        assert leak_key not in db_status
    leak_strings = ["localhost", "127.0.0.1", "://", "DATABASE_URL", "db_host", "db_port"]
    body = resp.text
    for needle in leak_strings:
        assert needle not in body
