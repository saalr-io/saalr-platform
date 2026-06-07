from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .aggregates import BarRow

_UPSERT_BARS = text(
    """
    INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
    VALUES (:ts, :symbol, :market, :interval, :open, :high, :low, :close, :volume)
    ON CONFLICT (symbol, market, interval, ts) DO UPDATE SET
      open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
      close = EXCLUDED.close, volume = EXCLUDED.volume
    """
)


async def upsert_bars(session: AsyncSession, rows: list[BarRow]) -> int:
    """Idempotent upsert of daily bars into the shared `bars` table. Returns row count."""
    if not rows:
        return 0
    params = [
        {
            "ts": r.ts, "symbol": r.symbol, "market": r.market, "interval": r.interval,
            "open": Decimal(str(r.open)), "high": Decimal(str(r.high)),
            "low": Decimal(str(r.low)), "close": Decimal(str(r.close)), "volume": r.volume,
        }
        for r in rows
    ]
    await session.execute(_UPSERT_BARS, params)
    return len(rows)


async def backfill_symbol(
    session: AsyncSession, provider, symbol: str, market: str, start: date, end: date
) -> int:
    """Fetch daily bars for [start, end] from `provider` and upsert them. Returns row count."""
    rows = await provider.get_daily_bars(symbol, start, end, market)
    return await upsert_bars(session, rows)
