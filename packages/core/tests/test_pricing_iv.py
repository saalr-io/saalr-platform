import math

from saalr_core.pricing.greeks import price
from saalr_core.pricing.iv import implied_vol
from saalr_core.pricing.types import OptionKind, OptionParams


def _params(sigma, kind=OptionKind.CALL, s=100.0, k=100.0, t=0.5, r=0.03, q=0.0):
    return OptionParams(s, k, t, r, sigma, q, kind)


def test_round_trip_atm():
    p = _params(0.25)
    mkt = price(p)
    assert math.isclose(implied_vol(mkt, p), 0.25, abs_tol=1e-4)


def test_round_trip_deep_otm_uses_bisection():
    p = _params(0.6, k=160.0)  # far OTM call, low vega -> Newton struggles
    mkt = price(p)
    iv = implied_vol(mkt, p)
    assert iv is not None and math.isclose(iv, 0.6, abs_tol=1e-3)


def test_below_intrinsic_returns_none():
    p = _params(0.25, kind=OptionKind.CALL, s=120.0, k=100.0)
    intrinsic = 120.0 * math.exp(-0.0 * 0.5) - 100.0 * math.exp(-0.03 * 0.5)
    assert implied_vol(intrinsic - 1.0, p) is None


def test_expired_returns_none():
    p = _params(0.25, t=0.0)
    assert implied_vol(5.0, p) is None


def test_non_positive_price_returns_none():
    p = _params(0.25)
    assert implied_vol(0.0, p) is None
