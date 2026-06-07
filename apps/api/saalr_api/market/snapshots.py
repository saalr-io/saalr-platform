from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.pricing.types import ContractGreeks


def _dec(value: float | None) -> Decimal | None:
    """asyncpg binds NUMERIC columns from Decimal, not float."""
    return None if value is None else Decimal(str(value))

_UPSERT = text(
    """
    INSERT INTO options_chain_snapshots
      (ts, underlying, market, expiry, strike, option_type,
       bid, ask, last, volume, open_interest, iv, delta, gamma, theta, vega)
    VALUES
      (:ts, :underlying, :market, :expiry, :strike, :option_type,
       :bid, :ask, :last, :volume, :open_interest, :iv, :delta, :gamma, :theta, :vega)
    ON CONFLICT (underlying, market, expiry, strike, option_type, ts)
    DO UPDATE SET
      bid = EXCLUDED.bid, ask = EXCLUDED.ask, last = EXCLUDED.last,
      volume = EXCLUDED.volume, open_interest = EXCLUDED.open_interest,
      iv = EXCLUDED.iv, delta = EXCLUDED.delta, gamma = EXCLUDED.gamma,
      theta = EXCLUDED.theta, vega = EXCLUDED.vega
    """
)


async def persist_chain(
    session: AsyncSession, underlying: str, market: str, ts: str, contracts: list[ContractGreeks]
) -> None:
    """Upsert our computed chain into the shared (non-tenant) options_chain_snapshots table."""
    if not contracts:
        return
    ts_dt = datetime.fromisoformat(ts)
    rows = [
        {
            "ts": ts_dt,
            "underlying": underlying,
            "market": market,
            "expiry": date.fromisoformat(c.expiry),
            "strike": _dec(c.strike),
            "option_type": c.kind.value,  # 'CALL' / 'PUT' (allowed by CHECK)
            "bid": _dec(c.bid),
            "ask": _dec(c.ask),
            "last": _dec(c.last),
            "volume": c.volume,
            "open_interest": c.open_interest,
            "iv": _dec(c.ours.iv),
            "delta": _dec(c.ours.delta),
            "gamma": _dec(c.ours.gamma),
            "theta": _dec(c.ours.theta),
            "vega": _dec(c.ours.vega),
        }
        for c in contracts
    ]
    await session.execute(_UPSERT, rows)
