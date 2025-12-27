import hashlib

import pytest

import app.api.routes.chat as chat
from app.api.routes.chat import (
    AskPayload,
    attach_debug_meta_to_detail,
    build_debug_meta,
    build_error_payload,
    contains_cjk,
    get_bearer_token,
    query_class,
    should_include_retrieval_debug,
    should_use_fts,
    should_use_trgm,
)
from app.core.authz import Principal, is_admin
from app.main import normalize_http_exception_detail


class DummyRequest:
    def __init__(self, authorization: str | None):
        self.headers = {}
        if authorization is not None:
            self.headers["authorization"] = authorization

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
    assert chat.is_admin_debug(principal, DummyRequest(None), is_admin_user=False) is False

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
    assert chat.is_admin_debug(admin_principal, req_no_hash, is_admin_user=True) is False
    # matching token should pass even without admin sub
    req_allowed = DummyRequest(f"Bearer {token}")
    user_principal = Principal(sub="user", permissions=set())
    assert chat.is_admin_debug(user_principal, req_allowed, is_admin_user=False) is True

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
    assert meta["fts_skipped"] is False
    assert meta["used_trgm"] is True
    assert meta["auth_mode_dev"] is False
    assert meta["auth_header_present"] is True
    assert meta["bearer_token_present"] is True

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

@pytest.mark.parametrize(
    "payload_debug,flag,is_admin_debug,expected",
    [
        (True, True, False, False),   # debug request but no admin-debug
        (False, True, True, False),   # admin-debug without payload flag
        (True, False, True, False),   # disabled feature flag
        (True, True, True, True),     # only valid combination
    ],
)
def test_retrieval_debug_requires_all_gates(monkeypatch, payload_debug, flag, is_admin_debug, expected):
    monkeypatch.setattr(chat, "ENABLE_RETRIEVAL_DEBUG", flag)
    assert should_include_retrieval_debug(payload_debug, is_admin_debug=is_admin_debug) is expected
