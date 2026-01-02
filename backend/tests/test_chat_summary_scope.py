from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.routes.chat as chat
from app.core.authz import Principal
from app.db.models import Base, Document, Run


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
        return SimpleNamespace(
            id=key, t0=None, t1=None, t2=None, t3=None, config={}, document_ids=[]
        )

    def execute(self, *args, **kwargs):
        class _Result:
            def scalar(self_inner):
                return 1

        return _Result()


def _sample_rows():
    return [
        {
            "id": "chunk-1",
            "document_id": "doc-1",
            "filename": "demo.pdf",
            "page": 1,
            "chunk_index": 0,
            "text": "Summary: The project improves reliability.",
        },
        {
            "id": "chunk-2",
            "document_id": "doc-1",
            "filename": "demo.pdf",
            "page": 2,
            "chunk_index": 1,
            "text": "Key Facts: Stakeholders include Alice and Bob.",
        },
    ]


def _stub_summary_chunks(*args, **kwargs):
    return _sample_rows(), {"strategy": "summary_offline_safe"}


def _stub_summary_chunks_missing_chunk(*args, **kwargs):
    rows = _sample_rows()
    rows[0] = rows[0].copy()
    rows[0].pop("id", None)
    return rows, {"strategy": "summary_offline_safe"}


def _stub_summary_run():
    return SimpleNamespace(
        id="summary-run", t0=None, t1=None, t2=None, t3=None, config={}, documents=[]
    )


def _noop_audit(**kwargs):
    return None


def _empty_summary_chunks(*args, **kwargs):
    return [], {"strategy": "summary_offline_safe"}


def _insert_document(session, doc_id: str, owner: str = "demo|user") -> None:
    doc = Document(
        id=doc_id, filename=f"{doc_id}.pdf", status="indexed", owner_sub=owner
    )
    session.add(doc)
    session.commit()


@pytest.fixture(autouse=True)
def _reset_offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_OFFLINE", "1")


def test_summary_with_document_ids_offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "_ensure_document_scope", lambda db, ids, principal: [])
    monkeypatch.setattr(chat, "fetch_summary_chunks", _stub_summary_chunks)
    monkeypatch.setattr(
        chat, "_create_summary_run", lambda *args, **kwargs: _stub_summary_run()
    )
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)
    payload = chat.AskPayload(
        question="Provide a summary of this document.",
        k=4,
        document_ids=["doc-1"],
        mode="summary_offline_safe",
    )
    principal = Principal(sub="demo|user", permissions={"read:docs"})
    resp = chat.ask(payload, DummyRequest(), db=DummyDB(), p=principal)
    assert "I don't know" not in resp["answer"]
    assert resp["citations"], "citations should not be empty"


def test_summary_citations_include_chunk_ids(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "fetch_summary_chunks", _stub_summary_chunks)
    monkeypatch.setattr(
        chat, "_create_summary_run", lambda *args, **kwargs: _stub_summary_run()
    )
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)
    payload = chat.AskPayload(
        question="Provide a run summary.",
        k=2,
        mode="summary_offline_safe",
    )
    principal = Principal(sub="demo|user", permissions={"read:docs"})
    resp = chat.ask(payload, DummyRequest(), db=DummyDB(), p=principal)
    assert resp["citations"], (
        "summary_offline_safe should return citations when chunks exist"
    )
    assert all(c.get("chunk_id") for c in resp["citations"]), resp["citations"]


def test_summary_citation_missing_chunk_has_reason(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        chat, "fetch_summary_chunks", _stub_summary_chunks_missing_chunk
    )
    monkeypatch.setattr(
        chat, "_create_summary_run", lambda *args, **kwargs: _stub_summary_run()
    )
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)
    payload = chat.AskPayload(
        question="Provide a summary even if chunk missing.",
        k=2,
        mode="summary_offline_safe",
    )
    principal = Principal(sub="demo|user", permissions={"read:docs"})
    resp = chat.ask(payload, DummyRequest(), db=DummyDB(), p=principal)
    assert resp["citations"], "citations should still be emitted"
    missing = next((c for c in resp["citations"] if c.get("chunk_id") is None), None)
    assert missing, resp["citations"]
    assert missing.get("chunk_id_missing_reason"), missing


def test_summary_with_run_offline(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "ensure_run_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat, "fetch_summary_chunks", _stub_summary_chunks)
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)
    payload = chat.AskPayload(
        question="Summarize the run",
        k=3,
        run_id="run-1",
        mode="summary_offline_safe",
    )
    principal = Principal(sub="demo|user", permissions={"read:docs"})
    resp = chat.ask(payload, DummyRequest(), db=DummyRunDB(), p=principal)
    assert "I don't know" not in resp["answer"]
    assert resp["citations"], "citations should not be empty"


def test_offline_answer_for_non_summary(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat, "_ensure_document_scope", lambda db, ids, principal: [])
    monkeypatch.setattr(chat, "fetch_summary_chunks", _stub_summary_chunks)
    monkeypatch.setattr(
        chat, "_create_summary_run", lambda *args, **kwargs: _stub_summary_run()
    )
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)
    payload = chat.AskPayload(
        question="List key stakeholders mentioned in the document.",
        k=4,
        document_ids=["doc-1"],
        mode="summary_offline_safe",
    )
    principal = Principal(sub="demo|user", permissions={"read:docs"})
    resp = chat.ask(payload, DummyRequest(), db=DummyDB(), p=principal)
    assert "I don't know" not in (resp["answer"] or "")
    assert resp["citations"], "citations should not be empty"


def test_fetch_summary_chunks_merges_anchor(monkeypatch: pytest.MonkeyPatch):
    base = [
        {
            "id": "chunk-base",
            "document_id": "doc-1",
            "filename": "demo.pdf",
            "page": 1,
            "chunk_index": 0,
            "text": "Intro text.",
        },
    ]
    anchor = [
        {
            "id": "chunk-anchor",
            "document_id": "doc-1",
            "filename": "demo.pdf",
            "page": 5,
            "chunk_index": 2,
            "text": "Contains zebra token.",
        },
    ]
    monkeypatch.setattr(
        chat, "_offline_chunk_sample", lambda *args, **kwargs: base.copy()
    )
    monkeypatch.setattr(
        chat,
        "_summary_anchor_chunks",
        lambda *args, **kwargs: anchor.copy(),
    )
    rows, debug = chat.fetch_summary_chunks(
        db=None,  # mocked helpers ignore db
        run_id=None,
        document_ids=["doc-1"],
        p=Principal(sub="demo|user", permissions={"read:docs"}),
        question="Give me a zebra highlight.",
        base_k=1,
        anchor_k=1,
    )
    ids = [row["id"] for row in rows]
    assert "chunk-anchor" in ids
    assert debug["anchor_hits"] == 1


def test_summary_without_run_id_creates_run(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    monkeypatch.setattr(chat, "fetch_summary_chunks", _stub_summary_chunks)
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    _insert_document(session, "doc-1")
    try:
        payload = chat.AskPayload(
            question="Provide a quick overview.",
            k=4,
            mode="summary_offline_safe",
        )
        principal = Principal(sub="demo|user", permissions={"read:docs"})
        resp = chat.ask(payload, DummyRequest(), db=session, p=principal)
        assert resp["run_id"], "summary mode should create a run_id when missing"
        assert resp["citations"], "summary mode should return citations"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_summary_invalid_run_replaced(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    monkeypatch.setattr(chat, "fetch_summary_chunks", _stub_summary_chunks)
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)

    def fake_ensure(*args, **kwargs):
        raise HTTPException(status_code=404, detail="run not found")

    monkeypatch.setattr(chat, "ensure_run_access", fake_ensure)
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    _insert_document(session, "doc-1")
    try:
        payload = chat.AskPayload(
            question="Summarize even if run missing.",
            k=4,
            run_id="missing-run",
            mode="summary_offline_safe",
        )
        principal = Principal(sub="demo|user", permissions={"read:docs"})
        resp = chat.ask(payload, DummyRequest(), db=session, p=principal)
        assert resp["run_id"] and resp["run_id"] != "missing-run"
        assert resp["citations"], "summary should still return citations"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_summary_no_sources_message(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    monkeypatch.setattr(chat, "fetch_summary_chunks", _empty_summary_chunks)
    monkeypatch.setattr(chat, "_emit_audit_event", _noop_audit)
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    try:
        payload = chat.AskPayload(
            question="Provide summary despite no docs",
            k=2,
            mode="summary_offline_safe",
        )
        principal = Principal(sub="demo|user", permissions={"read:docs"})
        resp = chat.ask(payload, DummyRequest(), db=session, p=principal)
        assert resp["run_id"], "response should include a run_id"
        assert resp["answer"].startswith("[NO_SOURCES]"), resp["answer"]
        assert resp["citations"] == []
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_summary_run_attaches_documents(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    monkeypatch.setattr(chat, "fetch_summary_chunks", _stub_summary_chunks)
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    _insert_document(session, "doc-1")
    try:
        payload = chat.AskPayload(
            question="Attach docs to summary run.",
            k=3,
            mode="summary_offline_safe",
        )
        principal = Principal(sub="demo|user", permissions={"read:docs"})
        resp = chat.ask(payload, DummyRequest(), db=session, p=principal)
        assert resp["run_id"]
        run = session.get(Run, resp["run_id"])
        assert run is not None
        doc_ids = {doc.id for doc in run.documents}
        assert "doc-1" in doc_ids
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
