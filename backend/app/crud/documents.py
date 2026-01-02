# app/crud/documents.py
from __future__ import annotations

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.db.models import Document


def list_docs(db: Session, owner_sub: str) -> list[Document]:
    return list(
        db.execute(select(Document).where(Document.owner_sub == owner_sub)).scalars()
    )


def get_doc(db: Session, doc_id: int, owner_sub: str) -> Document | None:
    return db.execute(
        select(Document).where(Document.id == doc_id, Document.owner_sub == owner_sub)
    ).scalar_one_or_none()


def delete_doc(db: Session, doc_id: int, owner_sub: str) -> bool:
    r = db.execute(
        delete(Document).where(Document.id == doc_id, Document.owner_sub == owner_sub)
    )
    return (r.rowcount or 0) > 0
