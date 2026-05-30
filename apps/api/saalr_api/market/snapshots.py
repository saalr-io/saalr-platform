from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.pricing.types import ContractGreeks

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
    rows = [
        {
            "ts": ts,
            "underlying": underlying,
            "market": market,
            "expiry": c.expiry,
            "strike": c.strike,
            "option_type": c.kind.value,  # 'CALL' / 'PUT' (allowed by CHECK)
            "bid": c.bid,
            "ask": c.ask,
            "last": c.last,
            "volume": c.volume,
            "open_interest": c.open_interest,
            "iv": c.ours.iv,
            "delta": c.ours.delta,
            "gamma": c.ours.gamma,
            "theta": c.ours.theta,
            "vega": c.ours.vega,
        }
        for c in contracts
    ]
    await session.execute(_UPSERT, rows)
