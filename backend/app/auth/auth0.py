# app/auth/auth0.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

import httpx
from jose import jwt

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "").strip()
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "").strip()
AUTH0_ISSUER = os.getenv("AUTH0_ISSUER", "").strip()  # 例: https://YOUR_DOMAIN/
AUTH0_ALGORITHMS = os.getenv("AUTH0_ALGORITHMS", "RS256").split(",")

ADMIN_SUBS = {s.strip() for s in os.getenv("ADMIN_SUBS", "").split(",") if s.strip()}

_JWKS_CACHE: Dict[str, Any] = {"jwks": None, "exp": 0.0}
_JWKS_TTL_SEC = 60 * 60  # 1h

class AuthError(Exception):
    pass

@dataclass(frozen=True)
class Principal:
    sub: str
    permissions: Set[str]
    is_admin: bool

def _jwks_url() -> str:
    if not AUTH0_DOMAIN:
        raise AuthError("AUTH0_DOMAIN is not set")
    return f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"

def _get_jwks() -> Dict[str, Any]:
    now = time.time()
    if _JWKS_CACHE["jwks"] and now < _JWKS_CACHE["exp"]:
        return _JWKS_CACHE["jwks"]

    with httpx.Client(timeout=10.0) as client:
        r = client.get(_jwks_url())
        r.raise_for_status()
        jwks = r.json()

    _JWKS_CACHE["jwks"] = jwks
    _JWKS_CACHE["exp"] = now + _JWKS_TTL_SEC
    return jwks

def _pick_key(jwks: Dict[str, Any], kid: str) -> Dict[str, Any]:
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k
    raise AuthError("Matching JWKS key not found")

def _extract_permissions(payload: Dict[str, Any]) -> Set[str]:
    # Auth0 RBAC: "permissions": ["read:docs", ...]
    perms = payload.get("permissions")
    if isinstance(perms, list):
        return {p for p in perms if isinstance(p, str)}

    # fallback: "scope": "read:docs write:docs"
    scope = payload.get("scope")
    if isinstance(scope, str):
        return set(scope.split())

    return set()

def decode_access_token(token: str) -> Principal:
    if not AUTH0_AUDIENCE or not AUTH0_ISSUER:
        raise AuthError("AUTH0_AUDIENCE / AUTH0_ISSUER is not set")

    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not kid:
        raise AuthError("No kid in token header")

    jwks = _get_jwks()
    key = _pick_key(jwks, kid)

    payload = jwt.decode(
        token,
        key,
        algorithms=AUTH0_ALGORITHMS,
        audience=AUTH0_AUDIENCE,
        issuer=AUTH0_ISSUER,
    )

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise AuthError("No sub in token")

    permissions = _extract_permissions(payload)
    is_admin = sub in ADMIN_SUBS
    return Principal(sub=sub, permissions=permissions, is_admin=is_admin)
