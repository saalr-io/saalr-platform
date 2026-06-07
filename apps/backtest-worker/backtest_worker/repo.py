# apps/backtest-worker/backtest_worker/repo.py
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.backtest.repo import (  # noqa: F401 - re-exported for the worker's service/CLI
    create_backtest,
    get_backtest,
    mark_running,
    save_result,
)
from saalr_core.db.models.trading import Strategy


async def get_strategy(session: AsyncSession, strategy_id: UUID) -> Strategy | None:
    return (
        await session.execute(select(Strategy).where(Strategy.strategy_id == strategy_id))
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
