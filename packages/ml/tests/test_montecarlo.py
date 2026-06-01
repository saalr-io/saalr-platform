from __future__ import annotations

import numpy as np

from saalr_core.strategies.payoff import (
    _leg_pnl_at_expiry,
    expiration_curve,
    profit_intervals,
    spot_grid,
)
from saalr_core.strategies.pop import probability_of_profit
from saalr_core.strategies.types import OptionLeg, OptionType, Side
from saalr_ml.montecarlo import monte_carlo_pop, sentiment_adjusted_drift, strategy_pnl


def _long_call(strike=100.0, expiry="2025-06-01", entry=2.5):
    return OptionLeg(OptionType.CALL, Side.BUY, strike, expiry, 1, entry)


def test_vectorized_payoff_matches_core_scalar():
    legs = [
        _long_call(100.0, entry=3.0),
        OptionLeg(OptionType.CALL, Side.SELL, 110.0, "2025-06-01", 1, 1.0),
    ]
    prices = np.array([80.0, 100.0, 105.0, 110.0, 130.0])
    vec = strategy_pnl(legs, prices)
    for i, s in enumerate(prices):
        scalar = sum(_leg_pnl_at_expiry(leg, float(s)) for leg in legs)
        assert abs(float(vec[i]) - scalar) < 1e-9


def test_long_call_pop_matches_lognormal_closed_form():
    spot, sigma, t, rate = 100.0, 0.25, 30 / 365, 0.05
    legs = [_long_call(100.0, entry=2.5)]
    mc = monte_carlo_pop(legs, spot, t, sigma, rate, paths=50000, seed=0)
    curve = expiration_curve(legs, spot_grid(legs, spot))
    ln = probability_of_profit(spot, sigma, t, rate, 0.0, profit_intervals(curve))
    assert abs(mc["pop"] - ln["pop"]) < 0.02   # MC sampling error at 50k paths is ~0.002


def test_histogram_determinism_and_bounds():
    legs = [_long_call(entry=2.5)]
    a = monte_carlo_pop(legs, 100.0, 30 / 365, 0.25, 0.05, paths=10000, seed=1)
    b = monte_carlo_pop(legs, 100.0, 30 / 365, 0.25, 0.05, paths=10000, seed=1)
    assert a["pop"] == b["pop"] and a["ev"] == b["ev"]          # deterministic per seed
    assert sum(a["histogram"]["counts"]) == 10000
    assert len(a["histogram"]["bin_edges"]) == 101              # bins + 1
    assert 0.0 <= a["pop"] <= 1.0
    assert a["model"] == "gbm_mc" and a["approximate"] is True


def test_sentiment_drift_raises_long_call_pop():
    legs = [_long_call(entry=2.5)]
    spot, sigma, t, rate = 100.0, 0.25, 30 / 365, 0.05
    base = monte_carlo_pop(legs, spot, t, sigma, rate, drift_adjust=0.0, paths=50000, seed=2)
    up = monte_carlo_pop(
        legs, spot, t, sigma, rate,
        drift_adjust=sentiment_adjusted_drift(0.8, sigma, t), paths=50000, seed=2,
    )
    down = monte_carlo_pop(
        legs, spot, t, sigma, rate,
        drift_adjust=sentiment_adjusted_drift(-0.8, sigma, t), paths=50000, seed=2,
    )
    assert up["pop"] > base["pop"] > down["pop"]


def test_rejects_nonpositive_inputs():
    legs = [_long_call(entry=2.5)]
    for bad in [dict(spot=0.0), dict(t_years=0.0), dict(sigma=0.0)]:
        kw = dict(spot=100.0, t_years=30 / 365, sigma=0.25, rate=0.05)
        kw.update(bad)
        try:
            monte_carlo_pop(legs, kw["spot"], kw["t_years"], kw["sigma"], kw["rate"])
            assert False, "expected ValueError"
        except ValueError:
            pass
