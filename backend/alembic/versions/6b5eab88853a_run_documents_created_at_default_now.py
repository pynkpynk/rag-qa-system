"""run_documents created_at default now

Revision ID: 6b5eab88853a
Revises: c8655eb58bc8
Create Date: 2025-12-26 21:04:29.453107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b5eab88853a'
down_revision: Union[str, Sequence[str], None] = 'c8655eb58bc8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ensure run_documents.created_at defaults to now() in an idempotent way."""
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'run_documents'
                      AND column_name = 'created_at'
                ) THEN
                    UPDATE run_documents
                    SET created_at = now()
                    WHERE created_at IS NULL;

                    ALTER TABLE run_documents
                    ALTER COLUMN created_at SET DEFAULT now();
                END IF;
            END;
            $$;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'run_documents'
                      AND column_name = 'created_at'
                ) THEN
                    ALTER TABLE run_documents
                    ALTER COLUMN created_at DROP DEFAULT;
                END IF;
            END;
            $$;
            """
        )
    )
