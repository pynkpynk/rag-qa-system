# app/deps.py
from __future__ import annotations

from typing import Callable, Iterable, Optional, Set

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.auth0 import AuthError, Principal, decode_access_token

bearer = HTTPBearer(auto_error=False)

def get_principal(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Principal:
    if cred is None or cred.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        return decode_access_token(cred.credentials)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def require_perms(*needed: str) -> Callable[[Principal], Principal]:
    needed_set: Set[str] = set(needed)

    def _dep(p: Principal = Depends(get_principal)) -> Principal:
        # adminはスキップしたいならここで許容
        if p.is_admin:
            return p
        if not needed_set.issubset(p.permissions):
            raise HTTPException(status_code=403, detail="Insufficient scope/permissions")
        return p

    return _dep
