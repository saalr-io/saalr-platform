from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from .repo import latest_bar_ts, list_active_instruments, upsert_bars


async def backfill_symbol(session: AsyncSession, provider, symbol: str, market: str,
                          start: date, end: date) -> int:
    rows = await provider.get_daily_bars(symbol, start, end, market)
    return await upsert_bars(session, rows)


async def run_incremental(session: AsyncSession, provider, default_days: int,
                          today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    counts: dict[str, int] = {}
    for inst in await list_active_instruments(session):
        last = await latest_bar_ts(session, inst.symbol, inst.market, "1d")
        start = (last.date() + timedelta(days=1)) if last else (today - timedelta(days=default_days))
        if start > today:
            counts[inst.symbol] = 0
            continue
        rows = await provider.get_daily_bars(inst.symbol, start, today, inst.market)
        counts[inst.symbol] = await upsert_bars(session, rows)
    return counts
