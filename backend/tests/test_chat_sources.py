from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.api.routes.chat as chat_module

pytestmark = pytest.mark.usefixtures("force_dev_auth")

client = TestClient(app)


def _headers():
    return {"Authorization": "Bearer dev-token", "x-dev-sub": "dev|user"}


@pytest.fixture(autouse=True)
def stub_retrieval(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    monkeypatch.setattr(chat_module, "embed_query", lambda q: [0.0])

    def fake_fetch_chunks(*_args, **_kwargs):
        rows = [
            {
                "id": "chunk-1",
                "page": 2,
                "document_id": "doc-1",
                "filename": "demo.pdf",
                "text": "Line A\nLine B",
            }
        ]
        return rows, {"strategy": "stub", "fts_count": 1}

    monkeypatch.setattr(chat_module, "fetch_chunks", fake_fetch_chunks)


def test_chat_sources_include_line_ranges():
    payload = {"question": "Test question?"}
    resp = client.post("/api/chat/ask", headers=_headers(), json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    sources = body.get("sources")
    assert isinstance(sources, list) and sources, "expected sources in response"
    src = sources[0]
    assert src["source_id"] == "S1"
    assert src["chunk_id"] == "chunk-1"
    assert src["document_id"] == "doc-1"
    assert src["line_start"] == 1
    assert src["line_end"] == 2
    assert src["text"] == "Line A\nLine B"
