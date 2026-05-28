import os

import pytest_asyncio
from sqlalchemy import text

from saalr_core.db.session import create_engine

EXPECTED_TABLES = {
    "tenants", "users", "memberships", "api_keys",
    "subscriptions", "billing_events",
    "strategies", "backtests", "model_validation_runs",
    "broker_accounts", "orders", "executions", "positions",
    "audit_log", "bars", "options_chain_snapshots", "config_kv",
}


@pytest_asyncio.fixture
async def admin_conn():
    engine = create_engine(os.environ["ADMIN_DATABASE_URL"])
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


async def test_all_tables_exist(admin_conn):
    rows = await admin_conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    present = {r[0] for r in rows}
    assert EXPECTED_TABLES <= present


async def test_hypertables_exist(admin_conn):
    rows = await admin_conn.execute(
        text("SELECT hypertable_name FROM timescaledb_information.hypertables")
    )
    hypertables = {r[0] for r in rows}
    assert {"bars", "options_chain_snapshots"} <= hypertables