import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# =========================
# Helpers / Constants
# =========================

def gen_uuid() -> str:
    """Primary key generator (UUID as string)."""
    return str(uuid.uuid4())

def utcnow() -> datetime:
    # timezone-aware UTC
    return datetime.now(timezone.utc)

EMBEDDING_DIM = 1536  # text-embedding-3-small 想定


# =========================
# Association Table
# Run <-> Document (Many-to-Many)
# =========================

run_documents = Table(
    "run_documents",
    Base.metadata,
    Column("run_id", String, ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True),
    Column("document_id", String, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), default=utcnow, nullable=False),
)


# =========================
# Models
# =========================

class Run(Base):
    """
    Experiment / evaluation run entity.
    A Run can be associated with multiple documents (document set for that run).
    """
    __tablename__ = "runs"

    id = Column(String, primary_key=True, default=gen_uuid)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Example config:
    # {"model":"gpt-5-mini","chunk":{"size":800,"overlap":120},"retriever":{"k":8}}
    # Optionally: {"gen": {"max_tokens": 600, ...}}
    config = Column(JSON, nullable=False)

    status = Column(String, default="created", nullable=False)
    error = Column(String, nullable=True)

    # Optional timing markers (latest /chat/ask instrumentation)
    t0 = Column(DateTime(timezone=True), nullable=True)  # request received
    t1 = Column(DateTime(timezone=True), nullable=True)  # LLM started
    t2 = Column(DateTime(timezone=True), nullable=True)  # LLM finished
    t3 = Column(DateTime(timezone=True), nullable=True)  # response returned

    documents = relationship(
        "Document",
        secondary=run_documents,
        back_populates="runs",
        lazy="selectin",
    )


class Document(Base):
    """
    Uploaded document entity.
    A Document can be linked to many runs.
    """
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_uuid)
    filename = Column(String, nullable=False)

    status = Column(String, default="uploaded", nullable=False)
    error = Column(String, nullable=True)

    # SHA256 hex digest (64 chars).
    content_hash = Column(String(64), unique=True, index=True, nullable=True)

    # e.g. {"path": "/abs/path/to/file.pdf"}
    meta = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    chunks = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    runs = relationship(
        "Run",
        secondary=run_documents,
        back_populates="documents",
        lazy="selectin",
    )


class Chunk(Base):
    """
    Chunk entity extracted from a document.
    """
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, default=gen_uuid)

    document_id = Column(
        String,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    page = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)

    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    document = relationship("Document", back_populates="chunks")
