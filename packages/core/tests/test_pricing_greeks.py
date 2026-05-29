import math

from saalr_core.pricing.greeks import price
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
