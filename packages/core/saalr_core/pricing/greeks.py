from __future__ import annotations

import math

from .types import Greeks, OptionKind, OptionParams

_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _d1_d2(p: OptionParams) -> tuple[float, float]:
    vt = p.sigma * math.sqrt(p.t_years)
    d1 = (math.log(p.spot / p.strike) + (p.rate - p.div_yield + 0.5 * p.sigma**2) * p.t_years) / vt
    return d1, d1 - vt


def price(p: OptionParams) -> float:
    d1, d2 = _d1_d2(p)
    disc_q = math.exp(-p.div_yield * p.t_years)
    disc_r = math.exp(-p.rate * p.t_years)
    if p.kind is OptionKind.CALL:
        return p.spot * disc_q * _norm_cdf(d1) - p.strike * disc_r * _norm_cdf(d2)
    return p.strike * disc_r * _norm_cdf(-d2) - p.spot * disc_q * _norm_cdf(-d1)
