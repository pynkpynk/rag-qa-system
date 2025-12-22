"""add storage_key to documents

Revision ID: 4a9d185719de
Revises: 99eabb931944
Create Date: 2025-12-21 17:51:21.377976

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "4a9d185719de"
down_revision: Union[str, Sequence[str], None] = "99eabb931944"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("documents", sa.Column("storage_key", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("documents", "storage_key")
