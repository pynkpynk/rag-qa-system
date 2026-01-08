from __future__ import annotations

from fastapi import APIRouter, Depends

from .authn_authz import CurrentUser, deny_as_not_found, require_scope
from .errors import http_error
from .dto_mapping import DocumentOut, to_document_out

router = APIRouter(tags=["documents"])


# Pseudo repository (replace with your real repo)
def _get_document_by_id(db: object, doc_id: str):
    if doc_id == "missing":
        return None
    return type(
        "Doc",
        (),
        {"id": doc_id, "title": "Example", "owner_sub": "demo-user", "created_at": __import__("datetime").datetime.utcnow()},
    )()


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(
    doc_id: str,
    user: CurrentUser = Depends(require_scope("documents:read")),
) -> DocumentOut:
    db = object()  # replace with DI session/uow
    doc = _get_document_by_id(db, doc_id)

    # 404 for not found
    if doc is None:
        raise deny_as_not_found()

    # Hide existence when not owner (404 for both not found / not allowed)
    if doc.owner_sub != user.sub:
        raise deny_as_not_found()

    return to_document_out(doc)


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    user: CurrentUser = Depends(require_scope("documents:write")),
) -> dict:
    db = object()  # replace with DI session/uow
    doc = _get_document_by_id(db, doc_id)
    if doc is None or doc.owner_sub != user.sub:
        raise deny_as_not_found()

    # delete operation here...
    return {"status": "deleted"}
