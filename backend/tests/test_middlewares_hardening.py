from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.middleware.security import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
)
from app.core import rate_limit


def test_request_id_propagation_on_health():
    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id")

    resp2 = client.get("/api/health", headers={"x-request-id": "test-req"})
    assert resp2.headers.get("x-request-id") == "test-req"


def test_security_headers_present_on_health():
    client = TestClient(create_app())
    resp = client.get("/api/health")
    headers = resp.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("referrer-policy") == "no-referrer"
    assert headers.get("permissions-policy") == "interest-cohort=()"
    assert headers.get("cross-origin-opener-policy") == "same-origin"
    assert headers.get("cross-origin-resource-policy") == "same-site"


def test_body_size_limit_returns_413(monkeypatch):
    monkeypatch.setenv("MAX_REQUEST_BYTES", "10")
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware)

    @app.post("/echo")
    async def echo(payload: dict):
        return payload

    client = TestClient(app)
    resp = client.post("/echo", json={"big": "0123456789abc"})
    assert resp.status_code == 413
    assert resp.json()["detail"] == "Request body too large"


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("RATE_LIMIT_RPM", "2")
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_ENABLED", True, raising=False)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_RPM", 2, raising=False)
    rate_limit._REQUEST_BUCKETS.clear()

    times = [0.0, 0.1, 0.2]

    class FakeTime:
        def monotonic(self):
            return times.pop(0)

    monkeypatch.setattr(rate_limit, "time", FakeTime(), raising=False)

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RateLimitMiddleware)

    @app.post("/api/chat/ask")
    async def ask():
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/api/chat/ask").status_code == 200
    assert client.post("/api/chat/ask").status_code == 200
    resp = client.post("/api/chat/ask")
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Rate limit exceeded"
