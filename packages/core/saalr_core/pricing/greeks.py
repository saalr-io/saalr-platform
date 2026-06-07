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


def greeks(p: OptionParams) -> Greeks:
    d1, d2 = _d1_d2(p)
    disc_q = math.exp(-p.div_yield * p.t_years)
    disc_r = math.exp(-p.rate * p.t_years)
    sqrt_t = math.sqrt(p.t_years)
    pdf_d1 = _norm_pdf(d1)

    gamma = disc_q * pdf_d1 / (p.spot * p.sigma * sqrt_t)
    vega_raw = p.spot * disc_q * pdf_d1 * sqrt_t  # per 1.0 sigma
    common_theta = -(p.spot * disc_q * pdf_d1 * p.sigma) / (2 * sqrt_t)

    if p.kind is OptionKind.CALL:
        delta = disc_q * _norm_cdf(d1)
        theta_year = (
            common_theta
            - p.rate * p.strike * disc_r * _norm_cdf(d2)
            + p.div_yield * p.spot * disc_q * _norm_cdf(d1)
        )
        rho_raw = p.strike * p.t_years * disc_r * _norm_cdf(d2)  # per 1.0 rate
    else:
        delta = -disc_q * _norm_cdf(-d1)
        theta_year = (
            common_theta
            + p.rate * p.strike * disc_r * _norm_cdf(-d2)
            - p.div_yield * p.spot * disc_q * _norm_cdf(-d1)
        )
        rho_raw = -p.strike * p.t_years * disc_r * _norm_cdf(-d2)

    return Greeks(
        price=price(p),
        delta=delta,
        gamma=gamma,
        theta=theta_year / 365.0,
        vega=vega_raw / 100.0,
        rho=rho_raw / 100.0,
    )
