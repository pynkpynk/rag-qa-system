# backend/app/db/session.py

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from pgvector.psycopg import register_vector
from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)


@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    # psycopg3 用。DB側で CREATE EXTENSION vector; が有効化されてる前提
    register_vector(dbapi_connection)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI dependency.
    `@contextmanager` は付けない（付けると _GeneratorContextManager になって 500 になります）
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
