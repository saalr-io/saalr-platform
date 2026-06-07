import numpy as np
import pytest

from saalr_ml.regime import (
    MIN_CLOSES, classify_regime, direction_label, efficiency_ratio, momentum_label,
    realized_vol_percentile, trend_score, vol_label, vol_trend_label,
)


def _ramp(n=120, step=0.004, start=100.0):
    return [start * (1 + step) ** i for i in range(n)]


def test_steady_uptrend_is_bullish_and_trending():
    c = _ramp()
    assert direction_label(trend_score(c)) in ("bullish", "strong_bullish")
    assert momentum_label(efficiency_ratio(c)) == "trending"


def test_flat_constant_is_neutral_range_bound():
    c = [100.0] * 120
    assert direction_label(trend_score(c)) == "neutral"
    assert momentum_label(efficiency_ratio(c)) == "range_bound"


def test_classify_raises_below_min_closes():
    with pytest.raises(ValueError):
        classify_regime([100.0] * (MIN_CLOSES - 1))


def test_classify_shape_and_headline():
    r = classify_regime(_ramp())
    assert set(r) >= {"direction", "volatility", "momentum", "headline", "last_close", "n_closes"}
    assert r["direction"]["label"] in ("bullish", "strong_bullish")
    assert "·" in r["headline"]
    assert r["n_closes"] == 120


def test_vol_percentile_is_high_when_recent_vol_spikes():
    rng = np.random.default_rng(0)
    calm = list(100 + np.cumsum(rng.normal(0, 0.15, 240)))
    storm = list(calm[-1] + np.cumsum(rng.normal(0, 2.5, 25)))
    _cur, pct = realized_vol_percentile(calm + storm)
    assert vol_label(pct) == "high"


def test_vol_trend_label_thresholds():
    assert vol_trend_label(25.0, 20.0) == "rising"
    assert vol_trend_label(16.0, 20.0) == "falling"
    assert vol_trend_label(20.5, 20.0) == "stable"
