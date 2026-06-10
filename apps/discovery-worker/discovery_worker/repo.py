# apps/discovery-worker/discovery_worker/repo.py
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.discovery.repo import (  # noqa: F401 - re-exported for the worker's service/CLI
    create_discovery,
    get_discovery,
    mark_running,
    save_result,
)


async def load_recent_closes(
    session: AsyncSession, underlying: str, market: str, as_of: date, lookback_days: int = 400,
) -> list[float]:
    """Daily closes ending at as_of for regime detection (needs >= 60). `bars` is
    non-RLS shared market data, keyed by symbol/market/interval (no instruments join)."""
    start = as_of - timedelta(days=lookback_days)
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
            {"sym": underlying.upper(), "mkt": market, "s": start, "e": as_of},
        )
    ).all()
    return [float(r.close) for r in rows]
