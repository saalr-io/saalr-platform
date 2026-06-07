import numpy as np

from saalr_ml.lstm import lstm_forecast


def _returns(n=320, seed=0):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n) * 0.01 + 0.0002  # raw log-returns


def test_lstm_forecast_shape_and_band():
    r = _returns()
    path, ci = lstm_forecast(r, horizon=10, last_close=100.0, seed=0, epochs=5)
    assert len(path) == 10 and len(ci) == 10
    assert all(np.isfinite(p) and p > 0 for p in path)
    for lo, hi in ci:
        assert lo <= hi


def test_lstm_forecast_is_deterministic():
    r = _returns()
    a, _ = lstm_forecast(r, horizon=6, last_close=100.0, seed=0, epochs=5)
    b, _ = lstm_forecast(r, horizon=6, last_close=100.0, seed=0, epochs=5)
    assert a == b
