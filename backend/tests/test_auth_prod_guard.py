from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_dev_auth_forbidden_in_prod(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("AUTH_BYPASS_ALLOW_IN_PROD", "0")

    resp = client.get(
        "/api/docs",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body.get("error", {}).get("code") == "AUTH_BYPASS_FORBIDDEN"
