"""documents content_hash unique per owner

Revision ID: 8a3a1b93d5de
Revises: 7c0441ed0c4b
Create Date: 2026-01-xx
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a3a1b93d5de"
down_revision: Union[str, Sequence[str], None] = "7c0441ed0c4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) drop old global unique (may exist as index name used previously)
    op.execute("DROP INDEX IF EXISTS ix_documents_content_hash")

    # 2) helpful non-unique index (safe if already exists)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_documents_owner_sub ON documents (owner_sub)"
    )

    # 3) per-owner dedupe: unique per (owner_sub, content_hash)
    #    (for non-NULL owners; legacy NULL owners handled separately)
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_owner_sub_content_hash
        ON documents (owner_sub, content_hash)
        WHERE owner_sub IS NOT NULL
        """.strip()
    )

    # 4) legacy rows (owner_sub IS NULL): keep global unique on content_hash for legacy only
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_content_hash_legacy
        ON documents (content_hash)
        WHERE owner_sub IS NULL
        """.strip()
    )


def downgrade() -> None:
    # reverse: drop new indexes (safe if missing)
    op.execute("DROP INDEX IF EXISTS ux_documents_content_hash_legacy")
    op.execute("DROP INDEX IF EXISTS ux_documents_owner_sub_content_hash")

    # keep ix_documents_owner_sub if you prefer; but drop for a clean downgrade
    op.execute("DROP INDEX IF EXISTS ix_documents_owner_sub")

    # restore old global unique
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_documents_content_hash ON documents (content_hash)"
    )
