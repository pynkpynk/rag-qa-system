"""merge multiple heads

Revision ID: 98b5063e46c8
Revises: 0003_add_owner_sub_to_runs, xxxxxxxx_add_chunks_fts
Create Date: 2025-12-26 10:17:10.138918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98b5063e46c8'
down_revision: Union[str, Sequence[str], None] = ('0003_add_owner_sub_to_runs', 'xxxxxxxx_add_chunks_fts')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
