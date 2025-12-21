# backend/app/db/session.py
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# pgvector (psycopg3)
from pgvector.psycopg import register_vector

DATABASE_URL = settings.database_url

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

@event.listens_for(engine, "connect")
def _register_vector(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    # psycopg3 用
    register_vector(dbapi_connection)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
