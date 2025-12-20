#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text as sql_text

from app.db.session import SessionLocal
from app.db.models import Document


UPLOAD_DIR = Path("data/uploads")


SQL_DELETE_RUN_DOCUMENTS = "DELETE FROM run_documents"
SQL_DELETE_RUNS = "DELETE FROM runs"

SQL_DELETE_CHUNKS = "DELETE FROM chunks"
SQL_DELETE_DOCUMENTS = "DELETE FROM documents"


def _collect_uploaded_paths(db) -> list[Path]:
    """
    documents.meta["path"] からアップロードPDFの実体パスを集める。
    metaが壊れてても落ちないように保守的に扱う。
    """
    paths: list[Path] = []
    docs = db.query(Document).all()
    for d in docs:
        meta = getattr(d, "meta", None)
        if not isinstance(meta, dict):
            continue
        p = meta.get("path")
        if not p:
            continue
        try:
            paths.append(Path(str(p)))
        except Exception:
            continue
    return paths


def cleanup_runs_only(db) -> None:
    db.execute(sql_text(SQL_DELETE_RUN_DOCUMENTS))
    db.execute(sql_text(SQL_DELETE_RUNS))


def cleanup_all_db(db) -> None:
    # 依存関係の順に消す（FKがあっても安全側）
    db.execute(sql_text(SQL_DELETE_RUN_DOCUMENTS))
    db.execute(sql_text(SQL_DELETE_RUNS))
    db.execute(sql_text(SQL_DELETE_CHUNKS))
    db.execute(sql_text(SQL_DELETE_DOCUMENTS))


def cleanup_uploaded_files(paths: list[Path], nuke_upload_dir: bool) -> dict:
    deleted = []
    missing = []
    failed = []

    for p in paths:
        try:
            if p.exists():
                p.unlink()
                deleted.append(str(p))
            else:
                missing.append(str(p))
        except Exception as e:
            failed.append({"path": str(p), "error": str(e)})

    if nuke_upload_dir and UPLOAD_DIR.exists():
        # uploads配下を丸ごと消す（tmp_含む）。危険なのでフラグ必須。
        for p in UPLOAD_DIR.glob("*"):
            try:
                if p.is_file():
                    p.unlink()
                    deleted.append(str(p))
            except Exception as e:
                failed.append({"path": str(p), "error": str(e)})

    return {"deleted": deleted, "missing": missing, "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Dev cleanup utility for rag-qa-system.")
    parser.add_argument(
        "--mode",
        choices=["runs", "all"],
        default="runs",
        help="runs: delete only runs/run_documents. all: delete runs + documents + chunks.",
    )
    parser.add_argument(
        "--delete-files",
        action="store_true",
        help="Also delete uploaded PDF files referenced by documents.meta['path'] (only meaningful with --mode all).",
    )
    parser.add_argument(
        "--nuke-upload-dir",
        action="store_true",
        help="DANGEROUS: delete everything under data/uploads as well (tmp files etc). Requires --delete-files.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        file_paths = _collect_uploaded_paths(db)

        if args.mode == "runs":
            cleanup_runs_only(db)
            db.commit()
            print(json.dumps({"ok": True, "mode": "runs", "note": "Deleted runs/run_documents only."}, indent=2))
            return

        # mode == "all"
        cleanup_all_db(db)
        db.commit()

        file_report = None
        if args.delete_files:
            file_report = cleanup_uploaded_files(file_paths, nuke_upload_dir=args.nuke_upload_dir)

        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "all",
                    "db": "Deleted run_documents, runs, chunks, documents.",
                    "files": file_report,
                },
                indent=2,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
