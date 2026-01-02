from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Optional

# --- DB session import (プロジェクトに合わせて調整) ---
try:
    # よくある構成
    from app.db.session import SessionLocal  # type: ignore
except Exception:  # pragma: no cover
    # もし SessionLocal が無い構成なら、settings.database_url から作る（応急）
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings

    db_url = getattr(settings, "database_url", None) or getattr(
        settings, "DATABASE_URL", None
    )
    if not db_url:
        raise RuntimeError("database_url is not configured (settings.database_url).")

    connect_args = (
        {"check_same_thread": False} if str(db_url).startswith("sqlite") else {}
    )
    engine = create_engine(db_url, connect_args=connect_args)  # type: ignore
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Document model import (プロジェクトに合わせて調整) ---
try:
    from app.db.models import Document  # type: ignore
except Exception:  # pragma: no cover
    # ここはあなたのモデルパスに合わせて直す
    raise ImportError(
        "Cannot import Document model. Update import path in doc_index_job.py"
    )

# --- Indexer import (あなたの既存 index 関数に合わせて調整) ---
try:
    # 例：PDFパスを渡して index する関数が既にある想定
    from app.services.indexer import index_document_from_pdf  # type: ignore
except Exception:  # pragma: no cover
    # ここもあなたの既存実装に合わせて直す
    index_document_from_pdf = None  # type: ignore


@contextmanager
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_pdf_path(doc: Any) -> Optional[str]:
    """
    既存実装に寄せるための“それっぽい”パス解決。
    - doc.path
    - doc.file_path
    - doc.meta["path"] / doc.metadata["path"]
    """
    for attr in ("path", "file_path", "pdf_path"):
        v = getattr(doc, attr, None)
        if isinstance(v, str) and v:
            return v

    meta = getattr(doc, "meta", None) or getattr(doc, "metadata", None)
    if isinstance(meta, dict):
        p = meta.get("path") or meta.get("file_path") or meta.get("pdf_path")
        if isinstance(p, str) and p:
            return p
    return None


def run_index_job(document_id: str) -> None:
    """
    BackgroundTasks から呼ばれる “ジョブ本体”。
    - status を indexing → indexed/failed に更新
    - 失敗時は error を保存（短く）
    """
    # 1) doc取得 & indexingに更新
    with db_session() as db:
        doc = db.get(Document, document_id)  # SQLAlchemy 2.0 style
        if not doc:
            return

        # すでに処理中なら二重起動しない
        if getattr(doc, "status", None) == "indexing":
            return

        doc.status = "indexing"
        doc.error = None
        db.commit()

        pdf_path = _get_pdf_path(doc)

    # 2) index 実行（ここは既存のindexerに合わせる）
    try:
        if not pdf_path:
            raise RuntimeError("PDF path is missing in Document record.")

        if index_document_from_pdf is None:
            raise RuntimeError(
                "index_document_from_pdf import is not configured. Fix import in doc_index_job.py"
            )

        # 例：既存パイプラインに合わせて「パス＋document_id」を渡す
        index_document_from_pdf(pdf_path, document_id=document_id)

    except Exception as e:
        msg = str(e)
        if len(msg) > 900:
            msg = msg[:900] + "…"
        with db_session() as db:
            doc = db.get(Document, document_id)
            if doc:
                doc.status = "failed"
                doc.error = msg
                db.commit()
        return

    # 3) 成功 → indexed
    with db_session() as db:
        doc = db.get(Document, document_id)
        if doc:
            doc.status = "indexed"
            doc.error = None
            db.commit()
