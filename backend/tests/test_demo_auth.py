from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
import app.api.routes.chat as chat


client = TestClient(app)


@pytest.fixture
def demo_token() -> str:
    return "demo-secret-token"


@pytest.fixture
def demo_env(monkeypatch: pytest.MonkeyPatch, demo_token: str):
    digest = hashlib.sha256(demo_token.encode("utf-8")).hexdigest()
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("DEMO_TOKEN_SHA256_LIST", digest)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    yield demo_token


def test_demo_mode_requires_bearer_token(demo_env: str):
    resp = client.get("/api/docs")
    assert resp.status_code == 401


def test_demo_mode_rejects_invalid_token(demo_env: str):
    resp = client.get("/api/docs", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


@pytest.fixture
def stub_chat(monkeypatch: pytest.MonkeyPatch):
    class DummySession:
        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    dummy = DummySession()

    def override_db():
        yield dummy

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(chat, "fetch_chunks", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(chat, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(chat, "answer_with_contract", lambda *args, **kwargs: ("demo answer", []))

    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_demo_token_allows_chat(monkeypatch: pytest.MonkeyPatch, demo_env: str, stub_chat):
    digest = hashlib.sha256(demo_env.encode("utf-8")).hexdigest()
    monkeypatch.setenv("DEMO_TOKEN_SHA256_LIST", digest)
    resp = client.post(
        "/api/chat/ask",
        headers={"Authorization": f"Bearer {demo_env}", "Content-Type": "application/json"},
        json={"question": "demo question"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "answer" in data
