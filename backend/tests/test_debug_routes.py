from fastapi.testclient import TestClient


def _client():
    from app.main import app

    return TestClient(app)


def _headers(token: str = "secret") -> dict[str, str]:
    return {"X-Debug-Token": token}


def test_debug_routes_blocked_in_prod(monkeypatch):
    from app.core import config as config_module

    monkeypatch.setenv("DEBUG_TOKEN", "secret")
    monkeypatch.setattr(config_module.settings, "app_env", "prod", raising=False)

    client = _client()
    resp = client.get("/api/_debug/aws-whoami", headers=_headers())
    assert resp.status_code == 404
    resp2 = client.get(
        "/api/_debug/s3-head", params={"key": "doc.pdf"}, headers=_headers()
    )
    assert resp2.status_code == 404
