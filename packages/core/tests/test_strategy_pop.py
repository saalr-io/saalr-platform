import math

from saalr_core.strategies.pop import probability_of_profit


def _lognormal_p_above(spot, k, iv, t, r, q):
    mu = math.log(spot) + (r - q - 0.5 * iv * iv) * t
    sd = iv * math.sqrt(t)
    z = (math.log(k) - mu) / sd
    return 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def test_pop_long_call_matches_p_above_breakeven():
    out = probability_of_profit(
        spot=100.0, atm_iv=0.25, t_years=0.5, rate=0.04, div_yield=0.0,
        profit_intervals=[(105.0, None)],
    )
    expected = _lognormal_p_above(100.0, 105.0, 0.25, 0.5, 0.04, 0.0)
    assert math.isclose(out["pop"], expected, abs_tol=1e-9)
    assert out["method"] == "lognormal_atm_iv"
    assert out["approximate"] is True


def test_pop_in_unit_interval():
    out = probability_of_profit(100.0, 0.3, 0.25, 0.04, 0.0, [(95.0, 105.0)])
    assert 0.0 <= out["pop"] <= 1.0


def test_pop_two_intervals_sum():
    out = probability_of_profit(100.0, 0.3, 0.25, 0.04, 0.0, [(0.0, 90.0), (110.0, None)])
    a = probability_of_profit(100.0, 0.3, 0.25, 0.04, 0.0, [(0.0, 90.0)])["pop"]
    b = probability_of_profit(100.0, 0.3, 0.25, 0.04, 0.0, [(110.0, None)])["pop"]
    assert math.isclose(out["pop"], a + b, abs_tol=1e-9)
