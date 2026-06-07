from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# (expiry_iso, strike_rounded, option_type) -> open_interest
OiKey = tuple[str, float, str]


async def load_oi_history(
    session: AsyncSession, underlying: str, market: str
) -> dict[datetime, dict[OiKey, int]]:
    """Load every stored snapshot's per-contract open interest for an underlying,
    keyed by snapshot timestamp. The table is small + shared (non-tenant)."""
    rows = (await session.execute(
        text("SELECT ts, expiry, strike, option_type, open_interest "
             "FROM options_chain_snapshots WHERE underlying = :u AND market = :m"),
        {"u": underlying, "m": market},
    )).all()
    hist: dict[datetime, dict[OiKey, int]] = {}
    for r in rows:
        if r.open_interest is None:
            continue
        key: OiKey = (r.expiry.isoformat(), round(float(r.strike), 4), r.option_type)
        hist.setdefault(r.ts, {})[key] = int(r.open_interest)
    return hist
