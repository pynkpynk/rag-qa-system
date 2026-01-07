from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
try:  # pragma: no cover - import shim for backend/ root runs
    from tests.test_eval_smoke_cases import (  # type: ignore  # noqa: I252
        _dev_headers as _smoke_headers,
    )
    from tests.test_eval_smoke_cases import smoke_document  # type: ignore # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    from backend.tests.test_eval_smoke_cases import (  # noqa: I252
        _dev_headers as _smoke_headers,
    )
    from backend.tests.test_eval_smoke_cases import smoke_document  # noqa: F401

pytestmark = pytest.mark.usefixtures("force_dev_auth")

client = TestClient(app)

CASES_PATH = Path(__file__).resolve().parent / "fixtures" / "search_eval_cases.json"
CASES = json.loads(CASES_PATH.read_text())


@pytest.fixture(autouse=True)
def _search_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_OFFLINE", "1")
    monkeypatch.setenv("ENABLE_TRGM", "1")
    monkeypatch.setenv("SEARCH_TRGM_ENABLED", "1")
    yield


def _format_hits(hits: list[dict]) -> str:
    parts = []
    for hit in hits:
        preview = (hit.get("text") or "").replace("\n", " ")[:120]
        parts.append(
            f"{hit.get('document_id')}#p{hit.get('page')} idx{hit.get('chunk_index')}: {preview}"
        )
    return "\n".join(parts)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_search_regression_eval(case: dict, smoke_document: str):
    headers = _smoke_headers()
    payload = {
        "q": case["query"],
        "mode": case.get("mode", "selected_docs"),
        "limit": case.get("limit", 5),
        "debug": False,
    }
    if payload["mode"] == "selected_docs":
        payload["document_ids"] = [smoke_document]
    resp = client.post("/api/search", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    hits = body.get("hits") or []
    assert hits, f"{case['name']}: expected hits but got none"

    expect = case.get("expected", {})
    contains = [s.lower() for s in expect.get("contains", [])]
    matched = False
    failure_summary = _format_hits(hits)

    for hit in hits:
        text_lower = (hit.get("text") or "").lower()
        if all(sub in text_lower for sub in contains):
            if expect.get("page") is not None:
                assert hit.get("page") == expect["page"], (
                    f"{case['name']}: expected page {expect['page']} but got {hit.get('page')}"
                )
            matched = True
            break

    assert matched, (
        f"{case['name']}: no hit contained substrings {contains}\n"
        f"Top hits:\n{failure_summary}"
    )
