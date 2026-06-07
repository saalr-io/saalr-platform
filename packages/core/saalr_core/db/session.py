from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def tenant_session(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: UUID | str
) -> AsyncIterator[AsyncSession]:
    """Open a transaction with app.current_tenant set for RLS, then yield the session.

    The GUC is set transaction-local (set_config third arg = true), so it is cleared
    automatically at COMMIT/ROLLBACK and can never leak to the next user of a pooled
    connection. All work must therefore happen inside this single transaction; do not
    open a nested session.begin() on the yielded session.
    """
    async with sessionmaker() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            yield session