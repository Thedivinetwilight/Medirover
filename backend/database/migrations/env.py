"""Alembic environment.

The database URL is taken from the MEDIROVER_DB_URL environment variable,
or from a programmatically set `sqlalchemy.url` (alembic.ini stores no URL).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _apply_url() -> None:
    url = os.environ.get("MEDIROVER_DB_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "MEDIROVER_DB_URL is not set. Run alembic with the environment's "
            "database URL, e.g. `make migrate` or "
            "`MEDIROVER_DB_URL=sqlite:///... alembic upgrade head`."
        )
    config.set_main_option("sqlalchemy.url", url)


def run_migrations_offline() -> None:
    _apply_url()
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    _apply_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
