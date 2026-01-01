from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.api.routes.chat as chat
from app.core.authz import Principal


class DummyRequest:
    def __init__(self):
        self.headers: dict[str, str] = {}
        self.state = SimpleNamespace(request_id=None)


class DummyDB:
    def commit(self) -> None:
        return None

    def execute(self, *args, **kwargs):
        raise AssertionError("execute should not be called in this test")

    def close(self) -> None:
        return None


class DummyRunDB(DummyDB):
    def get(self, model, key):
        return SimpleNamespace(id=key, t0=None, t1=None, t2=None, t3=None, config={}, document_ids=[])


def _sample_rows():
    return [
        {
            "id": "chunk-1",
            "document_id": "doc-1",
            "filename": "demo.pdf",
            "page": 1,
            "chunk_index": 0,
            "text": "Summary: The project improves reliability."
        },
        {
            "id": "chunk-2",
            "document_id": "doc-1",
            "filename": "demo.pdf",
            "page": 2,
            "chunk_index": 1,
            "text": "Key Facts: Stakeholders include Alice and Bob."
        },
    ]


def _stub_fetch_chunks(*args, **kwargs):
    return _sample_rows(), {}


def _noop_audit(**kwargs):
    return None


@pytest.fixture(autouse=True)
def _reset_offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_OFFLINE", "1")


def test_summary_with_document_ids_offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "_ensure_document_scope", lambda db, ids, principal: ids)
    monkeypatch.setattr(chat, "fetch_chunks", _stub_fetch_chunks)
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)
    payload = chat.AskPayload(question="Provide a summary of this document.", k=4, document_ids=["doc-1"])
    principal = Principal(sub="demo|user", permissions={"read:docs"})
    resp = chat.ask(payload, DummyRequest(), db=DummyDB(), p=principal)
    assert "I don't know" not in resp["answer"]
    assert resp["citations"], "citations should not be empty"


def test_summary_with_run_offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "ensure_run_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat, "fetch_chunks", _stub_fetch_chunks)
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)
    payload = chat.AskPayload(question="Summarize the run", k=3, run_id="run-1")
    principal = Principal(sub="demo|user", permissions={"read:docs"})
    resp = chat.ask(payload, DummyRequest(), db=DummyRunDB(), p=principal)
    assert "I don't know" not in resp["answer"]
    assert resp["citations"], "citations should not be empty"


def test_offline_answer_for_non_summary(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "_ensure_document_scope", lambda db, ids, principal: ids)
    monkeypatch.setattr(chat, "fetch_chunks", _stub_fetch_chunks)
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)
    payload = chat.AskPayload(question="List key stakeholders mentioned in the document.", k=4, document_ids=["doc-1"])
    principal = Principal(sub="demo|user", permissions={"read:docs"})
    resp = chat.ask(payload, DummyRequest(), db=DummyDB(), p=principal)
    assert "I don't know" not in (resp["answer"] or "")
    assert resp["citations"], "citations should not be empty"
