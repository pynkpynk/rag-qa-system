from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Tuple

import boto3
from botocore.exceptions import ClientError
from pypdf import PdfReader, PdfWriter

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
import httpx
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import Principal, current_user, is_admin, require_permissions
from app.core.config import settings
from app.core.run_access import ensure_run_access
from app.db.models import Chunk, Document
from app.db.session import SessionLocal, get_db
from app.schemas.api_contract import (
    DocumentDetailResponse,
    DocumentListItem,
    DocumentPageChunkItem,
    DocumentReindexResponse,
    DocumentUploadResponse,
)
from app.services.indexing import embed_texts, extract_pdf_pages, simple_chunk

router = APIRouter()
logger = logging.getLogger(__name__)
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "16") or "16")


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be processed even after normalization."""


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


def _normalize_pdf_bytes(raw: bytes) -> bytes:
    reader = PdfReader(BytesIO(raw))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _extract_pdf_pages_with_normalization(
    pdf_path: Path, *, request_id: str
) -> list[tuple[int | None, str]]:
    try:
        return extract_pdf_pages(str(pdf_path))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pdf_extract_first_pass_failed",
            extra={"request_id": request_id, "path": str(pdf_path), "error": str(exc)},
        )
        try:
            raw = pdf_path.read_bytes()
            normalized_bytes = _normalize_pdf_bytes(raw)
        except Exception as norm_exc:  # noqa: BLE001
            logger.exception(
                "pdf_normalization_failed",
                extra={"request_id": request_id, "path": str(pdf_path)},
            )
            raise PDFExtractionError("PDF_PARSE_FAILED") from norm_exc

        normalized_path = TMP_DIR / f"normalized_{uuid.uuid4().hex}.pdf"
        try:
            normalized_path.write_bytes(normalized_bytes)
            return extract_pdf_pages(str(normalized_path))
        except Exception as second_exc:  # noqa: BLE001
            logger.exception(
                "pdf_extract_failed_after_normalization",
                extra={"request_id": request_id, "path": str(pdf_path)},
            )
            raise PDFExtractionError("PDF_PARSE_FAILED") from second_exc
        finally:
            _cleanup_file(normalized_path)


def _ensure_request_id(request: Request | None) -> str:
    if request is None:
        return str(uuid.uuid4())
    rid = getattr(request.state, "request_id", None)
    if rid:
        return rid
    header_id = request.headers.get("x-request-id") or request.headers.get(
        "X-Request-ID"
    )
    if header_id:
        return header_id
    return str(uuid.uuid4())


def _log_stage_failure(
    stage: str, request_id: str, doc: Document | None, exc: Exception
) -> None:
    logger.exception(
        "document_stage_failed",
        extra={
            "stage": stage,
            "request_id": request_id,
            "document_id": getattr(doc, "id", None),
            "owner_sub": getattr(doc, "owner_sub", None),
        },
    )


def _handle_stage_failure(
    stage: str,
    exc: Exception,
    *,
    request_id: str,
    db: Session | None,
    doc: Document | None,
    raise_http: bool,
    status_code: int = 500,
) -> None:
    safe_message = _truncate_err(exc)
    _log_stage_failure(stage, request_id, doc, exc)
    if doc is not None and db is not None:
        try:
            doc.status = "error"
            doc.error = f"{stage}: {safe_message}"
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    detail = {
        "error": {
            "code": "UPLOAD_INDEX_FAILED",
            "message": f"Document processing failed at stage '{stage}'.",
            "stage": stage,
            "request_id": request_id,
            "reason": safe_message,
        }
    }
    if raise_http:
        raise HTTPException(status_code=status_code, detail=detail)


def _chunk_pdf_pages(
    pages: list[tuple[int | None, str]],
) -> tuple[list[str], list[tuple[int | None, int, str]]]:
    texts: list[str] = []
    metas: list[tuple[int | None, int, str]] = []
    for page_no, page_text in pages:
        chunks = simple_chunk(page_text or "")
        for idx, chunk in enumerate(chunks):
            if not chunk:
                continue
            texts.append(chunk)
            metas.append((page_no, idx, chunk))
    return texts, metas


def embed_texts_batched(
    texts: list[str], batch_size: int | None = None
) -> list[list[float]]:
    if not texts:
        return []
    size = batch_size or EMBED_BATCH_SIZE
    try:
        size = max(1, int(size))
    except Exception:
        size = EMBED_BATCH_SIZE

    vectors: list[list[float]] = []
    for start in range(0, len(texts), size):
        batch = texts[start : start + size]
        vec_batch = embed_texts(batch)
        if not isinstance(vec_batch, list) or len(vec_batch) != len(batch):
            raise RuntimeError("embedding batch size mismatch")
        vectors.extend(vec_batch)
    return vectors


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


def _process_document_content(
    *,
    db: Session,
    doc: Document,
    pdf_path: Path,
    skip_embedding: bool,
    request_id: str,
    raise_http: bool,
) -> None:
    try:
        pages = _extract_pdf_pages_with_normalization(pdf_path, request_id=request_id)
    except PDFExtractionError as exc:
        _handle_stage_failure(
            "extract_pdf_pages",
            exc,
            request_id=request_id,
            db=db,
            doc=doc,
            raise_http=raise_http,
            status_code=422,
        )
        return
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _handle_stage_failure(
            "extract_pdf_pages",
            exc,
            request_id=request_id,
            db=db,
            doc=doc,
            raise_http=raise_http,
            status_code=422,
        )
        return

    if not pages:
        _handle_stage_failure(
            "extract_pdf_pages",
            RuntimeError("No extractable content found in PDF."),
            request_id=request_id,
            db=db,
            doc=doc,
            raise_http=raise_http,
            status_code=422,
        )
        return

    try:
        texts, metas = _chunk_pdf_pages(pages)
    except Exception as exc:  # noqa: BLE001
        _handle_stage_failure(
            "chunk_text",
            exc,
            request_id=request_id,
            db=db,
            doc=doc,
            raise_http=raise_http,
            status_code=422,
        )
        return

    if not texts:
        _handle_stage_failure(
            "chunk_text",
            RuntimeError("No chunkable text found in PDF."),
            request_id=request_id,
            db=db,
            doc=doc,
            raise_http=raise_http,
            status_code=422,
        )
        return

    if skip_embedding:
        embeddings: list[list[float] | None] = [None] * len(texts)
    else:
        try:
            embeddings = embed_texts_batched(texts)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            _handle_stage_failure(
                "embed_chunks",
                exc,
                request_id=request_id,
                db=db,
                doc=doc,
                raise_http=raise_http,
            )
            return

    try:
        db.query(Chunk).filter(Chunk.document_id == doc.id).delete(
            synchronize_session=False
        )
        for idx, (page_no, chunk_idx, chunk_text) in enumerate(metas):
            db.add(
                Chunk(
                    document_id=doc.id,
                    page=page_no,
                    chunk_index=chunk_idx,
                    text=chunk_text,
                    embedding=embeddings[idx],
                )
            )
        doc.status = "indexed_fts_only" if skip_embedding else "indexed"
        doc.error = None
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:
            pass
        _handle_stage_failure(
            "persist_chunks",
            exc,
            request_id=request_id,
            db=db,
            doc=doc,
            raise_http=raise_http,
        )


# =========================
# Background Task
# =========================


def index_document(doc_id: str, *, skip_embedding: bool = False) -> None:
    db = SessionLocal()
    tmp_download: Path | None = None
    doc: Document | None = None
    request_id = f"reindex-{doc_id}"
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return

        doc.status = "indexing"
        doc.error = None
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()

        if not skip_embedding:
            ok, reason = _indexing_available()
            if not ok:
                doc.status = "error"
                doc.error = f"INDEXING_DISABLED: {reason}"
                db.commit()
                return

        if not doc.storage_key:
            raise RuntimeError("storage_key missing")

        storage_meta = doc.meta or {}
        storage_type = storage_meta.get("storage") or (
            "s3" if _s3_configured() else "local"
        )

        if storage_type == "local":
            path_value = storage_meta.get("path") or doc.storage_key
            processing_path = _resolve_local_path(path_value)
            if not processing_path.exists():
                raise RuntimeError("Local document missing")
        else:
            try:
                tmp_download = _s3_download_to_tmp(doc.storage_key, suffix=".pdf")
                processing_path = tmp_download
            except ClientError as e:
                raise RuntimeError(f"S3 download failed: {e}") from e

        _process_document_content(
            db=db,
            doc=doc,
            pdf_path=processing_path,
            skip_embedding=skip_embedding,
            request_id=request_id,
            raise_http=False,
        )

    except Exception as exc:  # noqa: BLE001
        _handle_stage_failure(
            "prepare_document",
            exc,
            request_id=request_id,
            db=db,
            doc=doc,
            raise_http=False,
        )
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
    request: Request,
    _background: BackgroundTasks,
    file: UploadFile = File(...),
    skip_embedding: bool = Query(
        default=False, description="Skip vector embeddings for debugging."
    ),
    db: Session = Depends(get_db),
    p: Principal = Depends(current_user),
):
    filename = _safe_filename(file.filename or "uploaded.pdf")
    _require_pdf_extension(filename)
    _require_pdf_content_type(file)

    request_id = _ensure_request_id(request)
    tmp_path = TMP_DIR / f"tmp_{uuid.uuid4().hex}_{filename}"
    cleanup_path: Path | None = tmp_path
    doc: Document | None = None
    processing_path: Path = tmp_path

    try:
        try:
            content_hash = _sha256_and_save_tmp(file, tmp_path)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            _handle_stage_failure(
                "save_file",
                exc,
                request_id=request_id,
                db=None,
                doc=None,
                raise_http=True,
            )
            return  # never reached

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
            processing_path = dest
            cleanup_path = None
            storage_key = dest.name
            storage_meta = {"storage": "local", "path": dest.name}

        doc = Document(
            id=doc_id,
            filename=filename,
            status="indexing",
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
            detail = {
                "error": {
                    "code": "DUPLICATE_DOCUMENT",
                    "message": "Document already exists.",
                    "request_id": request_id,
                }
            }
            raise HTTPException(status_code=409, detail=detail)

        db.refresh(doc)
        ok, reason = _indexing_available()
        if not skip_embedding and not ok:
            doc.status = "error"
            doc.error = f"INDEXING_DISABLED: {reason}"
            db.commit()
            detail = {
                "error": {
                    "code": "UPLOAD_INDEX_FAILED",
                    "message": "Embedding is not configured for this environment.",
                    "stage": "embed_chunks",
                    "request_id": request_id,
                    "reason": reason,
                }
            }
            raise HTTPException(status_code=503, detail=detail)

        _process_document_content(
            db=db,
            doc=doc,
            pdf_path=processing_path,
            skip_embedding=skip_embedding,
            request_id=request_id,
            raise_http=True,
        )
        db.refresh(doc)

        return DocumentUploadResponse(
            document_id=doc.id,
            filename=doc.filename,
            status=doc.status,
            dedup=False,
        )

    finally:
        if cleanup_path:
            _cleanup_file(cleanup_path)
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


@router.get(
    "/docs/{document_id}/content",
    dependencies=[Depends(require_permissions("read:docs"))],
)
def proxy_pdf_content(
    document_id: str,
    request: Request,
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
    headers = {}
    range_header = request.headers.get("range")
    if range_header:
        headers["range"] = range_header

    try:
        with httpx.stream("GET", url, headers=headers, timeout=30.0) as resp:
            if resp.status_code not in (200, 206):
                detail = resp.text
                raise HTTPException(status_code=resp.status_code, detail=detail)
            response_headers = {
                "Content-Type": resp.headers.get("content-type", "application/pdf"),
                "Content-Disposition": f"inline; filename=\"{_safe_cd_filename(doc.filename)}\"",
            }
            if resp.status_code == 206:
                if "content-range" in resp.headers:
                    response_headers["Content-Range"] = resp.headers["content-range"]
                if "accept-ranges" in resp.headers:
                    response_headers["Accept-Ranges"] = resp.headers["accept-ranges"]
                if "content-length" in resp.headers:
                    response_headers["Content-Length"] = resp.headers["content-length"]
            return StreamingResponse(
                resp.iter_raw(),
                status_code=resp.status_code,
                media_type="application/pdf",
                headers=response_headers,
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("pdf_proxy_failed", extra={"doc_id": doc.id})
        raise HTTPException(status_code=502, detail="Failed to fetch document") from exc


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
        db.delete(doc)
        db.commit()
    except Exception:
        db.rollback()
        raise

    storage_meta = doc.meta or {}
    if storage_meta.get("storage") == "local":
        _delete_local_file(storage_meta.get("path") or key)
    elif key and _s3_configured():
        _s3_delete_object(key)

    return None
