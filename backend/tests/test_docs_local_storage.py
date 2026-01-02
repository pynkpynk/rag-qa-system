from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pydantic import SecretStr

from app.main import app
from app.db.models import Base, Document
from app.db.session import get_db
from app.api.routes import docs as docs_module
from app.core import config as config_module


client = TestClient(app)


def _dev_headers(sub: str = "dev|local") -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-token",
        "x-dev-sub": sub,
    }


@pytest.fixture()
def sqlite_docs_storage(monkeypatch: pytest.MonkeyPatch, tmp_path):
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
    monkeypatch.setattr(
        config_module.settings,
        "openai_api_key",
        SecretStr("ci-test-key"),
        raising=False,
    )

    try:
        yield SessionLocal, local_dir
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_upload_and_view_local_storage(sqlite_docs_storage):
    session_factory, local_dir = sqlite_docs_storage
    sample_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<<>>\nstartxref\n9\n%%EOF"

    resp = client.post(
        "/api/docs/upload",
        headers=_dev_headers(),
        files={"file": ("sample.pdf", BytesIO(sample_pdf), "application/pdf")},
    )
    assert resp.status_code == 200
    payload = resp.json()
    doc_id = payload["document_id"]
    stored_path = local_dir / f"{doc_id}.pdf"
    assert stored_path.exists()

    with session_factory() as db:
        doc = db.get(Document, doc_id)
        assert doc is not None
        assert doc.meta.get("storage") == "local"

    view_resp = client.get(f"/api/docs/{doc_id}/view", headers=_dev_headers())
    assert view_resp.status_code == 200
    assert view_resp.headers.get("content-type") == "application/pdf"
    assert view_resp.content.startswith(b"%PDF-")


def test_upload_marks_failed_when_openai_missing(
    monkeypatch: pytest.MonkeyPatch, sqlite_docs_storage
):
    session_factory, _ = sqlite_docs_storage
    monkeypatch.setenv("OPENAI_OFFLINE", "0")
    monkeypatch.setattr(
        config_module.settings, "openai_api_key", SecretStr(""), raising=False
    )

    sample_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<<>>\nstartxref\n9\n%%EOF"

    resp = client.post(
        "/api/docs/upload",
        headers=_dev_headers(),
        files={"file": ("sample.pdf", BytesIO(sample_pdf), "application/pdf")},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "failed"

    with session_factory() as db:
        doc = db.get(Document, payload["document_id"])
        assert doc is not None
        assert doc.status == "failed"
        assert "INDEXING_DISABLED" in (doc.error or "")


def test_upload_rejects_non_pdf_content_type(sqlite_docs_storage):
    resp = client.post(
        "/api/docs/upload",
        headers=_dev_headers(),
        files={"file": ("sample.pdf", BytesIO(b"%PDF-1.4\n"), "text/plain")},
    )
    assert resp.status_code == 415
    payload = resp.json()
    assert payload["error"]["message"] == "Content-Type must be application/pdf."


def test_upload_rejects_invalid_pdf_header(sqlite_docs_storage):
    resp = client.post(
        "/api/docs/upload",
        headers=_dev_headers(),
        files={"file": ("sample.pdf", BytesIO(b"not-a-pdf"), "application/pdf")},
    )
    assert resp.status_code == 400
    payload = resp.json()
    assert "Invalid PDF file" in payload["error"]["message"]


def test_upload_rejects_oversize(monkeypatch: pytest.MonkeyPatch, sqlite_docs_storage):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")
    oversized = b"%PDF-1.4\n" + b"A" * 20
    resp = client.post(
        "/api/docs/upload",
        headers=_dev_headers(),
        files={"file": ("sample.pdf", BytesIO(oversized), "application/pdf")},
    )
    assert resp.status_code == 413
    payload = resp.json()
    assert "File too large" in payload["error"]["message"]
