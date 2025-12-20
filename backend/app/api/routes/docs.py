from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.db.session import SessionLocal, get_db
from app.services.indexing import embed_texts, extract_pdf_pages, simple_chunk

router = APIRouter()

# =========================
# Config
# =========================

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "data/uploads")).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

PDF_MAGIC = b"%PDF-"

SQL_DOC_ATTACHED_TO_RUN = """
SELECT EXISTS(
  SELECT 1
  FROM run_documents
  WHERE run_id = :run_id AND document_id = :document_id
) AS ok
"""

ERROR_MAX_LEN = 900

# =========================
# Response Models
# =========================

class DocListItem(BaseModel):
    document_id: str
    filename: str
    status: str
    error: str | None = None


class DocUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    dedup: bool = False


class DocDetailResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    error: str | None = None
    content_hash: str | None = None
    meta: dict[str, Any] | None = None
    created_at: str


class DocPageChunkItem(BaseModel):
    chunk_id: str
    chunk_index: int
    text: str


# =========================
# Helpers
# =========================

def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "")
    return base or "uploaded.pdf"


def _require_pdf_extension(filename: str) -> None:
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")


def _final_path(content_hash: str, filename: str) -> Path:
    return UPLOAD_DIR / f"{content_hash[:12]}_{filename}"


def _get_doc_path(doc: Document) -> Path | None:
    if not doc.meta or not isinstance(doc.meta, dict):
        return None
    p = doc.meta.get("path")
    if not p:
        return None
    path = Path(str(p))
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _cleanup_file(path: Path | None) -> None:
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _truncate_err(e: Exception) -> str:
    msg = str(e) or e.__class__.__name__
    if len(msg) > ERROR_MAX_LEN:
        msg = msg[:ERROR_MAX_LEN] + "…"
    return msg


def _sha256_and_save_tmp(upload: UploadFile, tmp_path: Path) -> str:
    hasher = hashlib.sha256()
    total = 0
    first = True

    with tmp_path.open("wb") as f:
        while True:
            buf = upload.file.read(1024 * 1024)  # 1MB
            if not buf:
                break

            if first:
                first = False
                if not buf.startswith(PDF_MAGIC):
                    raise HTTPException(status_code=400, detail="Invalid PDF file (missing %PDF- header).")

            total += len(buf)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Max {MAX_UPLOAD_MB}MB is allowed.",
                )

            hasher.update(buf)
            f.write(buf)

    if total == 0:
        raise HTTPException(status_code=400, detail="Empty file is not allowed.")

    return hasher.hexdigest()


def _enforce_run_access_if_needed(db: Session, run_id: str | None, document_id: str) -> None:
    if not run_id:
        return

    row = db.execute(
        sql_text(SQL_DOC_ATTACHED_TO_RUN),
        {"run_id": run_id, "document_id": document_id},
    ).mappings().first()

    ok = bool(row and row.get("ok"))
    if not ok:
        raise HTTPException(status_code=403, detail="document not accessible for this run_id")


def _safe_cd_filename(name: str) -> str:
    # Content-Disposition の filename="" を壊さない最低限の無害化
    return (name or "document.pdf").replace('"', "").replace("\n", "").replace("\r", "")


# =========================
# Background Task
# =========================

def index_document(doc_id: str, file_path: str) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return

        doc.status = "indexing"
        doc.error = None
        db.commit()

        path = Path(file_path)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()

        if not path.exists():
            raise RuntimeError("PDF file not found on disk.")

        pages = extract_pdf_pages(str(path))

        texts: list[str] = []
        metas: list[tuple[int | None, int, str]] = []
        for page_no, page_text in pages:
            chunks = simple_chunk(page_text)
            for idx, ch in enumerate(chunks):
                texts.append(ch)
                metas.append((page_no, idx, ch))

        if not texts:
            raise RuntimeError("No extractable text found in PDF.")

        vecs = embed_texts(texts)

        db.query(Chunk).filter(Chunk.document_id == doc_id).delete(synchronize_session=False)

        for (page_no, idx, ch), vec in zip(metas, vecs):
            db.add(
                Chunk(
                    document_id=doc_id,
                    page=page_no,
                    chunk_index=idx,
                    text=ch,
                    embedding=vec,
                )
            )

        doc.status = "indexed"
        doc.error = None
        db.commit()

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass

        doc = db.get(Document, doc_id)
        if doc:
            doc.status = "failed"
            doc.error = _truncate_err(e)
            try:
                db.commit()
            except Exception:
                pass
    finally:
        db.close()


# =========================
# Routes
# =========================

@router.post("/docs/upload", response_model=DocUploadResponse)
def upload_doc(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = _safe_filename(file.filename or "uploaded.pdf")
    _require_pdf_extension(filename)

    tmp_path = UPLOAD_DIR / f"tmp_{uuid.uuid4().hex}_{filename}"
    final_path: Path | None = None

    try:
        content_hash = _sha256_and_save_tmp(file, tmp_path)

        existing = db.query(Document).filter(Document.content_hash == content_hash).first()
        if existing:
            _cleanup_file(tmp_path)
            return DocUploadResponse(
                document_id=existing.id,
                filename=existing.filename,
                status=existing.status,
                dedup=True,
            )

        final_path = _final_path(content_hash, filename)
        os.replace(tmp_path, final_path)

        doc = Document(
            filename=filename,
            status="uploaded",
            content_hash=content_hash,
            meta={"path": str(final_path)},
        )
        db.add(doc)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            _cleanup_file(final_path)
            existing = db.query(Document).filter(Document.content_hash == content_hash).first()
            if existing:
                return DocUploadResponse(
                    document_id=existing.id,
                    filename=existing.filename,
                    status=existing.status,
                    dedup=True,
                )
            raise

        db.refresh(doc)

        # Upload直後から indexing に（UIの固まり感を軽減）
        doc.status = "indexing"
        doc.error = None
        db.commit()
        db.refresh(doc)

        background.add_task(index_document, doc.id, str(final_path))

        return DocUploadResponse(
            document_id=doc.id,
            filename=doc.filename,
            status=doc.status,
            dedup=False,
        )

    except HTTPException:
        _cleanup_file(tmp_path)
        _cleanup_file(final_path)
        raise
    except Exception:
        _cleanup_file(tmp_path)
        _cleanup_file(final_path)
        raise
    finally:
        try:
            file.file.close()
        except Exception:
            pass


@router.post("/docs/{document_id}/reindex")
def reindex_doc(
    document_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    file_path = _get_doc_path(doc)
    if not file_path:
        raise HTTPException(status_code=404, detail="document file path not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="file not found on disk")

    doc.status = "indexing"
    doc.error = None
    db.commit()

    background.add_task(index_document, doc.id, str(file_path))
    return {"document_id": doc.id, "queued": True}


@router.get("/docs", response_model=list[DocListItem])
def list_docs(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [
        DocListItem(
            document_id=d.id,
            filename=d.filename,
            status=d.status,
            error=d.error,
        )
        for d in docs
    ]


@router.get("/docs/{document_id}", response_model=DocDetailResponse)
def get_doc_detail(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    created_at = doc.created_at.isoformat() if isinstance(doc.created_at, datetime) else str(doc.created_at)

    return DocDetailResponse(
        document_id=doc.id,
        filename=doc.filename,
        status=doc.status,
        error=doc.error,
        content_hash=getattr(doc, "content_hash", None),
        meta=doc.meta,
        created_at=created_at,
    )


# ✅ App.jsx / api.js が呼ぶ「同一ページのチャンク一覧」
@router.get("/docs/{document_id}/pages/{page}", response_model=list[DocPageChunkItem])
def get_doc_page_chunks(
    document_id: str,
    page: int,
    run_id: str | None = Query(default=None, description="Optional: restrict access to docs attached to this run"),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    _enforce_run_access_if_needed(db, run_id, document_id)

    rows = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id, Chunk.page == page)
        .order_by(Chunk.chunk_index.asc())
        .all()
    )

    return [DocPageChunkItem(chunk_id=r.id, chunk_index=r.chunk_index, text=r.text) for r in rows]


@router.get("/docs/{document_id}/download")
def download_doc(
    document_id: str,
    run_id: str | None = None,
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    _enforce_run_access_if_needed(db, run_id, document_id)

    file_path = _get_doc_path(doc)
    if not file_path:
        raise HTTPException(status_code=404, detail="document file path not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="file not found on disk")

    # attachment（明示ダウンロード）
    safe_name = _safe_cd_filename(doc.filename)
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=safe_name,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{safe_name}"',
        },
    )


@router.get("/docs/{document_id}/view")
def view_pdf(
    document_id: str,
    run_id: str | None = None,
    db: Session = Depends(get_db),
):
    """
    inline（ブラウザ表示/iframe表示）用。
    """
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    _enforce_run_access_if_needed(db, run_id, document_id)

    file_path = _get_doc_path(doc)
    if not file_path:
        raise HTTPException(status_code=404, detail="document file path not found")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="file not found on disk")

    safe_name = _safe_cd_filename(doc.filename or os.path.basename(str(file_path)))

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "Cache-Control": "no-store",
        },
    )
