from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple

import boto3
from botocore.exceptions import ClientError

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    Query,
)
from fastapi.responses import RedirectResponse, FileResponse
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import Principal, require_permissions, is_admin, current_user
from app.core.config import settings
from app.db.models import Chunk, Document
from app.db.session import SessionLocal, get_db
from app.services.indexing import embed_texts, extract_pdf_pages, simple_chunk

from app.core.run_access import ensure_run_access
from app.schemas.api_contract import (
    DocumentDetailResponse,
    DocumentListItem,
    DocumentPageChunkItem,
    DocumentReindexResponse,
    DocumentUploadResponse,
)

router = APIRouter()

# =========================
# Config (S3 only)
# =========================

PDF_MAGIC = b"%PDF-"
ERROR_MAX_LEN = 900

AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
S3_BUCKET = os.environ.get("S3_BUCKET")
S3_PREFIX = (os.environ.get("S3_PREFIX") or "uploads").strip("/")
S3_PRESIGN_EXPIRES = int(os.environ.get("S3_PRESIGN_EXPIRES", "900"))

TMP_DIR = Path(os.environ.get("RAGQA_TMP_DIR", "/tmp/rag-qa-uploads"))
TMP_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_STORAGE_DIR = Path(settings.upload_dir).resolve()
LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

SQL_DOC_ATTACHED_TO_RUN = """
SELECT EXISTS(
  SELECT 1
  FROM run_documents
  WHERE run_id = :run_id AND document_id = :document_id
) AS ok
"""

_s3_client = None


def _s3_configured() -> bool:
    return bool(AWS_REGION and S3_BUCKET)


def _require_s3_settings() -> None:
    if not _s3_configured():
        raise RuntimeError("Object storage is not configured")


def _get_s3():
    global _s3_client
    _require_s3_settings()
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


# =========================
# Helpers
# =========================


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "")
    return base or "uploaded.pdf"


def _safe_cd_filename(name: str) -> str:
    return (name or "document.pdf").replace('"', "").replace("\n", "").replace("\r", "")


def _require_pdf_extension(filename: str) -> None:
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")


def _require_pdf_content_type(upload: UploadFile) -> None:
    ctype = (upload.content_type or "").split(";")[0].strip().lower()
    if ctype and ctype != "application/pdf":
        raise HTTPException(
            status_code=415, detail="Content-Type must be application/pdf."
        )


def _max_upload_limits() -> Tuple[int, int]:
    """
    Returns (bytes, mb_ceiling).
    Prefers runtime env override, otherwise settings.max_upload_bytes.
    """
    env_raw = os.getenv("MAX_UPLOAD_BYTES")
    limit = None
    if env_raw:
        try:
            limit = int(env_raw)
        except ValueError:
            limit = None
    if not limit or limit <= 0:
        limit = int(getattr(settings, "max_upload_bytes", 20_000_000))
    mb = max(1, (limit + (1024 * 1024) - 1) // (1024 * 1024))
    return limit, mb


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
    limit_bytes, limit_mb = _max_upload_limits()

    with tmp_path.open("wb") as f:
        while True:
            buf = upload.file.read(1024 * 1024)  # 1MB
            if not buf:
                break

            if first:
                first = False
                if not buf.startswith(PDF_MAGIC):
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid PDF file (missing %PDF- header).",
                    )

            total += len(buf)
            if total > limit_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Max {limit_mb}MB is allowed.",
                )

            hasher.update(buf)
            f.write(buf)

    if total == 0:
        raise HTTPException(status_code=400, detail="Empty file is not allowed.")

    return hasher.hexdigest()


def _enforce_run_access_if_needed(
    db: Session, run_id: str | None, document_id: str, p: Principal
) -> None:
    if not run_id:
        return

    # ① run所有権
    ensure_run_access(db, run_id, p)

    # ② run_documentsに紐づくdocか
    row = (
        db.execute(
            sql_text(SQL_DOC_ATTACHED_TO_RUN),
            {"run_id": run_id, "document_id": document_id},
        )
        .mappings()
        .first()
    )
    ok = bool(row and row.get("ok"))
    if not ok:
        raise HTTPException(status_code=404, detail="document not found")


def _not_found() -> None:
    # 他人doc/legacy doc は 404 で隠す（存在推測を防ぐ）
    raise HTTPException(status_code=404, detail="document not found")


def _get_doc_for_read(db: Session, document_id: str, p: Principal) -> Document:
    """
    - admin: 任意のdocにアクセス可（legacy含む）
    - non-admin: owner_sub == p.sub のdocのみ
    - legacy(owner_sub NULL) は adminのみ（non-adminは404）
    """
    if is_admin(p):
        doc = db.get(Document, document_id)
        if not doc:
            _not_found()
        return doc

    # 非adminは "id AND owner_sub" で直接絞る（db.getは使わない）
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.owner_sub == p.sub)
        .first()
    )
    if not doc:
        _not_found()
    return doc


# =========================
# S3 helpers
# =========================


def _s3_key_for(doc_id: str, content_hash: str, filename: str) -> str:
    safe = _safe_filename(filename)
    return f"{S3_PREFIX}/{doc_id}/{content_hash[:12]}_{safe}"


def _s3_upload_file(local_path: Path, key: str) -> None:
    s3 = _get_s3()
    s3.upload_file(
        Filename=str(local_path),
        Bucket=S3_BUCKET,
        Key=key,
        ExtraArgs={"ContentType": "application/pdf"},
    )


def _s3_delete_object(key: str) -> None:
    try:
        s3 = _get_s3()
        s3.delete_object(Bucket=S3_BUCKET, Key=key)
    except Exception:
        pass


def _s3_presign_get(key: str, inline: bool, filename: str) -> str:
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
    s3 = _get_s3()
    tmp = TMP_DIR / f"ragqa_{uuid.uuid4().hex}{suffix}"
    s3.download_file(Bucket=S3_BUCKET, Key=key, Filename=str(tmp))
    return tmp


def _local_storage_path(doc_id: str) -> Path:
    return LOCAL_STORAGE_DIR / f"{doc_id}.pdf"


def _resolve_local_path(path_value: str | None) -> Path:
    if not path_value:
        return LOCAL_STORAGE_DIR / "missing.pdf"
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = LOCAL_STORAGE_DIR / candidate
    return candidate


def _delete_local_file(path_value: str | None) -> None:
    path = _resolve_local_path(path_value)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _doc_uses_local_storage(doc: Document) -> bool:
    storage_meta = doc.meta or {}
    storage_type = storage_meta.get("storage")
    if storage_type:
        return storage_type == "local"
    return False


def _truthy_env(name: str, default: str = "") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _indexing_available() -> Tuple[bool, str | None]:
    if _truthy_env("OPENAI_OFFLINE", "0"):
        return True, None
    secret = getattr(settings, "openai_api_key", None)
    if hasattr(secret, "get_secret_value"):
        api_key_value = secret.get_secret_value()
    elif isinstance(secret, str):
        api_key_value = secret
    else:
        api_key_value = str(secret or "")
    api_key = (api_key_value or "").strip()
    if not api_key:
        return False, "OPENAI_API_KEY not configured"
    if "dummy" in api_key.lower():
        return False, "OPENAI_API_KEY is a placeholder"
    return True, None


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

        ok, reason = _indexing_available()
        if not ok:
            doc.status = "failed"
            doc.error = f"INDEXING_DISABLED: {reason}"
            db.commit()
            return

        doc.status = "indexing"
        doc.error = None
        db.commit()

        if not doc.storage_key:
            raise RuntimeError("storage_key missing")

        storage_meta = doc.meta or {}
        storage_type = storage_meta.get("storage") or (
            "s3" if _s3_configured() else "local"
        )

        if storage_type == "local":
            path_value = storage_meta.get("path") or doc.storage_key
            path = _resolve_local_path(path_value)
            if not path.exists():
                raise RuntimeError("Local document missing")
        else:
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

        db.query(Chunk).filter(Chunk.document_id == doc_id).delete(
            synchronize_session=False
        )

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
        _cleanup_file(tmp_download)
        db.close()


# =========================
# Routes (RBAC + owner_sub)
# =========================


@router.post(
    "/docs/upload",
    response_model=DocumentUploadResponse,
    dependencies=[Depends(require_permissions("write:docs"))],
)
def upload_doc(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    p: Principal = Depends(current_user),
):
    filename = _safe_filename(file.filename or "uploaded.pdf")
    _require_pdf_extension(filename)
    _require_pdf_content_type(file)

    tmp_path = TMP_DIR / f"tmp_{uuid.uuid4().hex}_{filename}"

    try:
        content_hash = _sha256_and_save_tmp(file, tmp_path)

        # ✅ dedup は user単位にする（安全側）
        existing = (
            db.query(Document)
            .filter(Document.content_hash == content_hash, Document.owner_sub == p.sub)
            .first()
        )
        if existing:
            _cleanup_file(tmp_path)
            return DocumentUploadResponse(
                document_id=existing.id,
                filename=existing.filename,
                status=existing.status,
                dedup=True,
            )

        doc_id = str(uuid.uuid4())

        if _s3_configured():
            key = _s3_key_for(doc_id, content_hash, filename)
            try:
                _s3_upload_file(tmp_path, key)
            except Exception as exc:  # noqa: BLE001
                _cleanup_file(tmp_path)
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": {
                            "code": "STORAGE_ERROR",
                            "message": f"Failed to upload to object storage: {exc}",
                        }
                    },
                ) from exc
            _cleanup_file(tmp_path)
            storage_key = key
            storage_meta = {
                "storage": "s3",
                "bucket": S3_BUCKET,
                "key": key,
                "region": AWS_REGION,
            }
        else:
            dest = _local_storage_path(doc_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.replace(dest)
            storage_key = dest.name
            storage_meta = {"storage": "local", "path": dest.name}

        doc = Document(
            id=doc_id,
            filename=filename,
            status="indexing",  # ここでindexingにして二重commitを減らす
            content_hash=content_hash,
            storage_key=storage_key,
            owner_sub=p.sub,
            meta=storage_meta,
        )
        db.add(doc)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if storage_meta.get("storage") == "s3":
                _s3_delete_object(storage_key)
            else:
                _delete_local_file(storage_meta.get("path") or storage_key)
            # 競合時：同じuser+hash ができてたらそれを返す
            existing2 = (
                db.query(Document)
                .filter(
                    Document.content_hash == content_hash, Document.owner_sub == p.sub
                )
                .first()
            )
            if existing2:
                return DocumentUploadResponse(
                    document_id=existing2.id,
                    filename=existing2.filename,
                    status=existing2.status,
                    dedup=True,
                )
            raise

        db.refresh(doc)
        ok, reason = _indexing_available()
        if not ok:
            doc.status = "failed"
            doc.error = f"INDEXING_DISABLED: {reason}"
            db.commit()
            return DocumentUploadResponse(
                document_id=doc.id,
                filename=doc.filename,
                status=doc.status,
                dedup=False,
            )

        background.add_task(index_document, doc.id)

        return DocumentUploadResponse(
            document_id=doc.id,
            filename=doc.filename,
            status=doc.status,
            dedup=False,
        )

    finally:
        try:
            file.file.close()
        except Exception:
            pass


@router.get(
    "/docs",
    response_model=list[DocumentListItem],
    dependencies=[Depends(require_permissions("read:docs"))],
)
def list_docs(
    db: Session = Depends(get_db),
    p: Principal = Depends(current_user),
):
    q = db.query(Document).order_by(Document.created_at.desc())
    if not is_admin(p):
        q = q.filter(Document.owner_sub == p.sub)

    docs = q.all()
    return [
        DocumentListItem(
            document_id=d.id,
            filename=d.filename,
            status=d.status,
            error=d.error,
        )
        for d in docs
    ]


@router.get(
    "/docs/{document_id}",
    response_model=DocumentDetailResponse,
    dependencies=[Depends(require_permissions("read:docs"))],
)
def get_doc_detail(
    document_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(current_user),
):
    doc = _get_doc_for_read(db, document_id, p)

    created_at = (
        doc.created_at.isoformat()
        if isinstance(doc.created_at, datetime)
        else str(doc.created_at)
    )
    return DocumentDetailResponse(
        document_id=doc.id,
        filename=doc.filename,
        status=doc.status,
        error=doc.error,
        content_hash=getattr(doc, "content_hash", None),
        storage_key=getattr(doc, "storage_key", None),
        meta=doc.meta,
        created_at=created_at,
    )


@router.get(
    "/docs/{document_id}/pages/{page}",
    response_model=list[DocumentPageChunkItem],
    dependencies=[Depends(require_permissions("read:docs"))],
)
def get_doc_page_chunks(
    document_id: str,
    page: int,
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    p: Principal = Depends(current_user),
):
    doc = _get_doc_for_read(db, document_id, p)
    _enforce_run_access_if_needed(db, run_id, doc.id, p)

    rows = (
        db.query(Chunk)
        .filter(Chunk.document_id == doc.id, Chunk.page == page)
        .order_by(Chunk.chunk_index.asc())
        .all()
    )
    return [
        DocumentPageChunkItem(chunk_id=r.id, chunk_index=r.chunk_index, text=r.text)
        for r in rows
    ]


@router.get(
    "/docs/{document_id}/download",
    dependencies=[Depends(require_permissions("read:docs"))],
)
def download_doc(
    document_id: str,
    run_id: str | None = None,
    db: Session = Depends(get_db),
    p: Principal = Depends(current_user),
):
    doc = _get_doc_for_read(db, document_id, p)
    _enforce_run_access_if_needed(db, run_id, doc.id, p)

    if _doc_uses_local_storage(doc):
        local_path = _resolve_local_path(
            (doc.meta or {}).get("path") or doc.storage_key
        )
        if not local_path.exists():
            _not_found()
        safe = _safe_cd_filename(doc.filename)
        return FileResponse(local_path, media_type="application/pdf", filename=safe)

    if not _s3_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "STORAGE_NOT_CONFIGURED",
                    "message": "Object storage is not configured.",
                }
            },
        )

    if not doc.storage_key:
        raise HTTPException(status_code=500, detail="storage_key missing")

    url = _s3_presign_get(doc.storage_key, inline=False, filename=doc.filename)
    return RedirectResponse(url, status_code=307)


@router.get(
    "/docs/{document_id}/view",
    dependencies=[Depends(require_permissions("read:docs"))],
)
def view_pdf(
    document_id: str,
    run_id: str | None = None,
    db: Session = Depends(get_db),
    p: Principal = Depends(current_user),
):
    doc = _get_doc_for_read(db, document_id, p)
    _enforce_run_access_if_needed(db, run_id, doc.id, p)

    if _doc_uses_local_storage(doc):
        local_path = _resolve_local_path(
            (doc.meta or {}).get("path") or doc.storage_key
        )
        if not local_path.exists():
            _not_found()
        safe = _safe_cd_filename(doc.filename)
        headers = {"Content-Disposition": f'inline; filename="{safe}"'}
        return FileResponse(local_path, media_type="application/pdf", headers=headers)

    if not _s3_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "STORAGE_NOT_CONFIGURED",
                    "message": "Object storage is not configured.",
                }
            },
        )

    if not doc.storage_key:
        raise HTTPException(status_code=500, detail="storage_key missing")

    url = _s3_presign_get(doc.storage_key, inline=True, filename=doc.filename)
    return RedirectResponse(url, status_code=307)


@router.post(
    "/docs/{document_id}/reindex",
    response_model=DocumentReindexResponse,
    dependencies=[Depends(require_permissions("write:docs"))],
)
def reindex_doc(
    document_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    p: Principal = Depends(current_user),
):
    doc = _get_doc_for_read(db, document_id, p)

    ok, reason = _indexing_available()
    if not ok:
        doc.status = "failed"
        doc.error = f"INDEXING_DISABLED: {reason}"
        db.commit()
        return DocumentReindexResponse(document_id=doc.id, queued=False, reason=reason)

    doc.status = "indexing"
    doc.error = None
    db.commit()

    background.add_task(index_document, doc.id)
    return DocumentReindexResponse(document_id=doc.id, queued=True)


@router.delete(
    "/docs/{document_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("delete:docs"))],
)
def delete_doc(
    document_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(current_user),
):
    doc = _get_doc_for_read(db, document_id, p)

    key = getattr(doc, "storage_key", None)

    try:
        # FK ON DELETE CASCADE 前提：doc deleteだけで chunks/run_documents が消える
        db.delete(doc)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Storage cleanup is best-effort.
    storage_meta = doc.meta or {}
    if storage_meta.get("storage") == "local":
        _delete_local_file(storage_meta.get("path") or key)
    elif key and _s3_configured():
        _s3_delete_object(key)

    return None
