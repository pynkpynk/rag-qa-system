from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, create_app
from app.core.config import settings
from app.db.capabilities import DBCapabilities


def _stub_caps(*args, **kwargs):
    return DBCapabilities(
        extensions_present=["vector"],
        pg_trgm_available=False,
        vector_available=True,
        checked_ok=True,
        error=None,
        missing_required_extensions=[],
    )


def test_debug_routes_locked_in_prod(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.delenv("ALLOW_PROD_DEBUG", raising=False)
    monkeypatch.setenv("DEBUG_TOKEN", "secret")
    client = TestClient(app)
    resp = client.get("/api/_debug/aws-whoami", headers={"X-Debug-Token": "secret"})
    assert resp.status_code == 404


def test_prod_cors_denies_without_origins(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "cors_origin", "")
    monkeypatch.setattr("app.db.capabilities.detect_db_capabilities", _stub_caps)
    new_app = create_app()
    client = TestClient(new_app)
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in resp.headers
