import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

import app.api.routes.chat as chat
from app.api.routes.chat import AskPayload
from app.core.authz import Principal


CASES_PATH = Path(__file__).resolve().parents[0] / "fixtures" / "eval_cases.json"
CASES = json.loads(CASES_PATH.read_text())


class DummyRequest:
    def __init__(self, case_name: str, authorization: str | None):
        header_dict = {"x-request-id": case_name}
        if authorization:
            header_dict["authorization"] = authorization
        self.headers = Headers(header_dict)
        self.state = SimpleNamespace(request_id=case_name)


class DummyResult:
    def __init__(self, first=None, rows=None):
        self._first = first
        self._rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self._first or (self._rows[0] if self._rows else None)

    def all(self):
        return self._rows


class DummyDB:
    def __init__(self, case: dict):
        run_cfg = case.get("run")
        if run_cfg and run_cfg.get("exists"):
            self._run = SimpleNamespace(
                id=run_cfg.get("id", "run-case"),
                config=run_cfg.get("config", {"model": "stub-model", "gen": {}}),
                t0=None,
                t1=None,
                t2=None,
                t3=None,
            )
        else:
            self._run = None
        exec_plan = case.get("db_exec", [])
        self._exec_plan = [DummyResult(**entry) for entry in exec_plan]

    def get(self, model, pk):
        return self._run

    def commit(self):
        return None

    def close(self):
        return None

    def execute(self, sql, params):
        if not self._exec_plan:
            raise AssertionError("Unexpected SQL execute during eval regression test")
        return self._exec_plan.pop(0)


def _load_rows(case_fetch: dict | None) -> list[dict]:
    if not case_fetch:
        return []
    rows = []
    for row in case_fetch.get("rows", []):
        rows.append(dict(row))
    return rows


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_eval_cases(case, monkeypatch):
    # base env defaults
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("ALLOW_PROD_DEBUG", "1")
    monkeypatch.setenv("ENABLE_RETRIEVAL_DEBUG", "1")
    monkeypatch.setenv("ENABLE_HYBRID", "1")
    monkeypatch.setenv("ENABLE_TRGM", "1")
    monkeypatch.setenv("TRGM_K", "30")
    monkeypatch.setenv(
        "RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH",
        case.get("env", {}).get("RETRIEVAL_DEBUG_REQUIRE_TOKEN_HASH", "0"),
    )
    # case-specific env overrides
    for key, value in case.get("env", {}).items():
        monkeypatch.setenv(key, str(value))
    # ensure unused allowlists don't leak
    monkeypatch.delenv("ADMIN_DEBUG_TOKEN_SHA256_LIST", raising=False)

    if "force_summary" in case:
        monkeypatch.setattr(
            chat, "_is_summary_question", lambda q: case["force_summary"]
        )

    monkeypatch.setattr(chat, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(chat, "ensure_run_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        chat,
        "_detect_trgm_available",
        lambda *_: case.get("trgm_available", True),
    )

    fetch_data = case.get("fetch")

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
        **_kwargs,
    ):
        if not fetch_data:
            return [], None
        rows = _load_rows(fetch_data)
        debug = fetch_data.get("debug")
        return rows, (dict(debug) if debug else None)

    monkeypatch.setattr(chat, "fetch_chunks", fake_fetch_chunks)

    answer_cfg = case.get("answer", {"text": "stub-answer", "citations": []})
    monkeypatch.setattr(
        chat,
        "answer_with_contract",
        lambda *args, **kwargs: (
            answer_cfg.get("text", "answer"),
            answer_cfg.get("citations", []),
        ),
    )

    payload = AskPayload.model_validate(case["payload"])
    request = DummyRequest(case["name"], case.get("authorization"))
    principal = Principal(
        sub=case.get("principal_sub", "dev|user"), permissions={"read:docs"}
    )
    db = DummyDB(case)

    try:
        response = chat.ask(payload, request, db=db, p=principal)
        status = 200
        body = response
    except HTTPException as exc:
        status = exc.status_code
        detail = exc.detail
        body = detail if isinstance(detail, dict) else {"error": {"code": str(detail)}}

    expect = case["expect"]
    assert status == expect["status"], (
        f"{case['name']}: status {status} != {expect['status']}"
    )

    json.dumps(body, allow_nan=False)

    if status >= 400:
        assert body["error"]["code"] == expect["error_code"], (
            f"{case['name']}: error code mismatch"
        )
        return

    rd_expect = expect.get("retrieval_debug")
    if rd_expect:
        present = rd_expect.get("present", True)
        if present:
            assert "retrieval_debug" in body, (
                f"{case['name']}: expected retrieval_debug"
            )
            rd = body["retrieval_debug"]
            if "strategy" in rd_expect:
                assert rd.get("strategy") == rd_expect["strategy"], (
                    f"{case['name']}: strategy mismatch"
                )
            if "min_count" in rd_expect:
                assert isinstance(rd.get("count"), int), (
                    f"{case['name']}: count missing or not int"
                )
                assert rd["count"] >= rd_expect["min_count"], (
                    f"{case['name']}: count too low"
                )
            if "used_trgm" in rd_expect:
                assert rd.get("used_trgm") == rd_expect["used_trgm"], (
                    f"{case['name']}: used_trgm mismatch"
                )
        else:
            if payload.debug:
                assert "retrieval_debug" in body, (
                    f"{case['name']}: retrieval_debug key should be present"
                )
                assert body["retrieval_debug"] == {}, (
                    f"{case['name']}: expected empty retrieval_debug object"
                )
            else:
                assert "retrieval_debug" not in body, (
                    f"{case['name']}: retrieval_debug should be absent"
                )
