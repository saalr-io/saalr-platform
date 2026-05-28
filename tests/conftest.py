import os
import subprocess

import pytest
import pytest_asyncio
from sqlalchemy import text

from saalr_core.db.session import create_engine, create_sessionmaker

ADMIN_URL = os.environ.setdefault(
    "ADMIN_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/saalr"
)
APP_URL = os.environ.setdefault(
    "APP_DATABASE_URL", "postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr"
)

TENANT_TABLES = [
    "executions", "orders", "positions", "broker_accounts", "backtests",
    "strategies", "billing_events", "subscriptions", "api_keys",
    "memberships", "audit_log", "tenants",
]


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    """Apply all migrations once before the suite (idempotent)."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env={**os.environ},
    )


@pytest_asyncio.fixture
async def admin_engine():
    engine = create_engine(ADMIN_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def app_sessionmaker():
    engine = create_engine(APP_URL)
    yield create_sessionmaker(engine)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _truncate(admin_engine):
    """Clean tenant tables before each test (admin connection bypasses RLS via TRUNCATE)."""
    async with admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE " + ", ".join(TENANT_TABLES) + " CASCADE"))
        await conn.execute(text("TRUNCATE users CASCADE"))
    yield