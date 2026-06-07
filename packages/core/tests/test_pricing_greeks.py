import math
from dataclasses import replace

from saalr_core.pricing.greeks import greeks, price
from saalr_core.pricing.types import OptionKind, OptionParams


def _p(kind, sigma=0.2, t=1.0, r=0.05, q=0.0, s=100.0, k=100.0):
    return OptionParams(spot=s, strike=k, t_years=t, rate=r, sigma=sigma, div_yield=q, kind=kind)


def test_call_price_hull_textbook():
    # Hull: S=42, K=40, r=0.10, sigma=0.20, T=0.5 -> call ~= 4.759
    p = OptionParams(42, 40, 0.5, 0.10, 0.20, 0.0, OptionKind.CALL)
    assert math.isclose(price(p), 4.759, abs_tol=1e-3)


def test_put_price_hull_textbook():
    # Same inputs -> put ~= 0.808
    p = OptionParams(42, 40, 0.5, 0.10, 0.20, 0.0, OptionKind.PUT)
    assert math.isclose(price(p), 0.808, abs_tol=1e-3)


def test_put_call_parity():
    # C - P = S*e^{-qT} - K*e^{-rT}
    c = price(_p(OptionKind.CALL, q=0.02))
    pp = price(_p(OptionKind.PUT, q=0.02))
    lhs = c - pp
    rhs = 100.0 * math.exp(-0.02 * 1.0) - 100.0 * math.exp(-0.05 * 1.0)
    assert math.isclose(lhs, rhs, abs_tol=1e-9)


def _fd(p, attr, h, fn):
    up = replace(p, **{attr: getattr(p, attr) + h})
    dn = replace(p, **{attr: getattr(p, attr) - h})
    return (fn(up) - fn(dn)) / (2 * h)


def test_delta_matches_fd():
    p = _p(OptionKind.CALL, q=0.01)
    g = greeks(p)
    assert math.isclose(g.delta, _fd(p, "spot", 1e-4, price), abs_tol=1e-4)


def test_gamma_matches_fd():
    p = _p(OptionKind.CALL, q=0.01)
    g = greeks(p)
    fd2 = (price(replace(p, spot=p.spot + 1e-2)) - 2 * price(p) + price(replace(p, spot=p.spot - 1e-2))) / 1e-4
    assert math.isclose(g.gamma, fd2, abs_tol=1e-3)


def test_vega_matches_fd_per_vol_point():
    p = _p(OptionKind.CALL, q=0.01)
    g = greeks(p)
    raw = _fd(p, "sigma", 1e-4, price)  # dPrice/dSigma (per 1.0)
    assert math.isclose(g.vega, raw / 100.0, abs_tol=1e-4)


def test_theta_matches_fd_per_day():
    p = _p(OptionKind.PUT, q=0.01)
    g = greeks(p)
    # dPrice/dT is sensitivity to increasing maturity; theta is decay = -that, per day
    dprice_dT = _fd(p, "t_years", 1e-4, price)
    assert math.isclose(g.theta, -dprice_dT / 365.0, abs_tol=1e-3)


def test_rho_matches_fd_per_rate_point():
    p = _p(OptionKind.CALL, q=0.01)
    g = greeks(p)
    raw = _fd(p, "rate", 1e-5, price)  # dPrice/dRate (per 1.0)
    assert math.isclose(g.rho, raw / 100.0, abs_tol=1e-3)
