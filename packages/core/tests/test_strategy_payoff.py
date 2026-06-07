from __future__ import annotations

import math
from datetime import date

from saalr_core.strategies.payoff import (
    breakevens,
    expiration_curve,
    max_pl,
    net_premium,
    profit_intervals,
    spot_grid,
    target_date_curve,
)
from saalr_core.strategies.types import OptionLeg, OptionType, Side


def _long_call(strike=100.0, entry=5.0, expiry="2026-12-18"):
    return OptionLeg(OptionType.CALL, Side.BUY, strike, expiry, 1, entry)


def test_long_call_curve_and_unbounded_profit():
    legs = [_long_call()]
    grid = spot_grid(legs, spot=100.0)
    curve = expiration_curve(legs, grid)
    m = max_pl(curve)
    assert m["unbounded_profit"] is True
    assert m["max_profit"] is None
    assert math.isclose(m["max_loss"], -500.0, abs_tol=1e-6)


def test_long_call_breakeven():
    legs = [_long_call(strike=100.0, entry=5.0)]
    grid = spot_grid(legs, spot=100.0)
    be = breakevens(expiration_curve(legs, grid))
    assert len(be) == 1 and math.isclose(be[0], 105.0, abs_tol=0.5)


def test_bull_call_spread_bounded():
    legs = [
        OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2026-12-18", 1, 6.0),
        OptionLeg(OptionType.CALL, Side.SELL, 110.0, "2026-12-18", 1, 2.0),
    ]
    grid = spot_grid(legs, spot=100.0)
    curve = expiration_curve(legs, grid)
    m = max_pl(curve)
    assert m["unbounded_profit"] is False and m["unbounded_loss"] is False
    assert math.isclose(net_premium(legs), 400.0, abs_tol=1e-6)
    assert math.isclose(m["max_profit"], 600.0, abs_tol=1.0)
    assert math.isclose(m["max_loss"], -400.0, abs_tol=1.0)


def test_short_call_unbounded_loss():
    legs = [OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2026-12-18", 1, 5.0)]
    grid = spot_grid(legs, spot=100.0)
    m = max_pl(expiration_curve(legs, grid))
    assert m["unbounded_loss"] is True and m["max_loss"] is None
    assert math.isclose(m["max_profit"], 500.0, abs_tol=1.0)


def test_profit_intervals_long_call():
    legs = [_long_call(strike=100.0, entry=5.0)]
    grid = spot_grid(legs, spot=100.0)
    curve = expiration_curve(legs, grid)
    intervals = profit_intervals(curve)
    assert len(intervals) == 1
    lo, hi = intervals[0]
    assert math.isclose(lo, 105.0, abs_tol=0.5) and hi is None


def test_target_date_equals_expiration_at_expiry():
    legs = [_long_call(strike=100.0, entry=5.0, expiry="2026-12-18")]
    grid = spot_grid(legs, spot=100.0)
    exp = expiration_curve(legs, grid)
    tgt = target_date_curve(
        legs, grid, eval_date=date(2026, 12, 18), rate=0.04, div_yield=0.0,
        iv_by_leg={0: 0.25},
    )
    for (s_e, p_e), (s_t, p_t) in zip(exp, tgt):
        assert math.isclose(p_e, p_t, abs_tol=1e-3)
