import numpy as np
import pytest

from saalr_ml.har import fit_har, har_one_step, har_rv_forecast


def test_fit_har_recovers_linear_relationship():
    # rv[t] generated as a known linear fn of its daily/weekly/monthly lags + tiny noise
    rng = np.random.default_rng(0)
    n = 400
    rv = np.abs(rng.standard_normal(n)) * 0.5 + 1.0  # positive variances
    beta = fit_har(rv)
    assert beta.shape == (4,)
    # one-step prediction is finite and non-negative
    pred = har_one_step(rv, beta)
    assert np.isfinite(pred) and pred >= 0


def test_har_rv_forecast_shape_and_positive():
    rng = np.random.default_rng(1)
    returns = rng.standard_normal(500) * 1.0  # scaled (×100) returns
    path = har_rv_forecast(returns, horizon=10)
    assert len(path) == 10
    assert all(np.isfinite(x) and x >= 0 for x in path)


def test_fit_har_rejects_short_series():
    with pytest.raises(ValueError):
        fit_har(np.ones(10))
