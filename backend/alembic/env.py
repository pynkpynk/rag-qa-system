# backend/alembic/env.py
from __future__ import annotations

import os
import re

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db.models import Base  # Base.metadata を使う

config = context.config
target_metadata = Base.metadata


def _resolve_port() -> str:
    """
    URL内の PORT プレースホルダを数値に解決する。
    優先順位: PGPORT -> PORT -> 5432
    """
    raw = (os.getenv("PGPORT") or os.getenv("PORT") or "5432").strip()
    # 数値以外が来たら安全側に倒す
    if not raw.isdigit():
        return "5432"
    return raw


def _substitute_port_placeholders(url: str) -> str:
    """
    よくある表記揺れの PORT プレースホルダを潰す:
    - :PORT
    - ${PORT}
    - %(PORT)s  (ini/ConfigParser由来で混ざるケース)
    """
    port = _resolve_port()

    # 文字列置換（素直に）
    url = url.replace(":PORT", f":{port}")
    url = url.replace("${PORT}", port)
    url = url.replace("%(PORT)s", port)

    # 念のため ${PORT:-5432} みたいなshell風が混ざった場合（雑に対応）
    url = re.sub(r"\$\{PORT:-\d+\}", port, url)

    return url


def _normalize_db_url(url: str) -> str:
    """
    Renderなどで出がちなURLをSQLAlchemy(psycopg3)で確実に動く形へ寄せる。
    - postgres://...        -> postgresql+psycopg://...
    - postgresql://...      -> postgresql+psycopg://...
    さらに PORT プレースホルダを数値へ解決する。
    """
    url = url.strip()
    url = _substitute_port_placeholders(url)

    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def get_url() -> str:
    url = (
        os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL") or ""
    ).strip()

    if not url:
        # alembic.ini の sqlalchemy.url を使う運用なら fallback
        url = (config.get_main_option("sqlalchemy.url") or "").strip()

    if not url:
        raise RuntimeError(
            "DATABASE_URL is required for alembic (set env DATABASE_URL)."
        )

    url = _normalize_db_url(url)

    # 最後に「まだ PORT が残ってる」みたいな事故を早期検知
    if re.search(r":PORT\b", url) or "PORT" == url.split(":")[-1].split("/")[0]:
        raise RuntimeError(f"DB URL still contains unresolved PORT placeholder: {url}")

    return url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_url()

    # engine_from_config を使うため sqlalchemy.url を注入
    configuration = config.get_section(config.config_ini_section, {})  # type: ignore[arg-type]
    configuration["sqlalchemy.url"] = url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
