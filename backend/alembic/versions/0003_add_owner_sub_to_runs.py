from alembic import op

revision = "0003_add_owner_sub_to_runs"
down_revision = "0002_add_owner_sub_to_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE runs
        ADD COLUMN IF NOT EXISTS owner_sub VARCHAR(128)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_runs_owner_sub
        ON runs(owner_sub)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_runs_owner_sub", table_name="runs")
    op.drop_column("runs", "owner_sub")
