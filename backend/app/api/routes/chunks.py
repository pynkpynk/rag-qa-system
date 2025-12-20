from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, Run
from app.db.session import get_db

router = APIRouter()

# ------------------------------------------------------------
# SQL helpers (run scoping)
# ------------------------------------------------------------

SQL_RUN_DOC_COUNT = """
SELECT COUNT(*) AS cnt
FROM run_documents
WHERE run_id = :run_id
"""

SQL_DOC_ATTACHED_TO_RUN = """
SELECT EXISTS(
  SELECT 1
  FROM run_documents
  WHERE run_id = :run_id AND document_id = :document_id
) AS ok
"""


# ------------------------------------------------------------
# Response model (固定スキーマで返す)
# ------------------------------------------------------------

class ChunkResponse(BaseModel):
    chunk_id: str
    document_id: str
    filename: str | None
    page: int | None
    chunk_index: int
    text: str


# ------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------

def _ensure_run_exists(db: Session, run_id: str) -> None:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

def _ensure_run_has_docs(db: Session, run_id: str) -> None:
    row = db.execute(sql_text(SQL_RUN_DOC_COUNT), {"run_id": run_id}).mappings().first()
    if not row or int(row["cnt"]) == 0:
        raise HTTPException(
            status_code=400,
            detail="This run_id has no attached documents. Attach docs first via /api/runs/{run_id}/attach_docs.",
        )

def _ensure_chunk_accessible_for_run(db: Session, run_id: str, document_id: str) -> None:
    row = db.execute(
        sql_text(SQL_DOC_ATTACHED_TO_RUN),
        {"run_id": run_id, "document_id": document_id},
    ).mappings().first()

    ok = bool(row and row.get("ok"))
    if not ok:
        raise HTTPException(status_code=403, detail="chunk not accessible for this run_id")


# ------------------------------------------------------------
# Route
# ------------------------------------------------------------

@router.get("/chunks/{chunk_id}", response_model=ChunkResponse)
def get_chunk(
    chunk_id: str,
    run_id: str | None = Query(
        default=None,
        description="Optional: restrict access to chunks attached to this run",
    ),
    db: Session = Depends(get_db),
):
    """
    Fetch a chunk for citation drill-down (front-end: click citation).
    If run_id is provided, enforce that the chunk's document is attached to the run.
    """
    chunk = db.get(Chunk, chunk_id)
    if not chunk:
        raise HTTPException(status_code=404, detail="chunk not found")

    if run_id:
        _ensure_run_exists(db, run_id)
        _ensure_run_has_docs(db, run_id)
        _ensure_chunk_accessible_for_run(db, run_id, chunk.document_id)

    doc = db.get(Document, chunk.document_id)
    filename = doc.filename if doc else None

    return ChunkResponse(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        filename=filename,
        page=chunk.page,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
    )
