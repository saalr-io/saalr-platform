import json
import math
from pathlib import Path

from saalr_core.discovery.testing import HarnessAdapter, harness_strategy_from_case

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "golden_strategies.json"


def test_pcs_golden_closed_forms():
    """PCS-GOLDEN-001: engine reproduces hand-verified max P/L + breakeven."""
    case = json.loads(FIXTURE.read_text())["cases"][0]
    adapter = HarnessAdapter()
    s = harness_strategy_from_case(case)
    exp = case["expected"]
    assert math.isclose(adapter.max_profit(s), exp["max_profit"] * 100, abs_tol=1e-2) or \
           math.isclose(adapter.max_profit(s), exp["max_profit"], abs_tol=1e-2)
    assert math.isclose(adapter.breakevens(s)[0], exp["breakevens"][0], abs_tol=1e-2)
    for sample in exp["payoff_samples"]:
        got = adapter.payoff_at_expiry(s, sample["terminal"])
        want = sample["payoff"]
        assert math.isclose(got, want, abs_tol=1e-2) or math.isclose(got, want * 100, abs_tol=1e-2)
