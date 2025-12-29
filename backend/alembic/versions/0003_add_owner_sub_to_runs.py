from alembic import op
import sqlalchemy as sa

revision = "0003_add_owner_sub_to_runs"
down_revision = "0002_add_owner_sub_to_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("owner_sub", sa.String(length=128), nullable=True))
    op.create_index("ix_runs_owner_sub", "runs", ["owner_sub"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_runs_owner_sub", table_name="runs")
    op.drop_column("runs", "owner_sub")
