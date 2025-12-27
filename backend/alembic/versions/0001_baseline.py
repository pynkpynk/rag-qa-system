"""baseline

Revision ID: 0001_baseline
Revises: 
Create Date: 2025-12-24

このリビジョンは「いまDBに存在しているスキーマ」を baseline として扱うための空マイグレーション。
"""

from __future__ import annotations

from alembic import op  # noqa: F401


# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 既存DBを baseline として扱うだけなので何もしない
    pass


def downgrade() -> None:
    # baseline の取り消しも基本やらない（何もしない）
    pass
