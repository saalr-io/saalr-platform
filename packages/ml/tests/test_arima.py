import numpy as np

from saalr_ml.arima import arima_forecast


def test_arima_forecast_shape_and_band():
    rng = np.random.default_rng(0)
    # log-price as a random walk with mild drift
    log_closes = np.cumsum(rng.standard_normal(300) * 0.01 + 0.0003) + np.log(100)
    path, ci, order = arima_forecast(log_closes, horizon=10)
    assert len(path) == 10 and len(ci) == 10
    assert all(np.isfinite(p) and p > 0 for p in path)
    for lo, hi in ci:
        assert lo <= hi
    assert len(order) == 3
