from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.api.routes.search as search_module
from app.db.hybrid_search import HybridHit, HybridMeta
from app.db.session import get_db

pytestmark = pytest.mark.usefixtures("force_dev_auth")

client = TestClient(app)


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer dev-token", "x-dev-sub": "dev|user"}


@pytest.fixture(autouse=True)
def override_search_dependencies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    monkeypatch.setattr(search_module, "_embed_query", lambda q: [0.0])

    fake_hit = HybridHit(
        chunk_id="chunk-1",
        document_id="doc-1",
        filename="demo.pdf",
        page=1,
        chunk_index=0,
        text="capital of France is Paris",
        score=0.9,
        rank_fts=1,
        rank_vec=None,
        vec_distance=None,
        rank_trgm=None,
        trgm_sim=None,
    )
    fake_meta = HybridMeta(
        fts_count=1,
        vec_count=0,
        trgm_count=0,
        vec_min_distance=None,
        vec_max_distance=None,
        vec_avg_distance=None,
        trgm_min_sim=None,
        trgm_max_sim=None,
        trgm_avg_sim=None,
    )
    monkeypatch.setattr(
        search_module,
        "hybrid_search_chunks_rrf",
        lambda *args, **kwargs: ([fake_hit], fake_meta),
    )

    def _override_db():
        db = SimpleNamespace(close=lambda: None)
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_search_defaults_to_library_when_mode_missing():
    resp = client.post("/api/search", headers=_headers(), json={"q": "capital"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hits"], "expected hits in default mode search"


def test_search_selected_docs_without_ids_still_422():
    resp = client.post(
        "/api/search",
        headers=_headers(),
        json={"q": "capital", "mode": "selected_docs"},
    )
    assert resp.status_code == 422
    assert "document_ids is required when mode=selected_docs" in resp.text
