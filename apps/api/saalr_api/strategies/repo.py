from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.trading import Strategy
from saalr_core.db.models.audit import AuditLog
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


async def first_paper_order_at(session: AsyncSession, strategy_id: UUID):
    """Timestamp of the strategy's earliest paper order (RLS-scoped), or None."""
    row = (await session.execute(text(
        "SELECT MIN(o.created_at) AS first FROM orders o "
        "JOIN broker_accounts b ON b.broker_account_id = o.broker_account_id "
        "WHERE o.strategy_id = :sid AND b.broker = 'paper'"),
        {"sid": str(strategy_id)})).first()
    first = row.first if row else None
    # MIN() over a raw text() aggregate can lose the TIMESTAMPTZ type metadata and come back naive;
    # coerce to aware UTC so the timezone-aware promotion gate never trips on driver quirks.
    if first is not None and first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    return first


async def record_promotion(session: AsyncSession, row: Strategy, now: datetime) -> Strategy:
    row.state = "live"
    row.promoted_to_live_at = now
    await session.flush()
    return row


async def write_strategy_audit(session: AsyncSession, *, tenant_id, user_id, strategy_id,
                               action, before, after, request_id) -> None:
    session.add(AuditLog(
        audit_id=new_id(), tenant_id=tenant_id, user_id=user_id, action=action,
        target_type="strategy", target_id=strategy_id, before_state=before, after_state=after,
        request_id=request_id,
    ))
    await session.flush()
