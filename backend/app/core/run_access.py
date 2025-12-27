from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.core.authz import Principal, is_admin

SQL_GET_RUN_OWNER = "SELECT owner_sub FROM runs WHERE id = :run_id"

def ensure_run_access(db: Session, run_id: str, p: Principal) -> None:
    """
    - admin: OK
    - non-admin: runs.owner_sub == p.sub のみOK
    - legacy(owner_sub NULL): adminのみOK（non-adminは404）
    """
    if is_admin(p):
        return

    row = db.execute(sql_text(SQL_GET_RUN_OWNER), {"run_id": run_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="run not found")

    owner_sub = row.get("owner_sub")
    if not owner_sub:
        raise HTTPException(status_code=404, detail="run not found")  # legacyは隠す
    if owner_sub != p.sub:
        raise HTTPException(status_code=404, detail="run not found")
