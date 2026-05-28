import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from saalr_core.db.base import Base
import saalr_core.db.models  # noqa: F401  (registers models on Base.metadata)

config = context.config

# Alembic runs synchronously; coerce an async URL to the sync psycopg2 driver
# (asyncpg cannot execute the multi-statement DDL blocks in the baseline migration).
raw_url = os.environ.get(
    "ADMIN_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/saalr",
)
config.set_main_option("sqlalchemy.url", raw_url.replace("+asyncpg", "+psycopg2"))

target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
