from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.pricing.greeks import price as bsm_price
from saalr_core.pricing.types import OptionKind, OptionParams

_RATE = 0.04
_VOL_FLOOR = 0.05
_TRADING_DAYS = 252


class NoMarketData(Exception):
    """No stored bar to price the order against."""


async def _closes(session: AsyncSession, symbol: str, market: str, limit: int = 40) -> list[float]:
    rows = (
        await session.execute(
            text("""SELECT close FROM bars
                    WHERE symbol=:s AND market=:m AND interval='1d'
                    ORDER BY ts DESC LIMIT :n"""),
            {"s": symbol, "m": market, "n": limit},
        )
    ).all()
    return [float(r.close) for r in reversed(rows)]  # oldest -> newest


def _realized_vol(closes: list[float]) -> float:
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    window = rets[-21:]
    if len(window) < 2:
        return _VOL_FLOOR
    mu = sum(window) / len(window)
    var = sum((r - mu) ** 2 for r in window) / (len(window) - 1)
    return max(math.sqrt(var) * math.sqrt(_TRADING_DAYS), _VOL_FLOOR)


async def model_mark(
    session: AsyncSession, *, symbol: str, market: str, option_type: str | None,
    strike: Decimal | None, expiry: date | None, today: date,
) -> Decimal:
    closes = await _closes(session, symbol, market)
    if not closes:
        raise NoMarketData(f"no bars for {symbol}")
    spot = closes[-1]
    if option_type is None:
        return Decimal(str(spot))
    if expiry is None:
        raise NoMarketData("option order missing expiry")
    t = (expiry - today).days / 365.0
    if t <= 0:
        raise NoMarketData("option expiry not in the future")
    sigma = _realized_vol(closes)
    kind = OptionKind.CALL if option_type.upper() in ("CALL", "CE") else OptionKind.PUT
    px = bsm_price(OptionParams(spot=spot, strike=float(strike), t_years=t, rate=_RATE,
                                sigma=sigma, div_yield=0.0, kind=kind))
    return Decimal(str(round(px, 4)))
