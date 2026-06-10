from saalr_core.discovery.baseline import naive_atm_short_put
from saalr_core.discovery.types import CleanChain, CleanContract
from saalr_core.strategies.types import OptionType


def _chain():
    cs = [CleanContract("2026-07-10", k, OptionType.PUT, mid=2.0, iv=0.3, volume=10, open_interest=100)
          for k in (95.0, 100.0, 105.0)]
    return CleanChain("AAPL", "2026-06-10T20:00:00Z", 100.0, 0.0, tuple(cs))


def _fake_mc(legs, spot, t_years, sigma, rate, div_yield, seed):
    return {"pop": 0.62, "ev": 18.0}


def test_baseline_is_atm_short_put_with_pop_and_ev():
    b = naive_atm_short_put(_chain(), "2026-07-10", dte=30, rate=0.05, mc_pop=_fake_mc, seed=7)
    assert b["naive"] == "atm_short_put"
    assert b["pop"] == 0.62 and b["ev"] == 18.0
    assert b["strike"] == 100.0
