from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol, TypeVar

# This pattern is sync SQLAlchemy-style.
# If you use AsyncSession, mirror the same semantics with async context manager.

TSession = TypeVar("TSession")


class SessionProtocol(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


SessionFactory = Callable[[], TSession]


@dataclass
class UnitOfWork:
    """
    Unit of Work pattern:
    - Owns session lifecycle
    - Commits on success
    - Rolls back on error
    """
    session_factory: SessionFactory[TSession]
    session: Optional[TSession] = None

    def __enter__(self) -> "UnitOfWork":
        self.session = self.session_factory()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.session is not None
        try:
            if exc is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
            self.session = None


def get_uow(session_factory: SessionFactory[TSession]) -> UnitOfWork:
    """
    Wrap your real SQLAlchemy sessionmaker here.
    Example:
      SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
      uow = Depends(lambda: get_uow(SessionLocal))
    """
    return UnitOfWork(session_factory=session_factory)
