"""run_documents created_at default now

Revision ID: c8655eb58bc8
Revises: 98b5063e46c8
Create Date: 2025-12-26

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# --- ここは生成されたものを残す ---
revision = "c8655eb58bc8"
down_revision = "98b5063e46c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 既存にNULLが混じってたら埋める（安全）
    op.execute(
        sa.text(
            """
            UPDATE run_documents
            SET created_at = now()
            WHERE created_at IS NULL;
            """
        )
    )

    # created_at のデフォルトを now() に（再現性の要）
    op.alter_column(
        "run_documents",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False,
        server_default=sa.text("now()"),
    )
    # 注：PK(run_id, document_id) が既にあるなら UNIQUE は不要。
    # もし過去に UNIQUE を作ってしまっても実害は薄いが、原則は増やさない方が良い。


def downgrade() -> None:
    # default を戻す（NULLにはしない）
    op.alter_column(
        "run_documents",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False,
        server_default=None,
    )
