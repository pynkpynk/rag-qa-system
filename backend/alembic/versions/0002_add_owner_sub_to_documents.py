"""add owner_sub to documents

Revision ID: 0002_add_owner_sub_to_documents
Revises: 0001_baseline
Create Date: 2025-12-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0002_add_owner_sub_to_documents"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("owner_sub", sa.String(length=128), nullable=True))
    op.create_index("ix_documents_owner_sub", "documents", ["owner_sub"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_owner_sub", table_name="documents")
    op.drop_column("documents", "owner_sub")
