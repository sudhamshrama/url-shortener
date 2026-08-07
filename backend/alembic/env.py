"""Alembic environment.

Reads the database URL from the application settings rather than alembic.ini so
there is exactly one source of truth for the connection string, and so no
credential is ever committed.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Imported for the side effect of registering the model on Base.metadata.
# Without this, autogenerate produces an empty migration and helpfully offers
# to drop your entire schema.
from app import models  # noqa: F401
from app.config import get_settings
from app.database import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it.

    Useful when a DBA wants to review the statements before they run against
    production — which is a normal requirement in regulated environments.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Catches column type drift that Alembic would otherwise ignore.
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
