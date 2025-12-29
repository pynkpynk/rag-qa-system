from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _ensure_jose_stub() -> None:
    if "jose" in sys.modules:
        return

    jose_mod = ModuleType("jose")
    jwt_mod = ModuleType("jose.jwt")

    def _unsupported(*args, **kwargs):
        raise RuntimeError("JWT operations unavailable in smoke test stub")

    jwt_mod.get_unverified_header = _unsupported
    jwt_mod.decode = _unsupported
    jwt_mod.encode = _unsupported

    exceptions_mod = ModuleType("jose.exceptions")

    class JWTError(Exception):
        pass

    exceptions_mod.JWTError = JWTError

    jose_mod.jwt = jwt_mod

    sys.modules["jose"] = jose_mod
    sys.modules["jose.jwt"] = jwt_mod
    sys.modules["jose.exceptions"] = exceptions_mod


_ensure_jose_stub()

os.environ.setdefault("OPENAI_API_KEY", "dummy")
os.environ.setdefault("DATABASE_URL", "sqlite:///smoke.db")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:3000")

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


class Case(NamedTuple):
    name: str
    payload_debug: bool
    flag: bool
    is_admin_debug: bool
    expected: bool


CASES = [
    Case("non_admin_debug_true_flag_true", True, True, False, False),
    Case("admin_debug_false_flag_true", False, True, True, False),
    Case("admin_debug_true_flag_false", True, False, True, False),
    Case("admin_debug_true_flag_true", True, True, True, True),
]


def run_case(case: Case) -> None:
    original_flag = chat.ENABLE_RETRIEVAL_DEBUG
    chat.ENABLE_RETRIEVAL_DEBUG = case.flag
    try:
        result = should_include_retrieval_debug(case.payload_debug, is_admin_debug=case.is_admin_debug)
    finally:
        chat.ENABLE_RETRIEVAL_DEBUG = original_flag

    if result is not case.expected:
        raise AssertionError(f"{case.name}: expected {case.expected}, got {result}")


def _assert_language_helpers() -> None:
    if not contains_cjk("テスト"):
        raise AssertionError("contains_cjk should be True for Japanese text")
    if contains_cjk("test"):
        raise AssertionError("contains_cjk should be False for ASCII text")
    if query_class("テスト") != "cjk":
        raise AssertionError("query_class should classify Japanese text as cjk")
    if query_class("test") != "latin":
        raise AssertionError("query_class should classify ASCII text as latin")
    if should_use_fts("テスト"):
        raise AssertionError("should_use_fts should be False for CJK text")
    if not should_use_fts("test"):
        raise AssertionError("should_use_fts should be True for latin text")
    if not should_use_trgm("テスト", trgm_available=True):
        raise AssertionError("should_use_trgm should be True for CJK text when enabled")
    original_trgm = chat.ENABLE_TRGM
    chat.ENABLE_TRGM = False
    try:
        if should_use_trgm("テスト", trgm_available=True):
            raise AssertionError("should_use_trgm should honor ENABLE_TRGM flag")
    finally:
        chat.ENABLE_TRGM = original_trgm


def _assert_payload_debug_flag() -> None:
    payload = AskPayload.model_validate({"question": "Q", "debug": True})
    if not payload.debug:
        raise AssertionError("AskPayload should keep debug=True from payload")


def _assert_debug_meta_helpers() -> None:
    meta_non_admin = build_debug_meta(
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
    if meta_non_admin is None or meta_non_admin["is_admin"]:
        raise AssertionError("Non-admin debug_meta should reflect is_admin=False")
    if meta_non_admin["include_debug"]:
        raise AssertionError("Non-admin debug_meta should show include_debug=False")
    if not meta_non_admin["fts_skipped"]:
        raise AssertionError("CJK debug_meta should note fts_skipped=True")

    meta_admin = build_debug_meta(
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
    if meta_admin is None or not meta_admin["include_debug"]:
        raise AssertionError("Admin debug_meta should exist with include_debug=True")
    if not meta_admin["admin_via_token_hash"]:
        raise AssertionError("Admin debug_meta should reflect token hash when provided")

    if build_debug_meta(
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
        bearer_token_present=False,
        trgm_enabled=True,
        trgm_available=True,
        used_trgm=False,
        used_fts=True,
        fts_skipped=False,
    ):
        raise AssertionError("debug_meta should be None when feature flag disabled")


def _assert_admin_debug_token_hash() -> None:
    token = "smoke_admin_token"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    original_hashes = chat._ADMIN_DEBUG_TOKEN_HASHES
    chat._ADMIN_DEBUG_TOKEN_HASHES = {digest}
    try:
        req = DummyRequest(f"Bearer {token}")
        principal = Principal(sub="user", permissions=set())
        if get_bearer_token(req) != token:
            raise AssertionError("get_bearer_token failed in smoke test")
        if not chat.admin_debug_via_token(req):
            raise AssertionError("Token allowlist should grant admin-debug access")
        if not chat.is_admin_debug(principal, req):
            raise AssertionError("is_admin_debug should consider token allowlist")
        meta = build_debug_meta(
            feature_flag_enabled=True,
            payload_debug=True,
            is_admin=False,
            is_admin_debug=True,
            auth_mode_dev=False,
            admin_via_sub=False,
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
        if meta is None or not meta["is_admin_debug"]:
            raise AssertionError("debug_meta should capture admin-debug=True")
    finally:
        chat._ADMIN_DEBUG_TOKEN_HASHES = original_hashes

def _assert_token_hash_requirement() -> None:
    original_flag = chat.RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH
    original_hashes = chat._ADMIN_DEBUG_TOKEN_HASHES
    token = "requirement_token"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    chat.RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH = True
    chat._ADMIN_DEBUG_TOKEN_HASHES = {digest}
    try:
        admin_principal = Principal(sub="admin-user", permissions=set())
        if chat.is_admin_debug(admin_principal, DummyRequest("Bearer other"), is_admin_user=True):
            raise AssertionError("Token hash requirement should block admin-sub without allowlist")
        allowed_req = DummyRequest(f"Bearer {token}")
        user_principal = Principal(sub="user", permissions=set())
        if not chat.is_admin_debug(user_principal, allowed_req, is_admin_user=False):
            raise AssertionError("Token hash requirement should allow allowlisted token")
    finally:
        chat.RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH = original_flag
        chat._ADMIN_DEBUG_TOKEN_HASHES = original_hashes

def _assert_dev_mode_admin_behavior() -> None:
    os.environ["AUTH_MODE"] = "dev"
    os.environ["AUTH_DISABLED"] = "0"
    os.environ["DEV_ADMIN_SUBS"] = ""
    principal = Principal(sub="dev|local", permissions=set())
    if is_admin(principal):
        raise AssertionError("DEV_ADMIN_SUBS should be empty by default (non-admin)")
    os.environ["DEV_ADMIN_SUBS"] = "dev|local"
    if not is_admin(principal):
        raise AssertionError("DEV_ADMIN_SUBS should grant admin status when matching")

def _assert_auth_header_flags() -> None:
    base_kwargs = dict(
        feature_flag_enabled=True,
        payload_debug=True,
        is_admin=False,
        is_admin_debug=False,
        auth_mode_dev=True,
        admin_via_sub=False,
        admin_via_token_hash=False,
        include_debug=False,
        is_cjk=False,
        trgm_enabled=True,
        trgm_available=True,
        used_trgm=False,
        used_fts=False,
        fts_skipped=False,
    )
    meta_missing = build_debug_meta(
        **base_kwargs,
        auth_header_present=False,
        bearer_token_present=False,
    )
    if meta_missing is None or meta_missing["auth_header_present"]:
        raise AssertionError("Missing Authorization header should be reflected in debug_meta")
    meta_empty = build_debug_meta(
        **base_kwargs,
        auth_header_present=True,
        bearer_token_present=False,
    )
    if meta_empty is None or meta_empty["bearer_token_present"]:
        raise AssertionError("Empty bearer token should set bearer_token_present=False")

def _assert_empty_bearer_never_admin() -> None:
    principal = Principal(sub="user", permissions=set())
    if chat.is_admin_debug(principal, DummyRequest(None), is_admin_user=False):
        raise AssertionError("Missing Authorization header must not unlock admin-debug")
    digest = hashlib.sha256(b"").hexdigest()
    original_hashes = chat._ADMIN_DEBUG_TOKEN_HASHES
    chat._ADMIN_DEBUG_TOKEN_HASHES = {digest}
    try:
        req = DummyRequest("Bearer ")
        if chat.admin_debug_via_token(req):
            raise AssertionError("Empty bearer token must not match allowlist")
        if chat.is_admin_debug(principal, req, is_admin_user=False):
            raise AssertionError("Empty bearer token must not grant admin-debug")
    finally:
        chat._ADMIN_DEBUG_TOKEN_HASHES = original_hashes

def _assert_error_payload_helpers() -> None:
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
    payload = build_error_payload("example", "oops", debug_meta=meta)
    if payload["error"]["code"] != "example":
        raise AssertionError("build_error_payload must keep error code")
    if payload.get("debug_meta") != meta:
        raise AssertionError("build_error_payload must attach debug_meta")
    wrapped = attach_debug_meta_to_detail("msg", meta)
    if wrapped.get("debug_meta") != meta:
        raise AssertionError("attach_debug_meta_to_detail must wrap string detail")
    if "retrieval_debug" in payload:
        raise AssertionError("Error payload must never contain retrieval_debug")
    shaped = normalize_http_exception_detail(payload)
    if shaped is not payload:
        raise AssertionError("normalize_http_exception_detail should return structured payload")
    shaped_simple = normalize_http_exception_detail({"code": "GENERIC", "message": "x"})
    if shaped_simple != {"error": {"code": "GENERIC", "message": "x"}}:
        raise AssertionError("normalize_http_exception_detail should wrap code/message dicts")
    if normalize_http_exception_detail("bad") is not None:
        raise AssertionError("normalize_http_exception_detail should ignore non-dicts")


def main() -> int:
    os.environ["ADMIN_SUBS"] = "smoke-admin"
    for case in CASES:
        run_case(case)
    _assert_language_helpers()
    _assert_payload_debug_flag()
    _assert_debug_meta_helpers()
    _assert_token_hash_requirement()
    _assert_admin_debug_token_hash()
    _assert_dev_mode_admin_behavior()
    _assert_auth_header_flags()
    _assert_empty_bearer_never_admin()
    _assert_error_payload_helpers()
    return 0


if __name__ == "__main__":
    sys.exit(main())
