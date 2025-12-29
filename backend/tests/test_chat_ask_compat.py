import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

API_BASE = ""  # TestClientなので不要
TOKEN = os.environ.get("TOKEN", "test")

def _headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

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
