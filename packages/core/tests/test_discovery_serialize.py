import pytest

from saalr_core.discovery.serialize import (
    FORBIDDEN,  # noqa: F401 — public API surface; tested implicitly via assert_compliant
    assert_compliant,
    serialize_candidate,
    DISCLOSURE_BLOCK_ID,
)
from saalr_core.discovery.types import Candidate
from saalr_core.strategies.types import OptionLeg, OptionType, Side, StrategyConfig


def _cand():
    legs = [OptionLeg(OptionType.PUT, Side.SELL, 100.0, "2026-07-10", 1, entry_price=1.71),
            OptionLeg(OptionType.PUT, Side.BUY, 95.0, "2026-07-10", 1, entry_price=0.62)]
    return Candidate("bull_put_spread", StrategyConfig("AAPL", legs), "2026-07-10", 30)


def test_serialized_candidate_has_no_imperative_language():
    m = {"net_premium": -109.0, "net_credit": 109.0, "max_profit": 109.0, "max_loss": 391.0,
         "risk_reward": 0.28, "breakevens": [98.9], "pop": 0.74, "pop_method": "monte_carlo",
         "pop_closed_form": 0.74, "ev": 31.0, "ev_to_risk": 0.079, "greeks": {"delta": 0.12},
         "percentiles": {}}
    out = serialize_candidate(_cand(), m, rank=1, profile="ev_to_risk")
    assert out["score_profile"] == "ev_to_risk"                 # COMPLY-2
    assert "_curve" not in out["metrics"]                       # internal field stripped
    assert_compliant(out["summary"])                            # COMPLY-1: no exception


def test_assert_compliant_rejects_advice():
    for bad in ("you should buy now", "we recommend this", "best trade today"):
        with pytest.raises(ValueError):
            assert_compliant(bad)


def test_disclosure_block_id_constant_present():
    assert DISCLOSURE_BLOCK_ID                                  # COMPLY-4
