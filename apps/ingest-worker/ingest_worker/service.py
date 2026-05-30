from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .repo import latest_bar_ts, list_active_instruments, upsert_bars


async def backfill_symbol(session: AsyncSession, provider, symbol: str, market: str,
                          start: date, end: date) -> int:
    rows = await provider.get_daily_bars(symbol, start, end, market)
    return await upsert_bars(session, rows)


async def incremental_symbol(session: AsyncSession, provider, symbol: str, market: str,
                             default_days: int, today: date) -> int:
    """Append daily bars for one symbol since its latest stored bar.

    INVARIANT: `Bar.ts` is the UTC-dated session day (Massive's epoch maps to that
    calendar date), so `latest.date() + 1 day` is the next day to fetch. Re-fetching
    a stored day would be harmless anyway (idempotent upsert); the +1 just avoids
    re-pulling the last stored day every run.
    """
    last = await latest_bar_ts(session, symbol, market, "1d")
    start = (last.date() + timedelta(days=1)) if last else (today - timedelta(days=default_days))
    if start > today:
        return 0
    rows = await provider.get_daily_bars(symbol, start, today, market)
    return await upsert_bars(session, rows)


async def run_incremental(session: AsyncSession, provider, default_days: int,
                          today: date | None = None) -> dict[str, int]:
    """Incremental append for all active instruments within a single session.

    The CLI uses `incremental_symbol` directly (one transaction per symbol) for
    crash isolation; this single-session helper is convenient for tests/small runs.
    """
    today = today or datetime.now(timezone.utc).date()
    counts: dict[str, int] = {}
    for inst in await list_active_instruments(session):
        counts[inst.symbol] = await incremental_symbol(
            session, provider, inst.symbol, inst.market, default_days, today
        )
    return counts
