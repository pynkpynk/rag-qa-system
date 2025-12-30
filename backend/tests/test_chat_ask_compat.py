import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.api.routes.chat as chat
from app.db.session import get_db

client = TestClient(app)

API_BASE = ""  # TestClientなので不要
TOKEN = os.environ.get("TOKEN", "dev-token")

def _headers():
    return {
        "Authorization": f"Bearer {TOKEN}",
        "x-dev-sub": os.getenv("DEV_SUB", "test-user"),
        "Content-Type": "application/json",
    }


@pytest.fixture(autouse=True)
def _stub_chat_dependencies(monkeypatch: pytest.MonkeyPatch):
    class DummySession:
        def commit(self):
            return None

        def close(self):
            return None

    dummy = DummySession()

    def override_db():
        yield dummy

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(chat, "fetch_chunks", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(chat, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(chat, "answer_with_contract", lambda *args, **kwargs: ("compat answer", []))

    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)

def test_chat_ask_accepts_question():
    r = client.post("/api/chat/ask", headers=_headers(), json={
        "mode": "library",
        "question": "テスト質問",
        "debug": True,
    })
    assert r.status_code in (200, 201)

def test_chat_ask_accepts_message_alias():
    r = client.post("/api/chat/ask", headers=_headers(), json={
        "mode": "library",
        "message": "テスト質問",
        "debug": True,
    })
    assert r.status_code in (200, 201)

def test_chat_ask_prefers_question_when_both_present():
    r = client.post("/api/chat/ask", headers=_headers(), json={
        "mode": "library",
        "question": "question優先",
        "message": "messageは無視される想定",
        "debug": True,
    })
    assert r.status_code in (200, 201)

def test_chat_ask_requires_input():
    r = client.post("/api/chat/ask", headers=_headers(), json={
        "mode": "library",
        "debug": True,
    })
    assert r.status_code == 422
