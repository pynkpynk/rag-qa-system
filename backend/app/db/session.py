from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from pgvector.psycopg import register_vector
from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    register_vector(dbapi_connection)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
