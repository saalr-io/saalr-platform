from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.trading import Strategy
from saalr_core.ids import new_id


async def insert_strategy(
    session: AsyncSession, tenant_id: UUID, user_id: UUID, name: str,
    description: str | None, config_json: dict, market: str,
) -> Strategy:
    row = Strategy(
        strategy_id=new_id(), tenant_id=tenant_id, user_id=user_id, name=name,
        description=description, state="draft", config_json=config_json, market=market,
    )
    session.add(row)
    await session.flush()
    return row


async def get_strategy(session: AsyncSession, strategy_id: UUID) -> Strategy | None:
    return await session.get(Strategy, strategy_id)


async def list_strategies(
    session: AsyncSession, limit: int, cursor: tuple[datetime, UUID] | None
) -> list[Strategy]:
    stmt = select(Strategy).order_by(Strategy.created_at.desc(), Strategy.strategy_id.desc())
    if cursor is not None:
        created_at, sid = cursor
        stmt = stmt.where(
            (Strategy.created_at < created_at)
            | ((Strategy.created_at == created_at) & (Strategy.strategy_id < sid))
        )
    stmt = stmt.limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def update_strategy(session: AsyncSession, row: Strategy, **fields) -> Strategy:
    for k, v in fields.items():
        setattr(row, k, v)
    await session.flush()
    return row
