from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Document, Run
from app.db.session import get_db

router = APIRouter()

# -------------------------
# Schemas
# -------------------------

class RunCreatePayload(BaseModel):
    config: dict = Field(..., description="Run configuration JSON")
    document_ids: list[str] | None = None

class AttachDocsPayload(BaseModel):
    document_ids: list[str] = Field(..., min_length=1)

class RunListItem(BaseModel):
    run_id: str
    created_at: str
    status: str
    document_ids: list[str]

class RunDetailResponse(BaseModel):
    run_id: str
    created_at: str
    config: dict[str, Any]
    status: str
    error: str | None
    document_ids: list[str]

# -------------------------
# Helpers
# -------------------------

PROTECTED_STATUSES = {"running", "in_progress", "processing", "indexing"}

def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)

def _fetch_documents_or_400(db: Session, document_ids: list[str]) -> list[Document]:
    docs = db.query(Document).filter(Document.id.in_(document_ids)).all()
    if len(docs) != len(set(document_ids)):
        raise HTTPException(status_code=400, detail="one or more document_ids not found")
    return docs

def _require_indexed_docs(docs: list[Document]) -> None:
    not_indexed = [d.id for d in docs if (d.status or "").lower() != "indexed"]
    if not_indexed:
        raise HTTPException(
            status_code=400,
            detail=f"one or more documents are not indexed yet: {', '.join(not_indexed)}",
        )

def _serialize_run_list(run: Run) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "created_at": _iso(run.created_at),
        "status": run.status,
        "document_ids": [d.id for d in run.documents],
    }

def _serialize_run_detail(run: Run) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "created_at": _iso(run.created_at),
        "config": run.config,
        "status": run.status,
        "error": run.error,
        "document_ids": [d.id for d in run.documents],
    }

def _require_confirm(confirm: str | None) -> None:
    if confirm != "DELETE":
        raise HTTPException(
            status_code=400,
            detail='Destructive operation. Add query "?confirm=DELETE" to proceed.',
        )

# -------------------------
# Routes
# -------------------------

@router.get("/runs", response_model=list[RunListItem])
def list_runs(
    limit: int = Query(50, ge=1, le=500, description="Max number of runs to return"),
    db: Session = Depends(get_db),
):
    runs = db.query(Run).order_by(Run.created_at.desc()).limit(limit).all()
    return [_serialize_run_list(r) for r in runs]

@router.post("/runs", response_model=RunDetailResponse)
def create_run(payload: RunCreatePayload, db: Session = Depends(get_db)):
    """
    Create a run (experiment config).
    Optionally attach documents at creation.
    NOTE (P04): we enforce indexed docs only to avoid "run has docs but no chunks" issues.
    """
    run = Run(config=payload.config, status="created")
    db.add(run)
    db.flush()  # assign run.id

    if payload.document_ids:
        docs = _fetch_documents_or_400(db, payload.document_ids)
        _require_indexed_docs(docs)
        for d in docs:
            run.documents.append(d)

    db.commit()
    db.refresh(run)
    return _serialize_run_detail(run)

@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return _serialize_run_detail(run)

@router.post("/runs/{run_id}/attach_docs", response_model=RunDetailResponse)
def attach_docs(run_id: str, payload: AttachDocsPayload, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    docs = _fetch_documents_or_400(db, payload.document_ids)
    _require_indexed_docs(docs)

    existing = {d.id for d in run.documents}
    for d in docs:
        if d.id not in existing:
            run.documents.append(d)

    db.commit()
    db.refresh(run)
    return _serialize_run_detail(run)

@router.delete("/runs/{run_id}")
def delete_run(
    run_id: str,
    confirm: str | None = Query(None, description='Required: "DELETE"'),
    db: Session = Depends(get_db),
):
    """
    Delete a single run safely.
    - Requires ?confirm=DELETE
    - Refuses deletion if run.status indicates it's active (best-effort safety).
    """
    _require_confirm(confirm)

    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    if (run.status or "").lower() in PROTECTED_STATUSES:
        raise HTTPException(status_code=409, detail=f"run is active (status={run.status}); refuse to delete")

    run.documents.clear()
    db.flush()

    db.delete(run)
    db.commit()
    return {"deleted": True, "run_id": run_id}

@router.delete("/runs")
def cleanup_runs(
    older_than_days: int = Query(7, ge=0, le=3650, description="Delete runs older than N days"),
    dry_run: bool = Query(True, description="Default true (safe). Set false to actually delete."),
    confirm: str | None = Query(None, description='Required when dry_run=false: "DELETE"'),
    limit: int = Query(200, ge=1, le=2000, description="Max runs to delete in one call"),
    db: Session = Depends(get_db),
):
    """
    Bulk cleanup runs older than N days.
    SAFE BY DEFAULT:
      - dry_run=true returns candidates only
      - to delete: dry_run=false&confirm=DELETE
    Best-effort: skips active statuses.
    """
    if not dry_run:
        _require_confirm(confirm)

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    q = (
        db.query(Run)
        .filter(Run.created_at < cutoff)
        .order_by(Run.created_at.asc())
        .limit(limit)
    )
    candidates: list[Run] = q.all()

    deletable: list[Run] = []
    skipped: list[dict[str, Any]] = []
    for r in candidates:
        if (r.status or "").lower() in PROTECTED_STATUSES:
            skipped.append({"run_id": r.id, "status": r.status, "created_at": _iso(r.created_at)})
        else:
            deletable.append(r)

    if dry_run:
        return {
            "dry_run": True,
            "older_than_days": older_than_days,
            "cutoff_utc": cutoff.isoformat(),
            "limit": limit,
            "candidates": [_serialize_run_list(r) for r in deletable],
            "skipped": skipped,
            "count": len(deletable),
        }

    deleted_ids: list[str] = []
    for r in deletable:
        r.documents.clear()
        db.flush()
        db.delete(r)
        deleted_ids.append(r.id)

    db.commit()
    return {
        "dry_run": False,
        "older_than_days": older_than_days,
        "cutoff_utc": cutoff.isoformat(),
        "deleted_count": len(deleted_ids),
        "deleted_run_ids": deleted_ids,
        "skipped": skipped,
    }
