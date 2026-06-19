from alembic import context
from sqlalchemy import create_engine, pool

from saalr_core.config import get_settings
from saalr_core.db.base import Base
import saalr_core.db.models  # noqa: F401  (registers models on Base.metadata)

config = context.config
target_metadata = Base.metadata


def _admin_url() -> str:
    # admin_database_url is composed from the container DB_* vars (or ADMIN_DATABASE_URL)
    # by Settings, with the password URL-encoded. Alembic runs synchronously, so coerce
    # an async URL to the sync psycopg2 driver (asyncpg can't run the multi-statement DDL
    # blocks in the baseline). The URL is handed straight to the engine — NOT via the ini /
    # configparser, which would treat %-escapes in the encoded password as interpolation.
    return get_settings().admin_database_url.replace("+asyncpg", "+psycopg2")


def run_migrations_online() -> None:
    connectable = create_engine(_admin_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
