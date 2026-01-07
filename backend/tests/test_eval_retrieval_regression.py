from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.models import Chunk, Document
from app.db.session import SessionLocal
from app.main import app

pytestmark = pytest.mark.usefixtures("force_dev_auth")

client = TestClient(app)

CASES_PATH = Path(__file__).resolve().parent / "evals" / "retrieval_cases.jsonl"
CASES = [
    json.loads(line)
    for line in CASES_PATH.read_text().splitlines()
    if line.strip()
]

OWNER_SUB = "dev|retrieval"

EVAL_DOC_TEXT = {
    "eval_alpha.pdf": [
        "Paris is the capital of France.",
        "Quality answers require precise sources.",
        "For help, email support@ragqa.local.",
        "Library mode covers all indexed documents for evaluation.",
    ],
    "eval_beta.pdf": [
        "Neural search combines embeddings with trigram fallback logic.",
        "Precision and recall are classic information retrieval metrics.",
        "Selected document mode restricts results to approved documents.",
        "Hybrid retrieval merges scores from multiple candidate sources.",
    ],
}


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer dev-token", "x-dev-sub": OWNER_SUB}


@pytest.fixture(scope="module")
def seeded_docs():
    session = SessionLocal()
    doc_map: dict[str, str] = {}
    owner_sub = OWNER_SUB
    try:
        session.query(Document).filter(
            Document.owner_sub == owner_sub,
        ).delete(synchronize_session=False)
        session.commit()
        for filename, texts in EVAL_DOC_TEXT.items():
            doc_id = str(uuid.uuid4())
            content_hash = uuid.uuid4().hex
            doc = Document(
                id=doc_id,
                filename=filename,
                status="indexed",
                owner_sub=owner_sub,
                content_hash=content_hash,
                meta={"source": "eval"},
            )
            session.add(doc)
            for idx, text in enumerate(texts):
                chunk = Chunk(
                    id=str(uuid.uuid4()),
                    document_id=doc_id,
                    page=idx + 1,
                    chunk_index=idx,
                    text=text,
                )
                session.add(chunk)
            doc_map[filename] = doc_id
        session.commit()
        yield doc_map
    finally:
        if doc_map:
            ids = list(doc_map.values())
            session.query(Document).filter(Document.id.in_(ids)).delete(
                synchronize_session=False
            )
            session.commit()
        session.close()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_retrieval_regression(case: dict, seeded_docs: dict[str, str]):
    headers = _headers()
    payload = {
        "q": case["query"],
        "mode": case.get("mode", "library"),
        "limit": case.get("k", 5),
        "debug": bool(case.get("debug")),
    }

    if payload["mode"] == "selected_docs":
        allowed_filenames = case.get("allowed_filenames") or case.get(
            "expected_filenames", []
        )
        assert allowed_filenames, f"{case['name']}: allowed_filenames required"
        try:
            doc_ids = [seeded_docs[name] for name in allowed_filenames]
        except KeyError as exc:
            raise AssertionError(
                f"{case['name']}: unknown allowed filename {exc}"
            ) from exc
        payload["document_ids"] = doc_ids

    resp = client.post("/api/search", headers=headers, json=payload)
    assert resp.status_code == 200, f"{case['name']}: {resp.text}"
    body = resp.json()
    hits = body.get("hits") or []
    assert hits, f"{case['name']}: expected hits, got none"

    k = int(case.get("k", len(hits)))
    top_hits = hits[:k]
    expected_files = case.get("expected_filenames", [])
    if expected_files:
        try:
            expected_ids = {seeded_docs[name] for name in expected_files}
        except KeyError as exc:
            raise AssertionError(
                f"{case['name']}: unknown expected filename {exc}"
            ) from exc
        top_ids = {hit.get("document_id") for hit in top_hits}
        assert (
            top_ids & expected_ids
        ), f"{case['name']}: recall@{k} failed. expected {expected_ids}, got {top_ids}"

    substrings = [s.lower() for s in case.get("expected_substrings", [])]
    if substrings:
        normalized_hits = [
            (hit.get("document_id"), (hit.get("text") or "").lower()) for hit in top_hits
        ]
        assert any(
            all(sub in text for sub in substrings) for _, text in normalized_hits
        ), f"{case['name']}: expected substrings {substrings} not found in top hits"

    if payload["mode"] == "selected_docs":
        allowed_ids = set(payload.get("document_ids") or [])
        bad_hits = [
            (hit.get("document_id"), hit.get("text"))
            for hit in hits
            if hit.get("document_id") not in allowed_ids
        ]
        assert (
            not bad_hits
        ), f"{case['name']}: hits outside allowed doc_ids: {bad_hits}"

    if case.get("expect_trgm_count_min") is not None:
        debug = body.get("debug") or {}
        trgm_count = debug.get("trgm_count")
        assert trgm_count is not None, f"{case['name']}: missing trgm_count in debug"
        assert (
            trgm_count >= case["expect_trgm_count_min"]
        ), f"{case['name']}: expected trgm_count >= {case['expect_trgm_count_min']}, got {trgm_count}"

    if case.get("require_trgm_sim_hit"):
        has_trgm = any(hit.get("trgm_sim") is not None for hit in hits)
        assert has_trgm, f"{case['name']}: expected at least one hit with trgm_sim"
