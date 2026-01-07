from __future__ import annotations

import logging
from uuid import UUID

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.core.authz import Principal, require_permissions, is_admin
from app.core.run_access import ensure_run_access
from app.core.text_utils import strip_control_chars
from app.db.models import Chunk, Document, Run
from app.db.session import get_db
from app.schemas.api_contract import ChunkHealthResponse, ChunkResponse

logger = logging.getLogger(__name__)

router = APIRouter()
__all__ = ["router"]  # import事故の保険


# ------------------------------------------------------------
# SQL helpers (run scoping)
#   run_documents/run_id/document_id が varchar の前提で "文字列比較" に統一
# ------------------------------------------------------------

SQL_RUN_DOC_COUNT_ADMIN = """
SELECT COUNT(*)::int AS cnt
FROM run_documents
WHERE run_id = :run_id
"""

SQL_RUN_DOC_COUNT_USER = """
SELECT COUNT(*)::int AS cnt
FROM run_documents rd
JOIN documents d ON d.id = rd.document_id
WHERE rd.run_id = :run_id
  AND d.owner_sub = :owner_sub
"""

SQL_DOC_ATTACHED_TO_RUN = """
SELECT EXISTS(
  SELECT 1
  FROM run_documents
  WHERE run_id = :run_id AND document_id = :document_id
) AS ok
"""


# ------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------


def _not_found() -> None:
    raise HTTPException(status_code=404, detail="not found")


def _db_get_flexible(db: Session, model, key):
    """
    PKが uuid 型でも varchar 型でも取り逃しにくくする。
    """
    obj = None
    try:
        obj = db.get(model, key)
        if obj is not None:
            return obj
    except Exception:
        pass

    # UUID -> str, str -> UUID の両方向を試す
    try:
        if isinstance(key, UUID):
            obj = db.get(model, str(key))
        else:
            obj = db.get(model, UUID(str(key)))
    except Exception:
        obj = None
    return obj


def _ensure_run_exists(db: Session, run_id: UUID) -> Run:
    run = _db_get_flexible(db, Run, run_id)
    if not run:
        _not_found()
    return run


def _ensure_run_has_docs(db: Session, run_id: UUID, p: Principal) -> None:
    run_id_s = str(run_id)

    try:
        if is_admin(p):
            cnt = db.execute(
                sql_text(SQL_RUN_DOC_COUNT_ADMIN), {"run_id": run_id_s}
            ).scalar_one()
        else:
            cnt = db.execute(
                sql_text(SQL_RUN_DOC_COUNT_USER),
                {"run_id": run_id_s, "owner_sub": p.sub},
            ).scalar_one()
    except Exception:
        logger.exception("failed to count run_documents")
        raise HTTPException(status_code=500, detail="failed to count run_documents")

    if int(cnt) == 0:
        raise HTTPException(
            status_code=400,
            detail="This run_id has no attached documents. Attach docs first via /api/runs/{run_id}/attach_docs.",
        )


def _ensure_doc_readable(db: Session, document_id, p: Principal) -> Document:
    """
    - admin: 任意doc OK（legacy含む）
    - non-admin: owner_sub == p.sub のdocのみ
    - legacy(owner_sub NULL) は admin のみ（non-adminは404）
    """
    # document_id は Chunk.document_id の型に依存（uuid/strどちらでも来る）
    doc_id_s = str(document_id)

    if is_admin(p):
        doc = _db_get_flexible(db, Document, document_id)
        if not doc:
            doc = _db_get_flexible(db, Document, doc_id_s)
        if not doc:
            _not_found()
        return doc

    doc = (
        db.query(Document)
        .filter(Document.id == doc_id_s, Document.owner_sub == p.sub)
        .first()
    )
    if not doc:
        _not_found()
    return doc


def _ensure_chunk_accessible_for_run(
    db: Session, run_id: UUID, document_id, p: Principal
) -> None:
    run_id_s = str(run_id)
    doc_id_s = str(document_id)

    # ① run_id 自体が自分のものか（非ownerは404）
    ensure_run_access(db, run_id_s, p)

    # ② run_documentsに紐づいてるか
    row = (
        db.execute(
            sql_text(SQL_DOC_ATTACHED_TO_RUN),
            {"run_id": run_id_s, "document_id": doc_id_s},
        )
        .mappings()
        .first()
    )

    ok = bool(row and row.get("ok"))
    if not ok:
        _not_found()


def _safe_bool_query(db: Session, sql: str) -> bool | None:
    try:
        result = db.execute(sql_text(sql)).scalar()
    except Exception:
        return None
    if result is None:
        return None
    return bool(result)


def _get_alembic_head() -> str | None:
    try:
        backend_dir = Path(__file__).resolve().parents[3]
        cfg = Config(str(backend_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        script = ScriptDirectory.from_config(cfg)
        return script.get_current_head()
    except Exception:
        return None


def _build_db_status(db: Session) -> dict:
    status = {
        "dialect": None,
        "alembic_revision": None,
        "alembic_head": None,
        "is_alembic_head": None,
        "chunks_fts_column": None,
        "fts_gin_index": None,
        "pg_trgm_installed": None,
        "text_trgm_index": None,
    }
    try:
        bind = db.get_bind()
    except Exception:
        bind = None
    if bind is None:
        return status

    dialect = getattr(getattr(bind, "dialect", None), "name", None)
    if dialect:
        status["dialect"] = dialect

    try:
        version = db.execute(
            sql_text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalar()
        status["alembic_revision"] = version
    except Exception:
        status["alembic_revision"] = None

    head = _get_alembic_head()
    status["alembic_head"] = head
    if status["alembic_revision"] and head:
        status["is_alembic_head"] = status["alembic_revision"] == head
    else:
        status["is_alembic_head"] = None

    if dialect != "postgresql":
        return status

    status["chunks_fts_column"] = _safe_bool_query(
        db,
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'chunks'
          AND column_name = 'fts'
          AND table_schema = current_schema()
        LIMIT 1
        """,
    )
    status["fts_gin_index"] = _safe_bool_query(
        db,
        """
        SELECT 1
        FROM pg_indexes
        WHERE tablename = 'chunks'
          AND schemaname = current_schema()
          AND indexdef ILIKE '%USING gin%'
          AND indexdef ILIKE '%fts%'
        LIMIT 1
        """,
    )
    status["text_trgm_index"] = _safe_bool_query(
        db,
        """
        SELECT 1
        FROM pg_indexes
        WHERE tablename = 'chunks'
          AND schemaname = current_schema()
          AND indexdef ILIKE '%trgm_ops%'
        LIMIT 1
        """,
    )
    status["pg_trgm_installed"] = _safe_bool_query(
        db,
        """
        SELECT 1
        FROM pg_extension
        WHERE extname = 'pg_trgm'
        LIMIT 1
        """,
    )
    return status


# ------------------------------------------------------------
# Route
# ------------------------------------------------------------


@router.get("/chunks/health", response_model=ChunkHealthResponse)
def chunks_health(
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("read:docs")),
) -> ChunkHealthResponse:
    db_status = _build_db_status(db)
    return ChunkHealthResponse(
        ok=True, principal_sub=getattr(p, "sub", None), db=db_status
    )


@router.get("/chunks/{chunk_id}", response_model=ChunkResponse)
def get_chunk(
    chunk_id: UUID,
    run_id: UUID | None = Query(
        default=None,
        description="Optional: restrict access to chunks attached to this run",
    ),
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("read:docs")),
) -> ChunkResponse:
    chunk = _db_get_flexible(db, Chunk, chunk_id)
    if not chunk:
        _not_found()

    # doc所有権チェック（run_idの有無に関わらず defense-in-depth）
    doc = _ensure_doc_readable(db, chunk.document_id, p)

    if run_id is not None:
        _ensure_run_exists(db, run_id)
        _ensure_run_has_docs(db, run_id, p)
        _ensure_chunk_accessible_for_run(db, run_id, chunk.document_id, p)

    return ChunkResponse(
        chunk_id=str(chunk.id),
        document_id=str(chunk.document_id),
        filename=getattr(doc, "filename", None),
        page=getattr(chunk, "page", None),
        chunk_index=int(getattr(chunk, "chunk_index", 0)),
        text=strip_control_chars(getattr(chunk, "text", "")),
    )
