from __future__ import annotations

import math

VOL_FLOOR = 0.01
TRADING_DAYS = 252


def log_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev > 0 and cur > 0:
            out.append(math.log(cur / prev))
    return out


def realized_vol(closes: list[float], lookback: int, periods: int = TRADING_DAYS) -> float:
    """Annualized stdev of the last `lookback` daily log returns. Floors at VOL_FLOOR
    on insufficient or degenerate (flat) data so BSM never divides by zero."""
    rets = log_returns(closes)
    window = rets[-lookback:] if lookback and len(rets) > lookback else rets
    if len(window) < 2:
        return VOL_FLOOR
    mu = sum(window) / len(window)
    var = sum((r - mu) ** 2 for r in window) / (len(window) - 1)
    vol = math.sqrt(var) * math.sqrt(periods)
    return max(vol, VOL_FLOOR)
