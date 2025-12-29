from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "xxxxxxxx_add_chunks_fts"  # ←自動生成のIDに合わせてOK
down_revision = None  # ←自動生成に合わせてOK
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) tsvector generated column
    op.execute(
        """
        ALTER TABLE chunks
        ADD COLUMN IF NOT EXISTS fts tsvector
        GENERATED ALWAYS AS (
          to_tsvector('simple', coalesce(text, ''))
        ) STORED
        """
    )

    # 2) GIN index for FTS
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_fts_gin
        ON chunks
        USING GIN (fts)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_fts_gin")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS fts")
