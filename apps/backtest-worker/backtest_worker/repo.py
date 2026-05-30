from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.trading import Backtest, Strategy


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_strategy(session: AsyncSession, strategy_id: UUID) -> Strategy | None:
    return (
        await session.execute(select(Strategy).where(Strategy.strategy_id == strategy_id))
    ).scalar_one_or_none()


async def get_backtest(session: AsyncSession, backtest_id: UUID) -> Backtest | None:
    return (
        await session.execute(select(Backtest).where(Backtest.backtest_id == backtest_id))
    ).scalar_one_or_none()


async def load_underlying_closes(
    session: AsyncSession, symbol: str, market: str, start: date, end: date, lookback: int
) -> dict[date, float]:
    """Daily closes in [start - warmup, end]. Warmup pads back enough calendar days to
    fill the realized-vol lookback window. `bars` is non-RLS (shared market data)."""
    pad_start = start - timedelta(days=int(lookback * 1.6) + 7)
    rows = (
        await session.execute(
            text(
                """
                SELECT ts, close FROM bars
                WHERE symbol = :sym AND market = :mkt AND interval = '1d'
                  AND ts::date >= :s AND ts::date <= :e
                ORDER BY ts
                """
            ),
            {"sym": symbol, "mkt": market, "s": pad_start, "e": end},
        )
    ).all()
    return {r.ts.date(): float(r.close) for r in rows}


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
    bt.status = status
    bt.metrics_json = metrics_json
    bt.error_message = error
    bt.completed_at = _utcnow()
