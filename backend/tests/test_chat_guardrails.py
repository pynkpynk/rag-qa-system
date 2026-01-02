import hashlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.routes.chat as chat
from app.api.routes.chat import (
    AskPayload,
    attach_debug_meta_to_detail,
    build_debug_meta,
    build_error_payload,
    build_retrieval_debug_payload,
    contains_cjk,
    get_bearer_token,
    query_class,
    should_include_retrieval_debug,
    should_use_fts,
    should_use_trgm,
)
from app.core.output_contract import sanitize_nonfinite_floats
from app.core.authz import Principal, is_admin
from app.main import normalize_http_exception_detail
from app.core.run_access import ensure_run_access
import app.core.run_access as run_access


class DummyRequest:
    def __init__(self, authorization: str | None):
        self.headers = {}
        if authorization is not None:
            self.headers["authorization"] = authorization
        self.state = SimpleNamespace(request_id=None)


class DummyResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class DummyDB:
    def __init__(self, results):
        self.results = list(results)

    def execute(self, sql, params):
        if not self.results:
            raise AssertionError("Unexpected SQL execute call")
        return self.results.pop(0)


def test_dev_mode_defaults_to_non_admin(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("AUTH_DISABLED", "0")
    monkeypatch.delenv("DEV_ADMIN_SUBS", raising=False)
    principal = Principal(sub="dev|local", permissions=set())
    assert is_admin(principal) is False


def test_dev_mode_admin_allowlist(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("AUTH_DISABLED", "0")
    monkeypatch.setenv("DEV_ADMIN_SUBS", "dev|local")
    principal = Principal(sub="dev|local", permissions=set())
    assert is_admin(principal) is True


def test_payload_accepts_message_alias_and_strips():
    p = AskPayload(message="  hello  ", k=6)
    assert p.question == "hello"


def test_payload_prefers_question_over_message():
    p = AskPayload(question="Q", message="M", k=6)
    assert p.question == "Q"


def test_payload_rejects_whitespace_only():
    with pytest.raises(Exception):
        AskPayload(question="   ", k=6)
    with pytest.raises(Exception):
        AskPayload(message="   ", k=6)


def test_payload_deduplicates_document_ids():
    p = AskPayload(question="Q", k=6, document_ids=[" doc1 ", "doc1", "", "doc2 "])
    assert p.document_ids == ["doc1", "doc2"]


def test_payload_disallows_run_and_doc_scope():
    with pytest.raises(Exception):
        AskPayload(question="Q", k=6, run_id="run-1", document_ids=["doc1"])


def test_cjk_detection():
    assert contains_cjk("日本語の質問です")
    assert query_class("日本語の質問です") == "cjk"
    assert query_class("hello world") == "latin"


def test_should_use_fts_policy():
    assert should_use_fts("hello world") is True
    assert should_use_fts("日本語の質問です") is False


def test_should_use_trgm_policy(monkeypatch):
    monkeypatch.setattr(chat, "ENABLE_TRGM", True)
    assert should_use_trgm("日本語の質問です", trgm_available=True) is True
    assert should_use_trgm("日", trgm_available=True) is False
    assert should_use_trgm("hello world", trgm_available=True) is False
    assert should_use_trgm("日本語の質問です", trgm_available=False) is False
    monkeypatch.setattr(chat, "ENABLE_TRGM", False)
    assert should_use_trgm("日本語の質問です", trgm_available=True) is False


def test_payload_keeps_debug_flag():
    p = AskPayload(question="Q", k=6, debug=True)
    assert p.debug is True


def test_get_bearer_token_parses_header():
    req = DummyRequest("Bearer token123")
    assert get_bearer_token(req) == "token123"
    assert get_bearer_token(DummyRequest("Basic abc")) is None
    assert get_bearer_token(DummyRequest(None)) is None
    assert get_bearer_token(DummyRequest("Bearer ")) is None
    assert get_bearer_token(DummyRequest("Bearer")) is None


def test_is_admin_debug_false_without_auth_header():
    principal = Principal(sub="user", permissions=set())
    assert (
        chat.is_admin_debug(principal, DummyRequest(None), is_admin_user=False) is False
    )


def test_is_admin_debug_false_for_empty_bearer_token(monkeypatch):
    digest = hashlib.sha256(b"").hexdigest()
    monkeypatch.setattr(chat, "_ADMIN_DEBUG_TOKEN_HASHES", {digest})
    principal = Principal(sub="user", permissions=set())
    req = DummyRequest("Bearer ")
    assert chat.admin_debug_via_token(req) is False
    assert chat.is_admin_debug(principal, req, is_admin_user=False) is False


def test_is_admin_debug_via_token_hash(monkeypatch):
    token = "dummy_admin_token"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    monkeypatch.setattr(chat, "_ADMIN_DEBUG_TOKEN_HASHES", {digest})
    req = DummyRequest(f"Bearer {token}")
    principal = Principal(sub="user", permissions=set())
    assert chat.admin_debug_via_token(req) is True
    assert chat.is_admin_debug(principal, req) is True


def test_is_admin_debug_requires_token_hash_when_flag_enabled(monkeypatch):
    token = "allowed_token"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    monkeypatch.setattr(chat, "_ADMIN_DEBUG_TOKEN_HASHES", {digest})
    monkeypatch.setattr(chat, "RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH", True)
    req_no_hash = DummyRequest("Bearer other")
    admin_principal = Principal(sub="admin-user", permissions=set())
    # admin via sub only should fail when token hash required
    assert (
        chat.is_admin_debug(admin_principal, req_no_hash, is_admin_user=True) is False
    )
    # matching token should pass even without admin sub
    req_allowed = DummyRequest(f"Bearer {token}")
    user_principal = Principal(sub="user", permissions=set())
    assert chat.is_admin_debug(user_principal, req_allowed, is_admin_user=False) is True


class FakeRunDB:
    def __init__(self, owners: dict[str, str | None]):
        self.owners = owners

    class _Result:
        def __init__(self, row):
            self._row = row

        def mappings(self):
            return self

        def first(self):
            return self._row

    def execute(self, sql, params):
        run_id = params["run_id"]
        owner = self.owners.get(run_id)
        if owner is None:
            return self._Result(None)
        return self._Result({"owner_sub": owner})


def test_ensure_run_access_blocks_other_user():
    db = FakeRunDB({"run-user-a": "user-a"})
    principal = Principal(sub="user-b", permissions=set())
    with pytest.raises(HTTPException) as exc:
        ensure_run_access(db, "run-user-a", principal)
    assert exc.value.status_code == 404


def test_ensure_run_access_allows_owner():
    db = FakeRunDB({"run-user-a": "user-a"})
    principal = Principal(sub="user-a", permissions=set())
    ensure_run_access(db, "run-user-a", principal)


def test_ensure_run_access_admin_allowed(monkeypatch):
    db = FakeRunDB({"run-admin": "admin"})
    principal = Principal(sub="admin", permissions={"admin"})
    monkeypatch.setattr(run_access, "is_admin", lambda _: True)
    ensure_run_access(db, "run-admin", principal)


def test_debug_meta_for_non_admin_debug_request():
    meta = build_debug_meta(
        feature_flag_enabled=True,
        payload_debug=True,
        is_admin=False,
        is_admin_debug=False,
        auth_mode_dev=True,
        admin_via_sub=False,
        admin_via_token_hash=False,
        include_debug=False,
        is_cjk=True,
        auth_header_present=False,
        bearer_token_present=False,
        trgm_enabled=True,
        trgm_available=True,
        used_trgm=False,
        used_fts=False,
        fts_skipped=True,
    )
    assert meta is not None
    assert meta["is_admin"] is False
    assert meta["is_admin_debug"] is False
    assert meta["include_debug"] is False
    assert meta["admin_via_token_hash"] is False
    assert meta["is_cjk"] is True
    assert meta["fts_skipped"] is True
    assert meta["used_fts"] is False
    assert meta["used_trgm"] is False
    assert meta["auth_mode_dev"] is True
    assert meta["auth_header_present"] is False
    assert meta["bearer_token_present"] is False


def test_debug_meta_for_admin_debug_request():
    meta = build_debug_meta(
        feature_flag_enabled=True,
        payload_debug=True,
        is_admin=True,
        is_admin_debug=True,
        auth_mode_dev=False,
        admin_via_sub=True,
        admin_via_token_hash=True,
        include_debug=True,
        is_cjk=False,
        auth_header_present=True,
        bearer_token_present=True,
        trgm_enabled=True,
        trgm_available=True,
        used_trgm=True,
        used_fts=True,
        fts_skipped=False,
    )
    assert meta is not None
    assert meta["is_admin"] is True
    assert meta["is_admin_debug"] is True
    assert meta["admin_via_token_hash"] is True
    assert meta["used_fts"] is True


def test_prod_env_forces_debug_off(monkeypatch):
    class DummyDB:
        def commit(self):
            return None

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("ALLOW_PROD_DEBUG", "0")
    monkeypatch.setenv("ENABLE_RETRIEVAL_DEBUG", "1")
    monkeypatch.setenv("ENABLE_TRGM", "0")
    monkeypatch.setenv("RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH", "0")
    monkeypatch.setattr(chat, "_TRGM_AVAILABLE_FLAG", None, raising=False)
    monkeypatch.setattr(chat, "is_admin", lambda _: True)
    monkeypatch.setattr(chat, "effective_auth_mode", lambda: "prod")
    monkeypatch.setattr(chat, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(chat, "_detect_trgm_available", lambda *_: False)

    def fake_fetch_chunks(
        db,
        qvec_lit,
        q_text,
        k,
        run_id,
        document_ids,
        p,
        question,
        trgm_available,
        admin_debug_hybrid,
    ):
        rows = [
            {
                "id": "chunk1",
                "document_id": "doc1",
                "filename": "doc.pdf",
                "page": 1,
                "chunk_index": 0,
                "text": "chunk text",
                "dist": 0.12,
            }
        ]
        debug = {
            "strategy": "vector_by_run_admin",
            "vec_count": 1,
            "merged_count": 1,
            "used_trgm": False,
            "fts_skipped": True,
            "trgm_available": trgm_available,
        }
        return rows, debug

    events: list[dict] = []

    monkeypatch.setattr(chat, "fetch_chunks", fake_fetch_chunks)
    monkeypatch.setattr(
        chat, "answer_with_contract", lambda *args, **kwargs: ("answer", ["S1"])
    )
    monkeypatch.setattr(
        chat, "_emit_audit_event", lambda **kwargs: events.append(kwargs)
    )

    payload = AskPayload(question="Explain prod behavior", k=2, debug=True)
    request = DummyRequest(None)
    request.state.request_id = "prod-req"
    principal = Principal(sub="prod|admin", permissions={"read:docs"})

    resp = chat.ask(payload, request, db=DummyDB(), p=principal)
    assert "retrieval_debug" not in resp
    assert "debug_meta" not in resp
    assert events, "audit events should be emitted in prod"
    for ev in events:
        assert ev["retrieval_debug_included"] is False
        assert ev["debug_meta_included"] is False
        assert ev["debug_effective"] is False
        assert ev["status"] in {"success", "error"}
        assert "fts_skipped" not in ev
        assert "used_trgm" not in ev
        assert "trgm_available" not in ev


def test_debug_meta_disabled_when_auth_mode_not_dev(monkeypatch):
    class DummyDB:
        def commit(self):
            return None

    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("ALLOW_PROD_DEBUG", "1")
    monkeypatch.setattr(chat, "effective_auth_mode", lambda: "auth0")
    monkeypatch.setattr(chat, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(chat, "fetch_chunks", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(
        chat, "answer_with_contract", lambda *args, **kwargs: ("answer", [])
    )

    payload = AskPayload(question="Explain dev auth", k=2, debug=True)
    request = DummyRequest(None)
    principal = Principal(sub="user|auth0", permissions={"read:docs"})

    resp = chat.ask(payload, request, db=DummyDB(), p=principal)
    assert "debug_meta" not in resp
    assert "retrieval_debug" not in resp


def test_chat_ask_blocks_run_not_owned(monkeypatch):
    class RequestStub:
        def __init__(self):
            self.headers = {}
            self.state = SimpleNamespace(request_id="req-block")

    class DummyDB:
        def commit(self):
            return None

    payload = AskPayload(question="Need info", k=2, run_id="run-other", debug=True)
    principal = Principal(sub="user-a", permissions={"read:docs"})
    request = RequestStub()

    def deny_run(*args, **kwargs):
        raise HTTPException(status_code=404, detail="run not found")

    monkeypatch.setattr(chat, "ensure_run_access", deny_run)

    with pytest.raises(HTTPException) as exc:
        chat.ask(payload, request, db=DummyDB(), p=principal)
    assert exc.value.status_code == 404


def test_debug_meta_absent_when_payload_debug_false():
    meta = build_debug_meta(
        feature_flag_enabled=True,
        payload_debug=False,
        is_admin=True,
        is_admin_debug=True,
        auth_mode_dev=False,
        admin_via_sub=True,
        admin_via_token_hash=False,
        include_debug=True,
        is_cjk=False,
        auth_header_present=True,
        bearer_token_present=True,
        trgm_enabled=True,
        trgm_available=True,
        used_trgm=False,
        used_fts=True,
        fts_skipped=False,
    )
    assert meta is None


def test_debug_meta_tracks_header_without_token():
    meta = build_debug_meta(
        feature_flag_enabled=True,
        payload_debug=True,
        is_admin=False,
        is_admin_debug=False,
        auth_mode_dev=True,
        admin_via_sub=False,
        admin_via_token_hash=False,
        include_debug=False,
        is_cjk=False,
        auth_header_present=True,
        bearer_token_present=False,
        trgm_enabled=True,
        trgm_available=True,
        used_trgm=False,
        used_fts=False,
        fts_skipped=False,
    )
    assert meta is not None
    assert meta["auth_header_present"] is True
    assert meta["bearer_token_present"] is False


def test_debug_meta_absent_when_feature_flag_disabled():
    meta = build_debug_meta(
        feature_flag_enabled=False,
        payload_debug=True,
        is_admin=True,
        is_admin_debug=True,
        auth_mode_dev=False,
        admin_via_sub=True,
        admin_via_token_hash=False,
        include_debug=True,
        is_cjk=False,
        auth_header_present=True,
        bearer_token_present=True,
        trgm_enabled=True,
        trgm_available=True,
        used_trgm=False,
        used_fts=True,
        fts_skipped=False,
    )
    assert meta is None


def test_build_debug_meta_returns_expected_keys():
    meta = build_debug_meta(
        feature_flag_enabled=True,
        payload_debug=True,
        is_admin=True,
        is_admin_debug=True,
        auth_mode_dev=False,
        admin_via_sub=True,
        admin_via_token_hash=True,
        include_debug=True,
        is_cjk=False,
        auth_header_present=True,
        bearer_token_present=True,
        trgm_enabled=True,
        trgm_available=True,
        used_trgm=True,
        used_fts=True,
        fts_skipped=False,
    )
    expected_keys = {
        "feature_flag_enabled",
        "payload_debug",
        "is_admin",
        "is_admin_debug",
        "auth_mode_dev",
        "admin_via_sub",
        "admin_via_token_hash",
        "include_debug",
        "is_cjk",
        "auth_header_present",
        "bearer_token_present",
        "trgm_enabled",
        "trgm_available",
        "used_trgm",
        "used_fts",
        "fts_skipped",
    }
    assert set(meta.keys()) == expected_keys


def test_build_error_payload_includes_debug_meta():
    meta = build_debug_meta(
        feature_flag_enabled=True,
        payload_debug=True,
        is_admin=False,
        is_admin_debug=False,
        auth_mode_dev=True,
        admin_via_sub=False,
        admin_via_token_hash=False,
        include_debug=False,
        is_cjk=False,
        auth_header_present=False,
        bearer_token_present=False,
        trgm_enabled=True,
        trgm_available=False,
        used_trgm=False,
        used_fts=False,
        fts_skipped=False,
    )
    payload = build_error_payload("run_not_found", "run not found", debug_meta=meta)
    assert payload["error"]["code"] == "run_not_found"
    assert payload["error"]["message"] == "run not found"
    assert payload["debug_meta"] == meta
    assert "retrieval_debug" not in payload


def test_build_error_payload_skips_debug_meta_when_missing():
    payload = build_error_payload("generic_query", "msg", debug_meta=None)
    assert payload["error"]["code"] == "generic_query"
    assert "debug_meta" not in payload


def test_attach_debug_meta_wraps_string_detail():
    meta = build_debug_meta(
        feature_flag_enabled=True,
        payload_debug=True,
        is_admin=False,
        is_admin_debug=False,
        auth_mode_dev=True,
        admin_via_sub=False,
        admin_via_token_hash=False,
        include_debug=False,
        is_cjk=False,
        auth_header_present=False,
        bearer_token_present=False,
        trgm_enabled=True,
        trgm_available=False,
        used_trgm=False,
        used_fts=False,
        fts_skipped=False,
    )
    detail = attach_debug_meta_to_detail("bad", meta)
    assert detail["error"]["message"] == "bad"
    assert detail["debug_meta"] == meta
    shaped = normalize_http_exception_detail(detail)
    assert shaped is detail


def test_normalize_http_exception_detail_from_object():
    meta = build_debug_meta(
        feature_flag_enabled=True,
        payload_debug=True,
        is_admin=False,
        is_admin_debug=False,
        auth_mode_dev=True,
        admin_via_sub=False,
        admin_via_token_hash=False,
        include_debug=False,
        is_cjk=False,
        auth_header_present=False,
        bearer_token_present=False,
        trgm_enabled=True,
        trgm_available=True,
        used_trgm=False,
        used_fts=False,
        fts_skipped=False,
    )
    detail = {
        "error": {"code": "GENERIC", "message": "msg"},
        "debug_meta": meta,
    }
    shaped = normalize_http_exception_detail(detail)
    assert shaped is detail
    assert shaped["debug_meta"] == meta


def test_normalize_http_exception_detail_from_code_message():
    shaped = normalize_http_exception_detail({"code": "GENERIC", "message": "msg"})
    assert shaped == {"error": {"code": "GENERIC", "message": "msg"}}


def test_normalize_http_exception_detail_rejects_string():
    assert normalize_http_exception_detail("bad") is None


def test_sanitize_nonfinite_floats_records_paths():
    payload = {
        "a": float("nan"),
        "b": [0.1, float("inf"), {"c": float("-inf")}],
        "nested": {"d": (float("nan"), 1)},
    }
    sanitized, paths = sanitize_nonfinite_floats(payload)
    assert sanitized["a"] is None
    assert sanitized["b"][1] is None
    assert sanitized["b"][2]["c"] is None
    assert sanitized["nested"]["d"][0] is None
    assert set(paths) == {"a", "b[1]", "b[2].c", "nested.d[0]"}


def test_sanitize_allows_json_serialization():
    import json

    payload = {
        "retrieval_debug": {"vec_top5": [{"score": float("nan")}]},
        "debug_meta": {"payload_debug": True},
    }
    sanitized, paths = sanitize_nonfinite_floats(payload)
    assert paths == ["retrieval_debug.vec_top5[0].score"]
    json.dumps(sanitized, allow_nan=False)


def test_retrieval_debug_payload_sets_count_from_merged():
    payload = build_retrieval_debug_payload({"merged_count": 3, "vec_count": 5})
    assert payload["count"] == 3


def test_retrieval_debug_payload_sets_count_from_lists():
    payload = build_retrieval_debug_payload({"vec_top5": [{"rank": 1}, {"rank": 2}]})
    assert payload["count"] == 2


def test_admin_debug_strategy_default_firstk(monkeypatch):
    monkeypatch.setattr(chat, "is_admin", lambda p: True)
    monkeypatch.setattr(chat, "_is_summary_question", lambda q: True)
    db = DummyDB(
        [
            DummyResult([{"cnt": 1}]),
            DummyResult(
                [
                    {
                        "id": "chunk1",
                        "document_id": "doc1",
                        "filename": "en",
                        "page": 1,
                        "chunk_index": 0,
                        "text": "t",
                        "dist": 0.1,
                    }
                ]
            ),
        ]
    )
    principal = Principal(sub="admin", permissions=set())
    rows, debug = chat.fetch_chunks(
        db,
        qvec_lit="[0]",
        q_text="summary テスト",
        k=1,
        run_id="run1",
        document_ids=None,
        p=principal,
        question="summary テスト",
        trgm_available=True,
        admin_debug_hybrid=False,
    )
    assert len(rows) == 1
    assert debug["strategy"] == "firstk_by_run_admin"
    assert debug["used_trgm"] is False


def test_admin_debug_strategy_hybrid_overrides_summary(monkeypatch):
    monkeypatch.setattr(chat, "is_admin", lambda p: True)
    monkeypatch.setattr(chat, "_is_summary_question", lambda q: True)
    db = DummyDB(
        [
            DummyResult([{"cnt": 1}]),
            DummyResult(
                [
                    {
                        "id": "vec1",
                        "document_id": "doc1",
                        "filename": "en",
                        "page": 1,
                        "chunk_index": 0,
                        "text": "vec",
                        "dist": 0.1,
                    }
                ]
            ),
            DummyResult(
                [
                    {
                        "id": "trgm1",
                        "document_id": "doc2",
                        "filename": "ja",
                        "page": 2,
                        "chunk_index": 1,
                        "text": "ja",
                        "dist": None,
                    }
                ]
            ),
        ]
    )
    principal = Principal(sub="admin", permissions=set())
    rows, debug = chat.fetch_chunks(
        db,
        qvec_lit="[0]",
        q_text="要点 テスト",
        k=1,
        run_id="run1",
        document_ids=None,
        p=principal,
        question="要点 テスト",
        trgm_available=True,
        admin_debug_hybrid=True,
    )
    assert debug["strategy"] == "hybrid_rrf_by_run_admin"
    assert debug["used_trgm"] is True


@pytest.mark.parametrize(
    "payload_debug,flag,is_admin_debug,expected",
    [
        (True, True, False, False),  # debug request but no admin-debug
        (False, True, True, False),  # admin-debug without payload flag
        (True, False, True, False),  # disabled feature flag
        (True, True, True, True),  # only valid combination
    ],
)
def test_retrieval_debug_requires_all_gates(
    monkeypatch, payload_debug, flag, is_admin_debug, expected
):
    monkeypatch.setattr(chat, "ENABLE_RETRIEVAL_DEBUG", flag)
    assert (
        should_include_retrieval_debug(payload_debug, is_admin_debug=is_admin_debug)
        is expected
    )
