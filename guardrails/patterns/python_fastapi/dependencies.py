from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

from fastapi import Depends

# NOTE: Replace with your real session/user types.
# This file exists to centralize DI and avoid ad-hoc globals.


@dataclass(frozen=True)
class CurrentUser:
    sub: str
    email: Optional[str] = None


def get_db() -> Iterator[object]:
    """
    Yield a DB session/connection.
    Replace `object` with your real session type.
    """
    db = object()
    try:
        yield db
    finally:
        # close db session here
        pass


def get_current_user() -> CurrentUser:
    """
    Replace with real auth verification (JWT, session, etc.)
    Keep auth centralized.
    """
    return CurrentUser(sub="demo-user")


def require_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user
