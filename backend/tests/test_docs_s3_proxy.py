from __future__ import annotations

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


class DummyResponse:
    def __init__(self, *, status_code: int, headers: dict[str, str], body: bytes):
        self.status_code = status_code
        self.headers = headers
        self._body = body
        self._consumed = False

    @property
    def content(self) -> bytes:
        return self._body if self._consumed else b""

    @property
    def text(self) -> str:
        try:
            return self.content.decode("utf-8")
        except Exception:  # noqa: BLE001
            return ""

    @property
    def reason_phrase(self):
        return ""

    async def aread(self) -> bytes:
        self._consumed = True
        return self._body


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

    captured_client_kwargs = {}
    dummy_resp = DummyResponse(
        status_code=200,
        headers={
            "content-type": "application/pdf",
            "content-length": "11",
            "cache-control": "private",
        },
        body=b"%PDF-content",
    )

    class DummyClient:
        def __init__(self, *args, **kwargs):
            captured_client_kwargs.update(kwargs)
            self.last_headers = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            self.last_headers = headers or {}
            return dummy_resp

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    resp = client.get("/api/docs/doc-123/content", headers=_dev_headers())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.headers.get("accept-ranges") == "none"
    assert resp.headers.get("content-length") == str(len(b"%PDF-content"))
    assert resp.content.startswith(b"%PDF")
    assert captured_client_kwargs.get("follow_redirects") is True


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

    dummy_resp = DummyResponse(
        status_code=206,
        headers={
            "content-type": "application/pdf",
            "content-range": "bytes 0-3/11",
            "accept-ranges": "bytes",
            "content-length": "4",
        },
        body=b"%PDF",
    )
    captured_headers = {}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            captured_headers.update(headers or {})
            return dummy_resp

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    resp = client.get(
        "/api/docs/doc-123/content",
        headers={**_dev_headers(), "Range": "bytes=0-3"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("accept-ranges") == "none"
    assert captured_headers == {}
    assert resp.content.startswith(b"%PDF")


def test_proxy_pdf_empty_body_returns_502(monkeypatch: pytest.MonkeyPatch):
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

    dummy_resp = DummyResponse(
        status_code=200,
        headers={"content-type": "application/pdf"},
        body=b"",
    )

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return dummy_resp

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    resp = client.get("/api/docs/doc-123/content", headers=_dev_headers())
    assert resp.status_code == 502
    payload = resp.json()
    assert payload["error"]["code"] == "UPSTREAM_EMPTY_BODY"
