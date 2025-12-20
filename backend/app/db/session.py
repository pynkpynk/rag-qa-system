from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


# ---- Engine ----
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)


# ---- Session factory ----
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---- pgvector registration (psycopg2 or psycopg3) ----
def _try_register_vector(dbapi_connection) -> None:
    """
    Register pgvector adapter for whichever postgres driver is installed.
    - psycopg2: pgvector.psycopg2.register_vector
    - psycopg (v3): pgvector.psycopg.register_vector
    """
    try:
        from pgvector.psycopg2 import register_vector  # type: ignore

        register_vector(dbapi_connection)
        return
    except Exception:
        pass

    try:
        from pgvector.psycopg import register_vector  # type: ignore

        register_vector(dbapi_connection)
        return
    except Exception:
        # If registration fails, vector columns may still work via SQLAlchemy types,
        # but similarity ops could fail. We keep app boot resilient.
        return


@event.listens_for(engine, "connect")
def _on_connect(dbapi_connection, _connection_record) -> None:
    _try_register_vector(dbapi_connection)


# ---- FastAPI dependency (IMPORTANT: no @contextmanager) ----
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Safe rollback if an exception bubbles up during a request
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        db.close()
