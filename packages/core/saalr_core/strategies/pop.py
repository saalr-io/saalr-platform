from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _lognormal_cdf(s: float, mu: float, sd: float) -> float:
    if s <= 0:
        return 0.0
    return _norm_cdf((math.log(s) - mu) / sd)


def probability_of_profit(
    spot: float,
    atm_iv: float,
    t_years: float,
    rate: float,
    div_yield: float,
    profit_intervals: list[tuple[float, float | None]],
) -> dict:
    """Approximate POP: terminal price ~ lognormal(ATM IV). Sums mass over profit intervals."""
    if t_years <= 0 or atm_iv <= 0 or spot <= 0:
        return {"pop": None, "method": "lognormal_atm_iv", "approximate": True}
    mu = math.log(spot) + (rate - div_yield - 0.5 * atm_iv * atm_iv) * t_years
    sd = atm_iv * math.sqrt(t_years)
    pop = 0.0
    for lo, hi in profit_intervals:
        upper = 1.0 if hi is None else _lognormal_cdf(hi, mu, sd)
        pop += upper - _lognormal_cdf(lo, mu, sd)
    return {"pop": max(0.0, min(1.0, pop)), "method": "lognormal_atm_iv", "approximate": True}
