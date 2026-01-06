"""ensure pg_trgm extension exists

Revision ID: a9e7c1f3bb5c
Revises: 8a3a1b93d5de
Create Date: 2026-02-06 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9e7c1f3bb5c"
down_revision: Union[str, Sequence[str], None] = "8a3a1b93d5de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS pg_trgm;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'insufficient privilege to create pg_trgm extension';
            WHEN undefined_file THEN
                RAISE NOTICE 'pg_trgm extension is not available on this server';
        END;
        $$;
        """.strip()
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            DROP EXTENSION IF EXISTS pg_trgm;
        EXCEPTION
            WHEN insufficient_privilege THEN
                RAISE NOTICE 'insufficient privilege to drop pg_trgm extension';
        END;
        $$;
        """.strip()
    )
