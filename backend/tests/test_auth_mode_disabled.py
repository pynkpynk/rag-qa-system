from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
import app.api.routes.chat as chat_module


client = TestClient(app)


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
    monkeypatch.setattr(chat_module, "fetch_chunks", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(chat_module, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(
        chat_module, "answer_with_contract", lambda *args, **kwargs: ("ok", [])
    )

    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_auth_mode_disabled_allows_chat_without_token(
    monkeypatch: pytest.MonkeyPatch, stub_chat
) -> None:
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("APP_ENV", "dev")
    resp = client.post(
        "/api/chat/ask",
        json={"question": "summarize policy"},
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code in (200, 201), resp.text
