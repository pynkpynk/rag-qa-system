from __future__ import annotations

import os
import time
from dataclasses import dataclass
import hashlib
import hmac
import re
from typing import Any, Dict, Optional, Set, Union

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import JWTError

# -------------------------
# HTTP Bearer
# -------------------------
_bearer = HTTPBearer(auto_error=False)

# -------------------------
# JWKS cache (per issuer)
# -------------------------
# { issuer: {"jwks": dict|None, "exp": float} }
_JWKS_CACHE: Dict[str, Dict[str, Any]] = {}
_DEFAULT_JWKS_TTL_SEC = 60 * 60  # 1h


@dataclass(frozen=True)
class Principal:
    sub: str
    permissions: Set[str]


# -------------------------
# env helpers (read at runtime)
# -------------------------
def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _truthy(v: str) -> bool:
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _unauth_detail(message: str) -> Dict[str, str]:
    return {"code": "NOT_AUTHENTICATED", "message": message}


def _auth_bypass_forbidden_detail(message: str) -> Dict[str, str]:
    return {"code": "AUTH_BYPASS_FORBIDDEN", "message": message}


def _parse_csv(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def _admin_subs() -> Set[str]:
    return set(_parse_csv(_env("ADMIN_SUBS")))


def _dev_admin_subs() -> Set[str]:
    return set(_parse_csv(_env("DEV_ADMIN_SUBS")))


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _demo_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def demo_owner_sub_from_token(token: str) -> str:
    digest = _demo_digest(token)
    return f"demo|{digest[:12]}"


def _demo_tokens_configured() -> bool:
    return bool(_env("DEMO_TOKEN_SHA256_LIST") or _env("DEMO_TOKEN_PLAINTEXT"))


def _demo_token_hashes() -> Set[str]:
    hashes: Set[str] = set()
    for part in _parse_csv(_env("DEMO_TOKEN_SHA256_LIST")):
        lower = part.lower()
        if _SHA256_RE.fullmatch(lower):
            hashes.add(lower)
    plaintext = _env("DEMO_TOKEN_PLAINTEXT")
    if plaintext:
        digest = _demo_digest(plaintext)
        hashes.add(digest)
    return hashes


def effective_auth_mode() -> str:
    return _effective_mode()


def is_admin(p: Principal) -> bool:
    mode = _effective_mode()
    if mode == "dev":
        return p.sub in _dev_admin_subs()
    return p.sub in _admin_subs()


def _is_production() -> bool:
    """
    Best-effort production detection.
    You can standardize on APP_ENV=production to make it deterministic.
    """
    for k in ("APP_ENV", "ENV", "ENVIRONMENT"):
        v = _env(k)
        if v.lower() in {"prod", "production"}:
            return True
    return False


def _auth_disabled() -> bool:
    # Hard bypass (no token required). Intended for local only.
    return _truthy(_env("AUTH_DISABLED", "0"))


def _auth_mode() -> str:
    # "auth0" (default) or "dev" or "demo" or "disabled"
    return (_env("AUTH_MODE", "auth0") or "auth0").lower()


def _effective_mode() -> str:
    """
    Priority:
      1) AUTH_DISABLED=1 -> "disabled"
      2) AUTH_MODE in {"disabled","dev","demo"} -> same
      3) otherwise       -> "auth0"
    """
    if _auth_disabled():
        return "disabled"
    m = _auth_mode()
    if m in {"disabled", "dev", "demo"}:
        return m
    return "auth0"


def _normalize_domain(domain: str) -> str:
    """
    Accept:
      - dev-xxx.us.auth0.com
      - https://dev-xxx.us.auth0.com/
    Return:
      - dev-xxx.us.auth0.com
    """
    d = domain.strip()
    if d.startswith("https://"):
        d = d[len("https://") :]
    d = d.strip().strip("/")
    return d


def _issuer() -> str:
    """
    Priority:
      1) AUTH0_ISSUER (full URL, e.g. https://tenant.us.auth0.com/)
      2) AUTH0_DOMAIN (host only, e.g. tenant.us.auth0.com)
    Return must end with "/"
    """
    iss = _env("AUTH0_ISSUER")
    if iss:
        iss = iss.strip()
        if not iss.startswith("https://"):
            iss = "https://" + _normalize_domain(iss) + "/"
        if not iss.endswith("/"):
            iss += "/"
        return iss

    domain = _normalize_domain(_env("AUTH0_DOMAIN"))
    if not domain:
        raise RuntimeError("AUTH0_ISSUER or AUTH0_DOMAIN is not set")
    return f"https://{domain}/"


def _audience() -> Union[str, list[str]]:
    """
    AUTH0_AUDIENCE can be:
      - single string
      - comma-separated list
    """
    aud_raw = _env("AUTH0_AUDIENCE")
    if not aud_raw:
        raise RuntimeError("AUTH0_AUDIENCE is not set")
    parts = _parse_csv(aud_raw)
    return parts[0] if len(parts) == 1 else parts


def _algorithms() -> list[str]:
    raw = _env("AUTH0_ALGORITHMS", "RS256")
    algs = _parse_csv(raw)
    return algs or ["RS256"]


def _jwks_ttl_sec() -> int:
    v = _env("AUTH0_JWKS_TTL_SECONDS", str(_DEFAULT_JWKS_TTL_SEC))
    try:
        n = int(v)
        return max(30, min(n, 24 * 60 * 60))  # 30s .. 24h
    except ValueError:
        return _DEFAULT_JWKS_TTL_SEC


# -------------------------
# JWKS fetch (OIDC discovery)
# -------------------------
def _openid_config_url(issuer: str) -> str:
    return issuer.rstrip("/") + "/.well-known/openid-configuration"


def _fetch_jwks(issuer: str) -> Dict[str, Any]:
    """
    OIDC discovery -> jwks_uri -> JWKS
    Avoid hardcoding "/.well-known/jwks.json".
    """
    cfg_url = _openid_config_url(issuer)
    timeout = float(_env("AUTH0_HTTP_TIMEOUT_SECONDS", "10"))

    with httpx.Client(timeout=timeout) as client:
        r = client.get(cfg_url)
        r.raise_for_status()
        cfg = r.json()

        jwks_uri = cfg.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not jwks_uri:
            raise RuntimeError("jwks_uri missing in openid-configuration")

        r = client.get(jwks_uri)
        r.raise_for_status()
        jwks = r.json()

    if not isinstance(jwks, dict) or "keys" not in jwks:
        raise RuntimeError("invalid JWKS payload")
    return jwks


def _get_jwks(issuer: str) -> Dict[str, Any]:
    now = time.time()
    ent = _JWKS_CACHE.get(issuer)
    if ent and ent.get("jwks") is not None and now < float(ent.get("exp") or 0.0):
        return ent["jwks"]

    jwks = _fetch_jwks(issuer)
    _JWKS_CACHE[issuer] = {"jwks": jwks, "exp": now + _jwks_ttl_sec()}
    return jwks


def _pick_key(jwks: Dict[str, Any], kid: str) -> Dict[str, Any]:
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k
    raise HTTPException(
        status_code=401, detail=_unauth_detail("Invalid token (kid not found)")
    )


def _extract_permissions(payload: Dict[str, Any]) -> Set[str]:
    perms = payload.get("permissions")
    if isinstance(perms, list):
        return {p for p in perms if isinstance(p, str)}

    scope = payload.get("scope")
    if isinstance(scope, str):
        return set(scope.split())

    return set()


# -------------------------
# DEV/DISABLED mode
# -------------------------
def _dev_principal(sub_override: Optional[str] = None) -> Principal:
    sub = (sub_override or _env("DEV_SUB", "dev|local")).strip()
    perms = set(_parse_csv(_env("DEV_PERMISSIONS", "read:docs,write:docs,delete:docs")))
    return Principal(sub=sub, permissions=perms)


def _maybe_guard_prod_mode() -> None:
    """
    Safety rail: prevent accidentally running with auth bypass in production.
    You can turn this off by setting AUTH_BYPASS_ALLOW_IN_PROD=1 (not recommended).
    """
    if _truthy(_env("AUTH_BYPASS_ALLOW_IN_PROD", "0")):
        return
    mode = _effective_mode()
    if _is_production() and mode in {"dev", "disabled"}:
        raise HTTPException(
            status_code=403,
            detail=_auth_bypass_forbidden_detail(
                "Auth bypass (AUTH_MODE=dev/disabled or AUTH_DISABLED=1) is not allowed in production."
            ),
        )


# -------------------------
# Decode + validate
# -------------------------
def _decode_and_validate(token: str) -> Principal:
    issuer = _issuer()
    audience = _audience()
    algorithms = _algorithms()

    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(
            status_code=401, detail=_unauth_detail("Invalid token (bad header)")
        )

    kid = header.get("kid")
    if not kid:
        raise HTTPException(
            status_code=401, detail=_unauth_detail("Invalid token (no kid)")
        )

    try:
        jwks = _get_jwks(issuer)
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"Failed to fetch JWKS (check AUTH0_ISSUER/AUTH0_DOMAIN): {e}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Failed to fetch JWKS: {e}") from e

    key = _pick_key(jwks, kid)

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=audience,
            issuer=issuer,
        )
    except JWTError:
        raise HTTPException(status_code=401, detail=_unauth_detail("Invalid token"))
    except Exception:
        raise HTTPException(status_code=401, detail=_unauth_detail("Invalid token"))

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(
            status_code=401, detail=_unauth_detail("Invalid token (no sub)")
        )

    permissions = _extract_permissions(payload)
    return Principal(sub=sub, permissions=permissions)


def get_principal(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Principal:
    _maybe_guard_prod_mode()

    def _require_bearer_token() -> str:
        if cred is None or cred.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=401, detail=_unauth_detail("Missing bearer token")
            )
        token = (cred.credentials or "").strip()
        if not token:
            raise HTTPException(
                status_code=401, detail=_unauth_detail("Missing bearer token")
            )
        return token

    mode = _effective_mode()
    if mode == "disabled":
        sub_override = request.headers.get("x-dev-sub")
        return _dev_principal(sub_override=sub_override)

    if mode == "dev":
        token = _require_bearer_token()
        if token.strip().lower() not in {"dev-token", "devtoken"}:
            raise HTTPException(
                status_code=401, detail=_unauth_detail("Invalid dev token")
            )
        sub_override = request.headers.get("x-dev-sub")
        return _dev_principal(sub_override=sub_override)

    if mode == "demo":
        token = _require_bearer_token()
        if _is_production() and not _demo_tokens_configured():
            raise HTTPException(
                status_code=401,
                detail=_unauth_detail("Demo tokens not configured"),
            )
        digest = _demo_digest(token)
        allowed_hashes = _demo_token_hashes()
        allowed = any(hmac.compare_digest(digest, h) for h in allowed_hashes)
        if not allowed:
            raise HTTPException(status_code=401, detail=_unauth_detail("Invalid token"))
        sub = demo_owner_sub_from_token(token)
        perms = {"read:docs", "write:docs", "delete:docs"}
        return Principal(sub=sub, permissions=perms)

    token = _require_bearer_token()
    if token.strip().lower() == "dev-token":
        raise HTTPException(
            status_code=401,
            detail=_unauth_detail("Dev token disabled in this environment"),
        )
    return _decode_and_validate(token)


def require_permissions(*required: str):
    required_set = set(required)

    def _dep(p: Principal = Depends(get_principal)) -> Principal:
        # If auth is disabled, always allow (local only).
        if _effective_mode() == "disabled":
            return p

        if is_admin(p):
            return p
        if not required_set.issubset(p.permissions):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return p

    return _dep


def current_user(principal: Principal = Depends(get_principal)) -> Principal:
    """
    Dependency to resolve the current authenticated principal without enforcing extra scopes.
    Use together with require_permissions(...) where scope checks are still required.
    """
    return principal
