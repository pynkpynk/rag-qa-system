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
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
