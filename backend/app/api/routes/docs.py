from __future__ import annotations

import hashlib
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, UploadFile, Query
from fastapi.responses import RedirectResponse
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

# S3 ONLY (local backend disabled)
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "s3").lower()
if STORAGE_BACKEND != "s3":
    # fail-fast: avoid accidental disk persistence
    raise RuntimeError("This service is configured as S3-only. Set STORAGE_BACKEND=s3.")

AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
S3_BUCKET = os.environ.get("S3_BUCKET")
S3_PREFIX = (os.environ.get("S3_PREFIX") or "uploads").strip("/")
S3_PRESIGN_EXPIRES = int(os.environ.get("S3_PRESIGN_EXPIRES", "900"))

# Admin delete protection (required)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

# Temp upload dir (ephemeral OK)
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/tmp/rag-qa-uploads")).resolve()
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

_s3_client = None


def _require_s3_settings() -> None:
    if not AWS_REGION:
        raise RuntimeError("AWS_REGION (or AWS_DEFAULT_REGION) is not set")
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET is not set")


def _get_s3():
    global _s3_client
    _require_s3_settings()
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


# =========================
# Helpers
# =========================

def _log(event: str, **fields: Any) -> None:
    # simple structured log
    payload = {"event": event, **fields}
    try:
        import json
        print(json.dumps(payload, ensure_ascii=False))
    except Exception:
        print(payload)


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "")
    return base or "uploaded.pdf"


def _safe_cd_filename(name: str) -> str:
    return (name or "document.pdf").replace('"', "").replace("\n", "").replace("\r", "")


def _require_pdf_extension(filename: str) -> None:
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")


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
    """
    Read upload stream, validate PDF magic header, enforce size limit,
    compute sha256, and write to tmp_path.
    """
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


def _require_admin_token(x_admin_token: str | None) -> None:
    # fail-closed: if not set, endpoint behaves as Not Found
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=404, detail="Not Found")
    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")


# =========================
# S3 helpers
# =========================

def _s3_key_for(doc_id: str, content_hash: str, filename: str) -> str:
    safe = _safe_filename(filename)
    return f"{S3_PREFIX}/{doc_id}/{content_hash[:12]}_{safe}"


def _with_retry(fn, *, tries: int = 2, sleep_sec: float = 0.4):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(sleep_sec * (2 ** i))
    raise last  # type: ignore[misc]


def _s3_upload_file(local_path: Path, key: str) -> None:
    _require_s3_settings()
    s3 = _get_s3()

    def _do():
        s3.upload_file(
            Filename=str(local_path),
            Bucket=S3_BUCKET,
            Key=key,
            ExtraArgs={"ContentType": "application/pdf"},
        )
        return None

    _with_retry(_do, tries=2)


def _s3_delete_object_best_effort(key: str) -> None:
    try:
        _require_s3_settings()
        s3 = _get_s3()
        s3.delete_object(Bucket=S3_BUCKET, Key=key)
    except Exception:
        pass


def _s3_presign_get(key: str, inline: bool, filename: str) -> str:
    _require_s3_settings()
    s3 = _get_s3()
    disp = "inline" if inline else "attachment"
    safe = _safe_cd_filename(filename)
    return s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": S3_BUCKET,
            "Key": key,
            "ResponseContentType": "application/pdf",
            "ResponseContentDisposition": f'{disp}; filename="{safe}"',
        },
        ExpiresIn=S3_PRESIGN_EXPIRES,
    )


def _s3_download_to_tmp(key: str, suffix: str = ".pdf") -> Path:
    _require_s3_settings()
    s3 = _get_s3()
    tmp = Path("/tmp") / f"ragqa_{uuid.uuid4().hex}{suffix}"

    def _do():
        s3.download_file(Bucket=S3_BUCKET, Key=key, Filename=str(tmp))
        return None

    _with_retry(_do, tries=2)
    return tmp


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
    storage_key: str | None = None
    meta: dict[str, Any] | None = None
    created_at: str


class DocPageChunkItem(BaseModel):
    chunk_id: str
    chunk_index: int
    text: str


class DocDeleteResponse(BaseModel):
    document_id: str
    deleted: bool
    storage_deleted: bool
    storage_key: str | None = None


# =========================
# Background Task
# =========================

def index_document(doc_id: str) -> None:
    db = SessionLocal()
    tmp_download: Path | None = None

    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return

        doc.status = "indexing"
        doc.error = None
        db.commit()

        if not doc.storage_key:
            # S3-only運用なのでここに来たらデータ不整合
            raise RuntimeError("storage_key missing for S3-only backend")

        try:
            tmp_download = _s3_download_to_tmp(doc.storage_key, suffix=".pdf")
            path = tmp_download
        except ClientError as e:
            raise RuntimeError(f"S3 download failed: {e}")

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

        _log("index_ok", document_id=doc_id)

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

        _log("index_failed", document_id=doc_id, error=_truncate_err(e))

    finally:
        if tmp_download:
            _cleanup_file(tmp_download)
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

    try:
        content_hash = _sha256_and_save_tmp(file, tmp_path)

        existing = db.query(Document).filter(Document.content_hash == content_hash).first()
        if existing:
            # dedup: S3-only運用でも storage_key が空なら埋める（バックフィル）
            if not existing.storage_key:
                key = _s3_key_for(existing.id, content_hash, existing.filename)
                _s3_upload_file(tmp_path, key)
                existing.storage_key = key
                existing.meta = {
                    "storage": "s3",
                    "bucket": S3_BUCKET,
                    "key": key,
                    "region": AWS_REGION,
                }
                db.commit()

            _cleanup_file(tmp_path)
            return DocUploadResponse(
                document_id=existing.id,
                filename=existing.filename,
                status=existing.status,
                dedup=True,
            )

        # new document id（先に作ってS3 keyに使う）
        doc_id = str(uuid.uuid4())
        key = _s3_key_for(doc_id, content_hash, filename)

        # 1) upload to S3
        t0 = time.time()
        _s3_upload_file(tmp_path, key)
        _cleanup_file(tmp_path)
        _log("s3_upload_ok", document_id=doc_id, storage_key=key, ms=int((time.time() - t0) * 1000))

        # 2) write DB
        doc = Document(
            id=doc_id,
            filename=filename,
            status="uploaded",
            content_hash=content_hash,
            storage_key=key,
            meta={"storage": "s3", "bucket": S3_BUCKET, "key": key, "region": AWS_REGION},
        )
        db.add(doc)

        try:
            db.commit()
        except IntegrityError:
            # race: if another request inserted same hash, clean up the uploaded object
            db.rollback()
            _s3_delete_object_best_effort(key)

            existing2 = db.query(Document).filter(Document.content_hash == content_hash).first()
            if existing2:
                return DocUploadResponse(
                    document_id=existing2.id,
                    filename=existing2.filename,
                    status=existing2.status,
                    dedup=True,
                )
            raise
        except Exception as e:
            # DB failure -> best-effort cleanup S3 to avoid orphan
            db.rollback()
            _s3_delete_object_best_effort(key)
            raise HTTPException(status_code=500, detail=f"DB commit failed: {_truncate_err(e)}")

        db.refresh(doc)

        # 3) queue indexing
        doc.status = "indexing"
        doc.error = None
        db.commit()
        db.refresh(doc)

        background.add_task(index_document, doc.id)

        return DocUploadResponse(
            document_id=doc.id,
            filename=doc.filename,
            status=doc.status,
            dedup=False,
        )

    except HTTPException:
        _cleanup_file(tmp_path)
        raise
    except Exception as e:
        _cleanup_file(tmp_path)
        _log("upload_failed", error=_truncate_err(e))
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

    doc.status = "indexing"
    doc.error = None
    db.commit()

    background.add_task(index_document, doc.id)
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
        storage_key=getattr(doc, "storage_key", None),
        meta=doc.meta,
        created_at=created_at,
    )


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

    if not doc.storage_key:
        raise HTTPException(status_code=500, detail="storage_key missing (S3-only backend)")

    url = _s3_presign_get(doc.storage_key, inline=False, filename=doc.filename)
    return RedirectResponse(url, status_code=307)


@router.get("/docs/{document_id}/view")
def view_pdf(
    document_id: str,
    run_id: str | None = None,
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    _enforce_run_access_if_needed(db, run_id, document_id)

    if not doc.storage_key:
        raise HTTPException(status_code=500, detail="storage_key missing (S3-only backend)")

    url = _s3_presign_get(doc.storage_key, inline=True, filename=doc.filename)
    return RedirectResponse(url, status_code=307)


@router.delete("/docs/{document_id}", response_model=DocDeleteResponse)
def delete_doc(
    document_id: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: Session = Depends(get_db),
):
    _require_admin_token(x_admin_token)

    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")

    # capture before delete
    storage_key = getattr(doc, "storage_key", None) or (doc.meta.get("key") if isinstance(doc.meta, dict) else None)

    # ---- DB delete first (avoid deleting S3 while DB fails) ----
    try:
        # detach from runs
        db.execute(
            sql_text("DELETE FROM run_documents WHERE document_id = :document_id"),
            {"document_id": document_id},
        )

        # delete chunks
        db.query(Chunk).filter(Chunk.document_id == document_id).delete(synchronize_session=False)

        # delete document row
        db.delete(doc)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"delete failed: {_truncate_err(e)}")

    # ---- storage delete (best-effort) ----
    storage_deleted = False
    if storage_key:
        try:
            _s3_delete_object_best_effort(storage_key)
            storage_deleted = True
        except Exception:
            storage_deleted = False

    _log("doc_deleted", document_id=document_id, storage_key=storage_key, storage_deleted=storage_deleted)

    return DocDeleteResponse(
        document_id=document_id,
        deleted=True,
        storage_deleted=storage_deleted,
        storage_key=storage_key,
    )
