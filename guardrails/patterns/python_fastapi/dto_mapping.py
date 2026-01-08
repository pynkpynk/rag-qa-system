from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# Example Pydantic DTOs (Pydantic v2 style)

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    owner_sub: str
    created_at: datetime


def to_document_out(orm_doc: Any) -> DocumentOut:
    """
    Centralized DTO conversion.
    If ORM shape changes, fix it here, not across endpoints.
    """
    return DocumentOut.model_validate(orm_doc, from_attributes=True)
