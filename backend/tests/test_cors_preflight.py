from __future__ import annotations

from fastapi.testclient import TestClient

from app.core import config
from app.main import create_app


def test_cors_preflight_allows_configured_origin(monkeypatch):
    origin = "http://localhost:5173"
    # Ensure only cors_origin is set so the new parser uses it.
    monkeypatch.setattr(config.settings, "cors_origin", origin, raising=False)
    if hasattr(config.settings, "cors_origins"):
        monkeypatch.setattr(config.settings, "cors_origins", "", raising=False)

    app = create_app()
    client = TestClient(app)

    resp = client.options(
        "/api/docs/upload",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == origin
