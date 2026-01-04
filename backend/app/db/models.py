import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, Table, Text
from sqlalchemy.orm import relationship

from app.db.base import Base

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
    Column(
        "run_id", String, ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "document_id",
        String,
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True), default=utcnow, nullable=False),
)


# =========================
# Models
# =========================


class Run(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True, default=gen_uuid)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    # ✅ NEW: runs の所有者（Auth0 sub）
    owner_sub = Column(String, index=True, nullable=True)

    config = Column(JSON, nullable=False)

    status = Column(String, default="created", nullable=False)
    error = Column(String, nullable=True)

    t0 = Column(DateTime(timezone=True), nullable=True)
    t1 = Column(DateTime(timezone=True), nullable=True)
    t2 = Column(DateTime(timezone=True), nullable=True)
    t3 = Column(DateTime(timezone=True), nullable=True)

    documents = relationship(
        "Document",
        secondary=run_documents,
        back_populates="runs",
        lazy="selectin",
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index(
            "ux_documents_owner_sub_content_hash",
            "owner_sub",
            "content_hash",
            unique=True,
        ),
    )

    id = Column(String, primary_key=True, default=gen_uuid)
    filename = Column(String, nullable=False)

    status = Column(String, default="uploaded", nullable=False)
    error = Column(String, nullable=True)

    content_hash = Column(String(64), nullable=True, index=True)

    owner_sub = Column(String, index=True, nullable=True)

    # ✅ NEW: S3 object key を入れる（例: "uploads/<doc_id>/<hash>_file.pdf"）
    storage_key = Column(Text, nullable=True)

    # 既存互換：ローカルパス等（必要なら残す）
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
