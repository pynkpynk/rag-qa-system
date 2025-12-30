from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.core.authz import Principal, require_permissions, is_admin
from app.core.run_access import ensure_run_access
from app.db.models import Document, Run
from app.db.session import get_db
from app.schemas.api_contract import (
    RunCleanupResponse,
    RunDeleteResponse,
    RunDetailResponse,
    RunListItem,
)

router = APIRouter()

# -------------------------
# Schemas
# -------------------------

class RunCreatePayload(BaseModel):
    config: dict = Field(..., description="Run configuration JSON")
    document_ids: list[str] | None = None


class AttachDocsPayload(BaseModel):
    document_ids: list[str] = Field(..., min_length=1)

# -------------------------
# Helpers
# -------------------------

PROTECTED_STATUSES = {"running", "in_progress", "processing", "indexing"}

def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)

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
        "config": run.config or {},
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

def _fetch_docs_owned_by(db: Session, document_ids: list[str], owner_sub: str) -> list[Document]:
    """
    Attach入口の強制：
    - ここでは「run.owner_sub と doc.owner_sub が一致するdocのみ」取得する
    - 一致しない/存在しない/legacy(NULL)はまとめて 400 にして存在推測を防ぐ
    """
    uniq = list(dict.fromkeys(document_ids))
    docs = (
        db.query(Document)
        .filter(Document.id.in_(uniq), Document.owner_sub == owner_sub)
        .all()
    )
    if len(docs) != len(uniq):
        raise HTTPException(status_code=400, detail="one or more document_ids not found")
    return docs

def _get_run_for_update(db: Session, run_id: str, p: Principal) -> Run:
    """
    - 非admin: ensure_run_access で 404/拒否
    - admin: ensure_run_access が許可する前提（もし実装がadminバイパス無しならここを調整）
    """
    ensure_run_access(db, run_id, p)
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run

# -------------------------
# Routes
# -------------------------

@router.get("/runs", response_model=list[RunListItem])
def list_runs(
    limit: int = Query(50, ge=1, le=500, description="Max number of runs to return"),
    all_runs: bool = Query(False, alias="all", description="Admin only: list all runs"),
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("read:docs")),
):
    # ✅ filter → order_by → limit の順（SQLAlchemy 2系の事故回避）
    q = (
        db.query(Run)
        .options(selectinload(Run.documents))  # run.documents 参照のN+1回避
    )

    # 基本は自分のrunのみ（admin + all=true の時だけ全件）
    if not (all_runs and is_admin(p)):
        q = q.filter(Run.owner_sub == p.sub)

    q = q.order_by(Run.created_at.desc()).limit(limit)

    runs = q.all()
    return [_serialize_run_list(r) for r in runs]

@router.post("/runs", response_model=RunDetailResponse)
def create_run(
    payload: RunCreatePayload,
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("write:docs")),
):
    """
    Create a run.
    - owner_sub は必ず入れる（multi-tenant）
    - document_ids があれば同時attach（ただし run.owner_sub のdocのみ）
    - indexed docsのみ許可（run has docs but no chunks を避ける）
    """
    run = Run(
        id=str(uuid.uuid4()),
        owner_sub=p.sub,
        config=payload.config,
        status="created",
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()

    if payload.document_ids:
        docs = _fetch_docs_owned_by(db, payload.document_ids, owner_sub=run.owner_sub)
        _require_indexed_docs(docs)
        for d in docs:
            run.documents.append(d)

    db.commit()
    db.refresh(run)
    return _serialize_run_detail(run)

@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("read:docs")),
):
    run = _get_run_for_update(db, run_id, p)
    return _serialize_run_detail(run)

@router.post("/runs/{run_id}/attach_docs", response_model=RunDetailResponse)
def attach_docs(
    run_id: str,
    payload: AttachDocsPayload,
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("write:docs")),
):
    run = _get_run_for_update(db, run_id, p)

    docs = _fetch_docs_owned_by(db, payload.document_ids, owner_sub=run.owner_sub)
    _require_indexed_docs(docs)

    existing = {d.id for d in run.documents}
    for d in docs:
        if d.id not in existing:
            run.documents.append(d)

    db.commit()
    db.refresh(run)
    return _serialize_run_detail(run)

@router.delete("/runs/{run_id}", response_model=RunDeleteResponse)
def delete_run(
    run_id: str,
    confirm: str | None = Query(None, description='Required: "DELETE"'),
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("delete:docs")),
):
    _require_confirm(confirm)

    run = _get_run_for_update(db, run_id, p)

    if (run.status or "").lower() in PROTECTED_STATUSES:
        raise HTTPException(status_code=409, detail=f"run is active (status={run.status}); refuse to delete")

    run.documents.clear()
    db.flush()

    db.delete(run)
    db.commit()
    return {"deleted": True, "run_id": run_id}

@router.delete("/runs", response_model=RunCleanupResponse)
def cleanup_runs(
    older_than_days: int = Query(7, ge=0, le=3650, description="Delete runs older than N days"),
    dry_run: bool = Query(True, description="Default true (safe). Set false to actually delete."),
    confirm: str | None = Query(None, description='Required when dry_run=false: "DELETE"'),
    limit: int = Query(200, ge=1, le=2000, description="Max runs to delete in one call"),
    all_runs: bool = Query(False, alias="all", description="Admin only: cleanup all users' runs"),
    db: Session = Depends(get_db),
    p: Principal = Depends(require_permissions("delete:docs")),
):
    if not dry_run:
        _require_confirm(confirm)

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    # ✅ filter → order_by → limit の順（SQLAlchemy 2系の事故回避）
    q = (
        db.query(Run)
        .options(selectinload(Run.documents))
        .filter(Run.created_at < cutoff)
    )

    if not (all_runs and is_admin(p)):
        q = q.filter(Run.owner_sub == p.sub)

    q = q.order_by(Run.created_at.asc()).limit(limit)

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
