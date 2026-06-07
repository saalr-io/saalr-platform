from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_closes(
    session: AsyncSession, symbol: str, market: str, lookback_days: int = 900
) -> list[float]:
    """Daily closes for `symbol` over the trailing window (non-RLS shared `bars`)."""
    start = (datetime.now(timezone.utc).date()) - timedelta(days=lookback_days)
    rows = (
        await session.execute(
            text(
                """
                SELECT close FROM bars
                WHERE symbol = :sym AND market = :mkt AND interval = '1d' AND ts::date >= :s
                ORDER BY ts
                """
            ),
            {"sym": symbol, "mkt": market, "s": start},
        )
    ).all()
    return [float(r.close) for r in rows]
