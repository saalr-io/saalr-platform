# packages/core/saalr_core/backtest/repo.py
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.trading import Backtest


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_backtest(session: AsyncSession, backtest_id: UUID) -> Backtest | None:
    return (
        await session.execute(select(Backtest).where(Backtest.backtest_id == backtest_id))
    ).scalar_one_or_none()


async def create_backtest(
    session: AsyncSession,
    tenant_id: UUID,
    strategy_id: UUID,
    start: date,
    end: date,
    config_snapshot: dict,
) -> UUID:
    row = Backtest(
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        start_date=start,
        end_date=end,
        status="queued",
        config_snapshot=config_snapshot,
    )
    session.add(row)
    await session.flush()
    return row.backtest_id


async def mark_running(session: AsyncSession, backtest_id: UUID) -> None:
    bt = await get_backtest(session, backtest_id)
    if bt is None:  # row vanished (e.g. deleted) — nothing to update
        return
    bt.status = "running"
    bt.started_at = _utcnow()


async def save_result(
    session: AsyncSession,
    backtest_id: UUID,
    metrics_json: dict | None,
    status: str,
    error: str | None = None,
) -> None:
    bt = await get_backtest(session, backtest_id)
    if bt is None:  # row vanished — nothing to persist (the job gets acked/dropped)
        return
    bt.status = status
    bt.metrics_json = metrics_json
    bt.error_message = error
    bt.completed_at = _utcnow()
