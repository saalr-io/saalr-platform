import math

from saalr_core.discovery.metrics import candidate_metrics
from saalr_core.discovery.types import Candidate
from saalr_core.strategies.types import OptionLeg, OptionType, Side, StrategyConfig


def _pcs() -> Candidate:
    # put credit spread: short 100P @1.7158, long 95P @0.6181 (golden PCS-GOLDEN-001)
    legs = [
        OptionLeg(OptionType.PUT, Side.SELL, 100.0, "2026-07-10", 1, entry_price=1.7158),
        OptionLeg(OptionType.PUT, Side.BUY, 95.0, "2026-07-10", 1, entry_price=0.6181),
    ]
    return Candidate("bull_put_spread", StrategyConfig("AAPL", legs), "2026-07-10", 30)


def _fake_mc(legs, spot, t_years, sigma, rate, div_yield, seed):
    return {"pop": 0.74, "ev": 31.0, "percentiles": {"p5": -390.0, "p50": 50.0, "p95": 110.0}}


def test_metrics_closed_form_extremes_match_textbook():
    m = candidate_metrics(_pcs(), spot=105.0, atm_iv=0.30, rate=0.05, div_yield=0.0,
                          mc_pop=_fake_mc, seed=7)
    # credit = (1.7158-0.6181)*100 = 109.77 ; width = 5*100 = 500 ; max loss = 390.23
    assert math.isclose(m["net_credit"], 109.77, abs_tol=1e-2)
    assert math.isclose(m["max_profit"], 109.77, abs_tol=1e-2)
    assert math.isclose(m["max_loss"], 390.23, abs_tol=1e-2)
    assert math.isclose(m["breakevens"][0], 98.9023, abs_tol=1e-3)
    assert m["defined_risk"] is True            # STRUCT-3: finite max loss
    assert m["pop"] == 0.74 and m["pop_method"] == "monte_carlo"
    assert m["pop_closed_form"] is not None     # PROB-1 cross-check value present
    assert "delta" in m["greeks"]


def test_unbounded_loss_marks_not_defined_risk():
    # naked short call: unbounded loss to the upside
    legs = [OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2026-07-10", 1, entry_price=2.0)]
    cand = Candidate("short_call", StrategyConfig("AAPL", legs), "2026-07-10", 30)
    m = candidate_metrics(cand, spot=100.0, atm_iv=0.3, rate=0.05, div_yield=0.0,
                          mc_pop=_fake_mc, seed=7)
    assert m["max_loss"] is None
    assert m["defined_risk"] is False
