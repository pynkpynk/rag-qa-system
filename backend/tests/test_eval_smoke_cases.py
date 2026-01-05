from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.main import app
from app.api.routes import chat as chat_module

pytestmark = pytest.mark.usefixtures("force_dev_auth")

client = TestClient(app)

def _load_cases() -> list[dict[str, object]]:
    cases_path = Path(__file__).resolve().parent / "e2e_eval_cases.json"
    if not cases_path.exists():
        raise AssertionError(
            "Missing backend/tests/e2e_eval_cases.json. Ensure it is committed to the repo."
        )
    return json.loads(cases_path.read_text())


CASES = _load_cases()
SMOKE_PDF = Path(__file__).resolve().parent / "fixtures" / "ragqa_smoke.pdf"


def _dev_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-token",
        "x-dev-sub": "dev|eval",
    }


@pytest.fixture(scope="module")
def smoke_document():
    headers = _dev_headers()
    with SMOKE_PDF.open("rb") as handle:
        resp = client.post(
            "/api/docs/upload",
            headers=headers,
            files={"file": ("ragqa_smoke.pdf", handle, "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    doc_id = payload["document_id"]
    assert doc_id
    detail = client.get(f"/api/docs/{doc_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["status"].startswith("indexed")

    db_url = os.environ.get("DATABASE_URL")
    assert db_url, "DATABASE_URL must be set for smoke tests"
    engine = _create_db_engine(db_url)
    ready = False
    timeout_s = 5.0
    poll_interval = 0.1
    deadline = time.time() + timeout_s
    diagnostics: dict[str, object] = {}
    with engine.connect() as conn:
        while time.time() < deadline:
            total = conn.execute(
                text(
                    "SELECT COUNT(*) FROM chunks WHERE document_id = :doc_id"
                ),
                {"doc_id": doc_id},
            ).scalar_one()
            max_page = conn.execute(
                text(
                    "SELECT COALESCE(MAX(page), 0) FROM chunks WHERE document_id = :doc_id"
                ),
                {"doc_id": doc_id},
            ).scalar_one()
            has_at = conn.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM chunks WHERE document_id = :doc_id AND POSITION('@' IN text) > 0)"
                ),
                {"doc_id": doc_id},
            ).scalar_one()
            if total > 0 and max_page >= 3 and has_at:
                ready = True
                break
            diagnostics = {"total": total, "max_page": max_page, "has_at": has_at}
            time.sleep(poll_interval)
        if not ready:
            page_counts = conn.execute(
                text(
                    "SELECT page, COUNT(*) AS cnt FROM chunks WHERE document_id = :doc_id GROUP BY page ORDER BY page"
                ),
                {"doc_id": doc_id},
            ).all()
            chunk_samples = conn.execute(
                text(
                    "SELECT page, chunk_index, SUBSTR(text, 1, 120) AS preview "
                    "FROM chunks WHERE document_id = :doc_id "
                    "ORDER BY page NULLS LAST, chunk_index ASC LIMIT 5"
                ),
                {"doc_id": doc_id},
            ).all()
            raise AssertionError(
                f"Document {doc_id} never became ready within {timeout_s}s. "
                f"Diagnostics={diagnostics}, page_counts={page_counts}, chunk_samples={chunk_samples}"
            )
    engine.dispose()

    yield doc_id
    if os.getenv("SKIP_SMOKE_TEARDOWN", "0") != "1":
        client.delete(f"/api/docs/{doc_id}", headers=headers)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_eval_smoke_cases(case, smoke_document):
    headers = _dev_headers()
    payload = {
        "mode": "selected_docs",
        "document_ids": [smoke_document],
        "question": case["question"],
    }
    resp = client.post("/api/chat/ask", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    citations = body.get("citations") or []
    expect = case["expect"]
    assert len(citations) >= expect.get("min_citations", 1), (
        f"{case['name']}: expected at least {expect.get('min_citations', 1)} citation(s)"
    )
    normalized_answer = (body.get("answer") or "").lower()
    expected_phrase = expect["answer_substring"].lower()
    assert expected_phrase in normalized_answer, (
        f"{case['name']}: answer missing '{expected_phrase}'\nActual: {body.get('answer')}"
    )
    expected_filename = expect["filename"]
    expected_page = expect["page"]
    assert any(
        cite.get("filename") == expected_filename and cite.get("page") == expected_page
        for cite in citations
    ), (
        f"{case['name']}: expected citation for {expected_filename} page {expected_page}"
    )


def test_support_email_selected_docs_without_trgm(monkeypatch, smoke_document):
    monkeypatch.setenv("ENABLE_TRGM", "0")
    monkeypatch.setattr(chat_module, "_TRGM_AVAILABLE_FLAG", None)
    headers = _dev_headers()
    payload = {
        "mode": "selected_docs",
        "document_ids": [smoke_document],
        "question": "Which support email is listed in the smoke PDF?",
    }
    resp = client.post("/api/chat/ask", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "support@ragqa.local" in (body.get("answer") or "")
    citations = body.get("citations") or []
    assert any(
        cite.get("page") == 3 and cite.get("filename") == "ragqa_smoke.pdf"
        for cite in citations
    )
def _create_db_engine(db_url: str):
    url = make_url(db_url)
    if url.drivername == "postgresql":
        drivername = None
        try:
            import psycopg  # type: ignore # noqa: F401

            drivername = "postgresql+psycopg"
        except ImportError:
            try:
                import psycopg2  # type: ignore # noqa: F401

                drivername = "postgresql+psycopg2"
            except ImportError as exc:  # noqa: PERF203
                raise AssertionError(
                    "psycopg (psycopg3) or psycopg2 must be installed for smoke readiness polling"
                ) from exc
        url = url.set(drivername=drivername)
    return create_engine(url)
