from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Set

from fastapi import Depends, Header

from .errors import http_error


# ---- Domain model for auth context ----

@dataclass(frozen=True)
class CurrentUser:
    sub: str
    scopes: Set[str]
    email: Optional[str] = None


# ---- AuthN: build CurrentUser from credential (e.g. JWT) ----

def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """
    AuthN entrypoint.
    Replace token parsing / JWT verification with your real implementation.
    Keep this logic centralized and re-used across endpoints.
    """
    if not authorization:
        raise http_error(
            status_code=401,
            code="auth.missing",
            message="Authentication required.",
            hint="Provide Authorization header.",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise http_error(
            status_code=401,
            code="auth.invalid",
            message="Invalid authorization header.",
            hint='Use "Authorization: Bearer <token>".',
        )

    # TODO: Replace with a real verify_jwt(token) implementation.
    # This is intentionally minimal: keep the pattern stable.
    claims = _mock_verify_jwt(token)

    return CurrentUser(
        sub=str(claims["sub"]),
        email=claims.get("email"),
        scopes=set(claims.get("scopes", [])),
    )


def _mock_verify_jwt(token: str) -> dict:
    # Demo only. Replace with real verification.
    if token == "bad":
        raise http_error(status_code=401, code="auth.bad_token", message="Invalid token.")
    return {"sub": "demo-user", "email": "demo@example.com", "scopes": ["documents:read", "documents:write"]}


# ---- AuthZ: scope-based guard ----

def require_scope(*required: str):
    """
    Usage:
      user = Depends(require_scope("documents:read"))
    """
    required_set = set(required)

    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not required_set.issubset(user.scopes):
            raise http_error(
                status_code=403,
                code="auth.forbidden",
                message="You do not have permission to perform this action.",
                hint=f"Required scopes: {sorted(required_set)}",
                extra={"missing_scopes": sorted(required_set - user.scopes)},
            )
        return user

    return _dep


# ---- Resource authorization: 403 vs 404 design ----

def deny_as_not_found() -> Exception:
    """
    Use 404 to hide existence when the user should not learn
    whether the resource exists.
    """
    return http_error(status_code=404, code="resource.not_found", message="Resource not found.")


def deny_as_forbidden() -> Exception:
    """
    Use 403 when existence may be revealed but action is forbidden.
    """
    return http_error(status_code=403, code="resource.forbidden", message="Forbidden.")
