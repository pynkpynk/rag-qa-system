from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException


@dataclass(frozen=True)
class ApiErrorDetail:
    code: str
    message: str
    hint: Optional[str] = None
    extra: Optional[dict[str, Any]] = None


def http_error(
    *,
    status_code: int,
    code: str,
    message: str,
    hint: str | None = None,
    extra: dict[str, Any] | None = None,
) -> HTTPException:
    """
    Standardized HTTP error payload.
    Keep it stable and versionable for clients.
    """
    detail = {
        "error": {
            "code": code,
            "message": message,
            "hint": hint,
            "extra": extra,
        }
    }
    return HTTPException(status_code=status_code, detail=detail)
