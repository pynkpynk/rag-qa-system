#!/usr/bin/env python3
"""
Create a deterministic dev run with attached documents so local /api/chat/ask tests
can rely on a known run_id. Prints the run_id on success.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.authz import effective_auth_mode  # noqa: E402
from app.db.models import Chunk, Document, Run, EMBEDDING_DIM  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

SEED_SPECS = [
    {
        "filename": "dev-seed-en.txt",
        "content_hash": "dev_seed_document_en_v1",
        "text": "Dev seed chunk text for retrieval-debug E2E checks in English.",
    },
    {
        "filename": "dev-seed-ja.txt",
        "content_hash": "dev_seed_document_ja_v1",
        "text": "利害関係者 の 視点 の 違い を 要点 として まとめる テスト。",
    },
]

def _zero_embedding() -> list[float]:
    return [0.0] * EMBEDDING_DIM

def _ensure_chunk(db: Session, document_id: str, text: str) -> None:
    chunk = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id, Chunk.chunk_index == 0)
        .first()
    )
    if chunk:
        return
    db.add(
        Chunk(
            document_id=document_id,
            page=1,
            chunk_index=0,
            text=text,
            embedding=_zero_embedding(),
        )
    )

def _ensure_seed_document(db: Session, owner_sub: str, spec: dict[str, str]) -> Document:
    doc = (
        db.query(Document)
        .filter(
            Document.owner_sub == owner_sub,
            Document.content_hash == spec["content_hash"],
        )
        .first()
    )
    if doc:
        _ensure_chunk(db, doc.id, spec["text"])
        return doc

    doc = Document(
        filename=spec["filename"],
        owner_sub=owner_sub,
        content_hash=spec["content_hash"],
        status="uploaded",
        meta={"dev_seed": True},
    )
    db.add(doc)
    db.flush()

    _ensure_chunk(db, doc.id, spec["text"])
    return doc

def _create_run(db: Session, owner_sub: str, docs: list[Document]) -> Run:
    run = Run(
        owner_sub=owner_sub,
        config={"model": "gpt-5-mini", "gen": {}},
        status="seeded",
    )
    for doc in docs:
        run.documents.append(doc)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed a dev run with attached documents.")
    parser.add_argument("--force", action="store_true", help="Allow running outside AUTH_MODE=dev")
    args = parser.parse_args(argv)

    mode = effective_auth_mode()
    if mode != "dev" and not args.force:
        print("[dev_seed_run] AUTH_MODE must be 'dev' (pass --force to override).", file=sys.stderr)
        return 1

    owner_sub = (os.getenv("DEV_SUB") or "dev|local").strip()
    if not owner_sub:
        print("[dev_seed_run] DEV_SUB is empty; update backend/.env.local.", file=sys.stderr)
        return 1

    db: Session = SessionLocal()
    try:
        docs = [_ensure_seed_document(db, owner_sub, spec) for spec in SEED_SPECS]
        run = _create_run(db, owner_sub, docs)
        print(run.id)
    except Exception as exc:
        db.rollback()
        print(f"[dev_seed_run] Failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
