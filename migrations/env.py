# migrations/env.py
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from server_v2.db import database_url
from server_v2.identity_models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Our app's URL wins over the static alembic.ini value (so SQLite/Postgres follow env).
config.set_main_option("sqlalchemy.url", config.get_main_option("sqlalchemy.url") or database_url())

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
