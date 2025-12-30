"""baseline

Revision ID: 0001_baseline
Revises:
Create Date: 2025-12-24

このリビジョンは「いまDBに存在しているスキーマ」を baseline として扱うための空マイグレーション。
"""

from __future__ import annotations

import importlib
import pkgutil

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
import app.db.models as models_pkg  # noqa: F401


# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


REQUIRED_TABLES = {"documents", "runs", "chunks", "run_documents"}
DEFAULT_SCHEMA = "public"


def _import_all_model_modules() -> None:
    """Ensure every ORM module is imported so Base.metadata is populated."""
    if hasattr(models_pkg, "__path__"):
        prefix = models_pkg.__name__ + "."
        for _, name, _ in pkgutil.walk_packages(models_pkg.__path__, prefix):
            importlib.import_module(name)


def upgrade() -> None:
    """Bootstrap brand-new databases so future ALTER migrations succeed."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names(schema=DEFAULT_SCHEMA))

    if REQUIRED_TABLES.issubset(existing_tables):
        # Fully initialized; nothing to do.
        return

    if existing_tables.intersection(REQUIRED_TABLES):
        # Partial state detected; defer to later migrations to reconcile.
        return

    # At this point none of the required tables exist: bootstrap everything.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _import_all_model_modules()
    Base.metadata.create_all(bind=bind)

    inspector = sa.inspect(bind)
    tables_after = set(inspector.get_table_names(schema=DEFAULT_SCHEMA))
    if not REQUIRED_TABLES.issubset(tables_after):
        raise RuntimeError(
            "Bootstrap failed to create required tables",
            {
                "required": sorted(REQUIRED_TABLES),
                "existing_tables": sorted(tables_after),
                "metadata_tables": sorted(Base.metadata.tables.keys()),
            },
        )


def downgrade() -> None:
    # baseline の取り消しも基本やらない（何もしない）
    pass
