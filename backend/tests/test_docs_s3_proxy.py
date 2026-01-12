from __future__ import annotations

from unittest.mock import ANY

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.api.routes.docs as docs_module


client = TestClient(app)


def _dev_headers(sub: str = "dev|local") -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-token",
        "x-dev-sub": sub,
    }


@pytest.fixture(autouse=True)
def _disable_local_storage(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(docs_module, "_doc_uses_local_storage", lambda doc: False)
    yield


def test_proxy_pdf_content_streams(monkeypatch: pytest.MonkeyPatch):
    dummy_doc = type(
        "Doc",
        (),
        {
            "id": "doc-123",
            "storage_key": "s3/key",
            "filename": "sample.pdf",
        },
    )
    monkeypatch.setattr(docs_module, "_s3_configured", lambda: True)

    class DummyDB:
        def __init__(self, doc):
            self.doc = doc

    def fake_get_doc(db, document_id, principal):
        return dummy_doc

    monkeypatch.setattr(docs_module, "_get_doc_for_read", fake_get_doc)
    monkeypatch.setattr(docs_module, "_enforce_run_access_if_needed", lambda *args, **kwargs: None)

    def fake_presign(key, inline, filename):
        return "https://example.com/presigned"

    monkeypatch.setattr(docs_module, "_s3_presign_get", fake_presign)

    class DummyResp:
        status_code = 200
        headers = {
            "content-type": "application/pdf",
            "content-length": "11",
        }

        def iter_raw(self):
            yield b"%PDF"
            yield b"-content"

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @property
        def text(self):
            return ""

    def fake_stream(method, url, headers=None, timeout=None):
        return DummyResp()

    monkeypatch.setattr(httpx, "stream", fake_stream)

    resp = client.get("/api/docs/doc-123/content", headers=_dev_headers())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF")


def test_proxy_pdf_respects_range(monkeypatch: pytest.MonkeyPatch):
    dummy_doc = type(
        "Doc",
        (),
        {
            "id": "doc-123",
            "storage_key": "s3/key",
            "filename": "sample.pdf",
        },
    )
    monkeypatch.setattr(docs_module, "_s3_configured", lambda: True)
    monkeypatch.setattr(docs_module, "_get_doc_for_read", lambda *args, **kwargs: dummy_doc)
    monkeypatch.setattr(docs_module, "_enforce_run_access_if_needed", lambda *args, **kwargs: None)
    monkeypatch.setattr(docs_module, "_s3_presign_get", lambda *args, **kwargs: "https://example.com/presigned")

    class DummyResp:
        status_code = 206
        headers = {
            "content-type": "application/pdf",
            "content-range": "bytes 0-3/11",
            "accept-ranges": "bytes",
            "content-length": "4",
        }

        def iter_raw(self):
            yield b"%PDF"

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @property
        def text(self):
            return ""

    captured_headers = {}

    def fake_stream(method, url, headers=None, timeout=None):
        captured_headers.update(headers or {})
        return DummyResp()

    monkeypatch.setattr(httpx, "stream", fake_stream)

    resp = client.get(
        "/api/docs/doc-123/content",
        headers={**_dev_headers(), "Range": "bytes=0-3"},
    )
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 0-3/11"
    assert captured_headers.get("range") == "bytes=0-3"
