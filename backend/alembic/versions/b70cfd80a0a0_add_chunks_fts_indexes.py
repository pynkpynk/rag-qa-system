"""add chunks fts column and indexes

Revision ID: b70cfd80a0a0
Revises: a9e7c1f3bb5c
Create Date: 2026-02-10 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b70cfd80a0a0"
down_revision: Union[str, Sequence[str], None] = "a9e7c1f3bb5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                CREATE EXTENSION IF NOT EXISTS pg_trgm;
            EXCEPTION
                WHEN insufficient_privilege THEN
                    RAISE NOTICE 'insufficient privilege to create pg_trgm';
                WHEN undefined_file THEN
                    RAISE NOTICE 'pg_trgm extension is not available on this server';
            END;
            $$;
            """
        )
    )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'chunks'
                      AND column_name = 'fts'
                ) THEN
                    ALTER TABLE chunks
                    ADD COLUMN fts tsvector
                    GENERATED ALWAYS AS (
                        to_tsvector('simple', coalesce("text", ''))
                    ) STORED;
                END IF;
            END;
            $$;
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_fts_gin
            ON chunks
            USING GIN (fts);
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_text_trgm
            ON chunks
            USING GIN ("text" gin_trgm_ops);
            """
        )
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS idx_chunks_text_trgm;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS idx_chunks_fts_gin;
            """
        )
    )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'chunks'
                      AND column_name = 'fts'
                ) THEN
                    ALTER TABLE chunks
                    DROP COLUMN fts;
                END IF;
            END;
            $$;
            """
        )
    )
