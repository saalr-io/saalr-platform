import numpy as np

from saalr_ml.garch import (
    GarchParams,
    conditional_variance,
    fit_garch11,
    forecast_var,
    simulate_ci,
)


def _simulate_garch(n, omega, alpha, beta, mu=0.0, seed=7):
    rng = np.random.default_rng(seed)
    r = np.empty(n)
    sigma2 = omega / (1 - alpha - beta)
    resid_prev2 = sigma2
    for t in range(n):
        sigma2 = omega + alpha * resid_prev2 + beta * sigma2
        eps = np.sqrt(sigma2) * rng.standard_normal()
        r[t] = mu + eps
        resid_prev2 = eps * eps
    return r


def test_fit_recovers_known_params():
    # data from known GARCH(1,1); fit should land in the neighbourhood
    r = _simulate_garch(4000, omega=0.05, alpha=0.08, beta=0.90, seed=11)
    p = fit_garch11(r)
    assert isinstance(p, GarchParams)
    assert 0.0 <= p.alpha < 1.0 and 0.0 <= p.beta < 1.0
    assert p.alpha + p.beta < 1.0          # stationarity always enforced
    assert abs((p.alpha + p.beta) - 0.98) < 0.06   # persistence recovered roughly


def test_forecast_converges_to_unconditional():
    r = _simulate_garch(3000, omega=0.05, alpha=0.08, beta=0.90, seed=3)
    p = fit_garch11(r)
    sigma2, resid = conditional_variance(p, r)
    fc = forecast_var(p, sigma2[-1], resid[-1] ** 2, horizon=400)
    uncond = p.omega / (1 - p.alpha - p.beta)
    assert abs(fc[-1] - uncond) < 0.05 * uncond   # tail converges to unconditional variance


def test_conditional_variance_shapes_and_positive():
    r = _simulate_garch(500, omega=0.05, alpha=0.08, beta=0.90, seed=5)
    p = fit_garch11(r)
    sigma2, resid = conditional_variance(p, r)
    assert sigma2.shape == r.shape and resid.shape == r.shape
    assert np.all(sigma2 > 0)


def test_simulate_ci_brackets_point_and_is_deterministic():
    r = _simulate_garch(1000, omega=0.05, alpha=0.08, beta=0.90, seed=9)
    p = fit_garch11(r)
    sigma2, resid = conditional_variance(p, r)
    point = np.sqrt(forecast_var(p, sigma2[-1], resid[-1] ** 2, horizon=10) * 252)
    lo1, hi1 = simulate_ci(p, sigma2[-1], resid[-1] ** 2, horizon=10, n_paths=2000, seed=0)
    lo2, hi2 = simulate_ci(p, sigma2[-1], resid[-1] ** 2, horizon=10, n_paths=2000, seed=0)
    assert np.allclose(lo1, lo2) and np.allclose(hi1, hi2)   # deterministic under seed
    assert np.all(lo1 <= point + 1e-9) and np.all(point <= hi1 + 1e-9)  # brackets point
    assert np.all(hi1[1:] >= hi1[:-1] - 0.5)                 # band widens with horizon (MC tolerance)
