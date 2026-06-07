import numpy as np
import pytest

from saalr_ml.price_forecast import price_forecast


def _closes(n=300, seed=0):
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * 0.01 + 0.0003
    return 100.0 * np.exp(np.cumsum(rets))


def test_price_forecast_shape_and_models():
    out = price_forecast(_closes(), horizon=5, holdout_days=30, n_origins=2, lstm_epochs=5)
    assert out["horizon_days"] == 5
    assert out["primary_model"] in ("arima", "lstm", "naive")
    by = {m["model"]: m for m in out["models"]}
    assert set(by) == {"arima", "lstm", "naive"}
    for m in by.values():
        assert len(m["path"]) == 5
        assert m["direction"] in ("up", "down", "flat")
        assert 0.0 <= m["directional_accuracy"] <= 1.0
    assert by["naive"]["ci_95"] is None
    assert out["validation"]["n_origins"] == 2
    assert out["approximate"] is True and out["disclaimer"]


def test_price_forecast_primary_is_lowest_mae():
    out = price_forecast(_closes(seed=3), horizon=5, holdout_days=30, n_origins=2, lstm_epochs=5)
    maes = {m["model"]: m["holdout_mae"] for m in out["models"]}
    assert out["primary_model"] == min(maes, key=maes.get)


def test_price_forecast_rejects_short_history():
    with pytest.raises(ValueError, match="insufficient history"):
        price_forecast(_closes(n=100), horizon=5)
