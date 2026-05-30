from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.market_data import Bar, Instrument
from saalr_core.marketdata.aggregates import BarRow

_ADD_INSTRUMENT = text(
    """
    INSERT INTO instruments (symbol, market, name, is_active)
    VALUES (:symbol, :market, :name, true)
    ON CONFLICT (symbol, market) DO UPDATE SET name = EXCLUDED.name, is_active = true
    """
)

_UPSERT_BARS = text(
    """
    INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
    VALUES (:ts, :symbol, :market, :interval, :open, :high, :low, :close, :volume)
    ON CONFLICT (symbol, market, interval, ts) DO UPDATE SET
      open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
      close = EXCLUDED.close, volume = EXCLUDED.volume
    """
)


async def add_instrument(session: AsyncSession, symbol: str, market: str = "US", name: str | None = None) -> None:
    await session.execute(_ADD_INSTRUMENT, {"symbol": symbol, "market": market, "name": name})


async def list_active_instruments(session: AsyncSession, market: str | None = None) -> list[Instrument]:
    stmt = select(Instrument).where(Instrument.is_active.is_(True))
    if market is not None:
        stmt = stmt.where(Instrument.market == market)
    stmt = stmt.order_by(Instrument.symbol)
    return list((await session.execute(stmt)).scalars().all())


async def latest_bar_ts(session: AsyncSession, symbol: str, market: str, interval: str) -> datetime | None:
    return (
        await session.execute(
            select(func.max(Bar.ts)).where(
                Bar.symbol == symbol, Bar.market == market, Bar.interval == interval
            )
        )
    ).scalar_one_or_none()


async def upsert_bars(session: AsyncSession, rows: list[BarRow]) -> int:
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
