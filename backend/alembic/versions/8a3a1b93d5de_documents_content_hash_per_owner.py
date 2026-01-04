"""documents content hash unique per owner

Revision ID: 8a3a1b93d5de
Revises: f621b25f81b9
Create Date: 2026-01-10 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a3a1b93d5de"
down_revision: str | None = '7c0441ed0c4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documents_content_hash")
    op.create_index(
        "ux_documents_owner_sub_content_hash",
        "documents",
        ["owner_sub", "content_hash"],
        unique=True,
    )
    op.create_index(
        "ux_documents_content_hash_legacy",
        "documents",
        ["content_hash"],
        unique=True,
        postgresql_where=sa.text("owner_sub IS NULL"),
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_documents_content_hash_legacy")
    op.execute("DROP INDEX IF EXISTS ux_documents_owner_sub_content_hash")
    op.create_index(
        "ix_documents_content_hash",
        "documents",
        ["content_hash"],
        unique=True,
    )
