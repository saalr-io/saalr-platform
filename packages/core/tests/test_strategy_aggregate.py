import math

from saalr_core.pricing.types import Greeks
from saalr_core.strategies.aggregate import net_greeks
from saalr_core.strategies.types import EquityLeg, OptionLeg, OptionType, Side


def _g(delta):
    return Greeks(price=1.0, delta=delta, gamma=0.01, theta=-0.02, vega=0.05, rho=0.0, iv=0.25)


def test_long_call_net_delta_scaled_by_100():
    leg = OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2026-12-18", 2, 5.0)
    out = net_greeks([(leg, _g(0.5))])
    assert math.isclose(out["delta"], 0.5 * 100 * 2, abs_tol=1e-9)
    assert math.isclose(out["gamma"], 0.01 * 100 * 2, abs_tol=1e-9)


def test_short_leg_flips_sign():
    leg = OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2026-12-18", 1, 5.0)
    out = net_greeks([(leg, _g(0.5))])
    assert math.isclose(out["delta"], -50.0, abs_tol=1e-9)


def test_equity_leg_contributes_delta_only():
    leg = EquityLeg(Side.BUY, 100, 50.0)
    out = net_greeks([(leg, None)])
    assert math.isclose(out["delta"], 100.0, abs_tol=1e-9)
    assert out["vega"] == 0.0
