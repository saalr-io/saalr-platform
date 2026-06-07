import os

import pytest_asyncio
from sqlalchemy import text

from saalr_core.db.base import Base
import saalr_core.db.models  # noqa: F401
from saalr_core.db.session import create_engine


@pytest_asyncio.fixture
async def admin_conn():
    engine = create_engine(os.environ["ADMIN_DATABASE_URL"])
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


async def test_db_tables_match_models(admin_conn):
    rows = await admin_conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    db_tables = {r[0] for r in rows}
    model_tables = set(Base.metadata.tables.keys())
    # Every model table must exist in the DB (DB may also hold timescale internals).
    assert model_tables <= db_tables


async def test_all_model_columns_match_db(admin_conn):
    for table in Base.metadata.tables.keys():
        rows = await admin_conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t"
            ),
            {"t": table},
        )
        db_cols = {r[0] for r in rows}
        model_cols = set(Base.metadata.tables[table].columns.keys())
        assert model_cols == db_cols, f"{table}: {model_cols ^ db_cols}"