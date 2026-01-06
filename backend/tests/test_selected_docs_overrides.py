from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
SMOKE_PDF = Path(__file__).resolve().parent / "fixtures" / "ragqa_smoke.pdf"


def _dev_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer dev-token",
        "x-dev-sub": "dev|override",
    }


def _upload_smoke() -> str:
    headers = _dev_headers()
    with SMOKE_PDF.open("rb") as handle:
        resp = client.post(
            "/api/docs/upload",
            headers=headers,
            files={"file": ("ragqa_smoke.pdf", handle, "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["document_id"]


def test_selected_docs_capital_has_no_contradiction():
    doc_id = _upload_smoke()
    payload = {
        "mode": "selected_docs",
        "document_ids": [doc_id],
        "question": "What city does the smoke document name as the capital of France?",
    }
    resp = client.post("/api/chat/ask", headers=_dev_headers(), json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    answer = (body.get("answer") or "").lower()
    assert "capital of france is paris" in answer
    assert "quality answers require precise sources" not in answer
    citations = body.get("citations") or []
    assert any(
        (cite.get("filename") == "ragqa_smoke.pdf")
        and (int(cite.get("page") or 0) == 1)
        for cite in citations
    ), citations


def test_selected_docs_quality_has_expected_citation():
    doc_id = _upload_smoke()
    payload = {
        "mode": "selected_docs",
        "document_ids": [doc_id],
        "question": "According to the smoke PDF, what does it say about quality answers?",
    }
    resp = client.post("/api/chat/ask", headers=_dev_headers(), json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    answer = (body.get("answer") or "").lower()
    assert "quality answers require precise sources" in answer
    assert "i don't know" not in answer
    assert "does not" not in answer
    assert "capital of france" not in answer
    citations = body.get("citations") or []
    assert any(
        (cite.get("filename") == "ragqa_smoke.pdf")
        and (int(cite.get("page") or 0) == 2)
        for cite in citations
    ), citations
