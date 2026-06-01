from __future__ import annotations

import numpy as np
import pytest

from saalr_ml.forecast import vol_forecast
from saalr_ml.tests_helpers import simulate_garch


def _closes_from_returns(returns_scaled, p0=100.0):
    # returns are scaled (×100); de-scale to build a price path
    r = returns_scaled / 100.0
    return p0 * np.exp(np.cumsum(np.concatenate([[0.0], r])))


def test_vol_forecast_shape_and_honesty_fields():
    r = simulate_garch(600, omega=0.05, alpha=0.10, beta=0.88, seed=4)
    closes = _closes_from_returns(r)
    out = vol_forecast(closes, horizon=10)
    assert out["horizon_days"] == 10
    assert out["primary_model"] in ("garch", "hv21")
    assert len(out["primary_forecast"]) == 10
    assert out["model"] == "garch(1,1)" and out["approximate"] is True
    assert "garch_mae" in out["validation"] and "hv21_mae" in out["validation"]
    # exactly one alternative, naming the non-primary model
    alts = out["alternative_models"]
    assert len(alts) == 1 and alts[0]["model"] != out["primary_model"]
    # when GARCH loses, the alternative GARCH is explicitly flagged
    if out["primary_model"] == "hv21":
        assert alts[0]["status"] == "underperforming_baseline"


def test_vol_forecast_primary_matches_walk_forward_on_clustered_data():
    r = simulate_garch(2000, omega=0.05, alpha=0.12, beta=0.86, seed=21)
    closes = _closes_from_returns(r)
    out = vol_forecast(closes, horizon=5, holdout_days=60)
    assert out["primary_model"] == "garch"
    assert out["primary_ci_95"] is not None and len(out["primary_ci_95"]) == 5


def test_vol_forecast_rejects_short_history():
    with pytest.raises(ValueError, match="insufficient history"):
        vol_forecast(np.linspace(100, 110, 100), horizon=5)
