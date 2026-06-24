from __future__ import annotations

from datetime import date

from saalr_core.discovery.pipeline import run_discovery, DiscoveryRequest
from saalr_core.discovery.types import CleanChain, CleanContract
from saalr_core.strategies.types import OptionType


def _chain(expiry="2026-07-10", spot=100.0):
    cs = []
    for k in range(80, 121, 5):
        for kind in (OptionType.CALL, OptionType.PUT):
            cs.append(CleanContract(expiry, float(k), kind, mid=2.0, iv=0.3, volume=50, open_interest=500))
    return CleanChain("AAPL", "2026-06-10T20:00:00Z", spot, 0.0, tuple(cs))


def _closes():
    # 60+ rising closes so classify_regime returns a real regime
    return [90.0 + i * 0.15 for i in range(80)]


def _mc(legs, spot, t_years, sigma, rate, div_yield, seed):
    return {"pop": 0.7, "ev": 25.0, "percentiles": {"p5": -300.0, "p50": 20.0, "p95": 110.0}}


def test_pipeline_returns_ranked_compliant_results():
    req = DiscoveryRequest(dte_min=0, dte_max=60, strike_window=5, profile="ev_to_risk",
                           top_n=5, families=["bull_put_spread", "bear_call_spread"])
    res = run_discovery(_chain(), _closes(), lambda t: 0.05, _mc, req, as_of_date=date(2026, 6, 10))
    assert res.results, "expected ranked results"
    assert len(res.results) <= 5
    assert res.scoring_profile == "ev_to_risk"
    assert res.baseline["naive"] == "atm_short_put"
    assert res.disclosure_block_id
    assert "direction" in res.regime
    for r in res.results:
        assert r["score_profile"] == "ev_to_risk"


def test_pipeline_quarantines_free_lunch():
    # force a free-lunch candidate by making the long leg almost free (huge credit)
    chain = _chain()
    cs = list(chain.contracts)
    cs = [
        CleanContract(c.expiry, c.strike, c.kind,
                      mid=(6.0 if (c.kind is OptionType.PUT and c.strike == 100.0) else
                           0.05 if (c.kind is OptionType.PUT and c.strike == 95.0) else c.mid),
                      iv=c.iv, volume=c.volume, open_interest=c.open_interest)
        for c in cs
    ]
    chain = CleanChain(chain.underlying, chain.as_of, chain.spot, chain.div_yield, tuple(cs))
    req = DiscoveryRequest(dte_min=0, dte_max=60, strike_window=5, profile="ev_to_risk",
                           top_n=20, families=["bull_put_spread"])
    res = run_discovery(chain, _closes(), lambda t: 0.05, _mc, req, as_of_date=date(2026, 6, 10))
    assert any(d.get("reason") == "free_lunch" for d in res.data_quality_report)
    for r in res.results:
        legs = {(leg["strike"]) for leg in r["legs"]}
        assert not (legs == {100.0, 95.0} and r["metrics"]["net_credit"] > 500.0)
