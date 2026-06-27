# migrations/env.py
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from server_v2.db import database_url, ensure_sqlite_parent
from server_v2.identity_models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the DB URL: an explicit alembic.ini value (or one a caller set) wins; otherwise fall
# back to the app's env-derived database_url(). alembic.ini ships empty, so deploys use database_url().
config.set_main_option("sqlalchemy.url", config.get_main_option("sqlalchemy.url") or database_url())
ensure_sqlite_parent(config.get_main_option("sqlalchemy.url"))  # create data/ before sqlite opens

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite-safe ALTERs for future migrations
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
