# backend/app/db/session.py

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from pgvector.psycopg import register_vector
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _normalize_database_url(url: str) -> str:
    """
    SQLAlchemy's default driver for 'postgresql://' is psycopg2.
    This project uses psycopg3 + pgvector.psycopg, so we normalize to:
      postgresql+psycopg://...

    Also handles Render-style 'postgres://'.
    """
    u = (url or "").strip()
    if not u:
        return u

    # Render sometimes uses postgres://
    if u.startswith("postgres://"):
        return "postgresql+psycopg://" + u[len("postgres://") :]

    # Plain postgresql:// -> force psycopg3
    if u.startswith("postgresql://") and not u.startswith("postgresql+"):
        return "postgresql+psycopg://" + u[len("postgresql://") :]

    # If someone set psycopg2 explicitly, prefer psycopg3 for this repo
    if u.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + u[len("postgresql+psycopg2://") :]

    return u


DATABASE_URL = _normalize_database_url(settings.database_url)

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db() -> Generator:
    db = SessionLocal()
    try:
        # Register pgvector type support (psycopg3 connection)
        conn = db.connection().connection
        register_vector(conn)
        yield db
    finally:
        db.close()
