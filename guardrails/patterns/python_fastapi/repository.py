from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Repository should be the only place that "knows" persistence details.


@dataclass(frozen=True)
class Document:
    id: str
    title: str


def get_document_by_id(*, db: object, doc_id: str) -> Optional[Document]:
    # Replace with real query logic.
    # Keep DB details here, not in services/routers.
    if doc_id == "missing":
        return None
    return Document(id=doc_id, title="Example")
