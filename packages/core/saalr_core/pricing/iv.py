from __future__ import annotations

import math
from dataclasses import replace

from .greeks import _norm_pdf, price
from .types import OptionKind, OptionParams

_LO, _HI = 1e-4, 5.0
_MAX_ITER = 100
_TOL = 1e-6


def _vega_raw(p: OptionParams) -> float:
    vt = p.sigma * math.sqrt(p.t_years)
    d1 = (math.log(p.spot / p.strike) + (p.rate - p.div_yield + 0.5 * p.sigma**2) * p.t_years) / vt
    return p.spot * math.exp(-p.div_yield * p.t_years) * _norm_pdf(d1) * math.sqrt(p.t_years)


def implied_vol(market_price: float, p: OptionParams) -> float | None:
    """Return implied volatility, or None when uncomputable (honest failure)."""
    if p.t_years <= 0 or market_price <= 0 or p.spot <= 0 or p.strike <= 0:
        return None

    disc_q = math.exp(-p.div_yield * p.t_years)
    disc_r = math.exp(-p.rate * p.t_years)
    fwd = p.spot * disc_q
    if p.kind is OptionKind.CALL:
        lo_bound, hi_bound = max(0.0, fwd - p.strike * disc_r), fwd
    else:
        lo_bound, hi_bound = max(0.0, p.strike * disc_r - fwd), p.strike * disc_r
    if market_price < lo_bound - _TOL or market_price > hi_bound + _TOL:
        return None  # violates no-arbitrage bounds

    def diff(sigma: float) -> float:
        return price(replace(p, sigma=sigma)) - market_price

    # Newton-Raphson, seeded at 0.2
    sigma = 0.2
    for _ in range(_MAX_ITER):
        f = diff(sigma)
        if abs(f) < _TOL:
            return sigma
        v = _vega_raw(replace(p, sigma=sigma))
        if v < 1e-8:
            break  # vega too small -> hand off to bisection
        step = f / v
        nxt = sigma - step
        if nxt <= _LO or nxt >= _HI or math.isnan(nxt):
            break
        sigma = nxt

    # Bisection fallback on [_LO, _HI]
    lo, hi = _LO, _HI
    flo = diff(lo)
    fhi = diff(hi)
    if flo * fhi > 0:
        return None  # no sign change -> no root in range
    for _ in range(_MAX_ITER):
        mid = 0.5 * (lo + hi)
        fm = diff(mid)
        if abs(fm) < _TOL:
            return mid
        if flo * fm < 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)
