"""allow null chunk embeddings

Revision ID: 7c0441ed0c4b
Revises: 4a9d185719de
Create Date: 2025-01-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "7c0441ed0c4b"
down_revision: str | None = '6b5eab88853a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=Vector(EMBEDDING_DIM),
        nullable=True,
    )
    # NOTE: skipped ivfflat index creation (Render maintenance_work_mem too small)
def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_l2")
    op.alter_column(
        "chunks",
        "embedding",
        existing_type=Vector(EMBEDDING_DIM),
        nullable=False,
    )
