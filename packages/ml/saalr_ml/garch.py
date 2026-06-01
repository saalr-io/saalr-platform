from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

TRADING_DAYS = 252


@dataclass(frozen=True)
class GarchParams:
    omega: float
    alpha: float
    beta: float
    mu: float


def conditional_variance(params: GarchParams, returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Filter the GARCH(1,1) conditional-variance series and residuals for `returns`
    (already scaled). sigma2[t] is the variance for day t given info up to t-1."""
    resid = returns - params.mu
    n = len(returns)
    sigma2 = np.empty(n)
    sigma2[0] = max(np.var(resid), 1e-8)
    for t in range(1, n):
        sigma2[t] = params.omega + params.alpha * resid[t - 1] ** 2 + params.beta * sigma2[t - 1]
    return sigma2, resid


def _neg_loglik(theta: np.ndarray, returns: np.ndarray) -> float:
    omega, alpha, beta, mu = theta
    if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1.0:
        return 1e12
    p = GarchParams(omega, alpha, beta, mu)
    sigma2, resid = conditional_variance(p, returns)
    if np.any(sigma2 <= 0):
        return 1e12
    ll = -0.5 * np.sum(np.log(2.0 * np.pi * sigma2) + resid**2 / sigma2)
    return 1e12 if not np.isfinite(ll) else -ll


def fit_garch11(returns: np.ndarray) -> GarchParams:
    """Maximum-likelihood GARCH(1,1) with constant mean, normal innovations.
    `returns` should already be scaled (×100) for optimizer conditioning."""
    returns = np.asarray(returns, dtype=float)
    var = float(np.var(returns))
    mu0 = float(np.mean(returns))
    alpha0, beta0 = 0.05, 0.90
    omega0 = max(var * (1 - alpha0 - beta0), 1e-6)
    x0 = np.array([omega0, alpha0, beta0, mu0])
    bounds = [(1e-9, None), (0.0, 0.9999), (0.0, 0.9999), (None, None)]
    constraints = [{"type": "ineq", "fun": lambda th: 1.0 - th[1] - th[2] - 1e-6}]
    res = minimize(
        _neg_loglik, x0, args=(returns,), method="SLSQP", bounds=bounds, constraints=constraints
    )
    omega, alpha, beta, mu = (float(v) for v in res.x)
    if alpha + beta >= 1.0:  # numerical guard: renormalize just below the unit root
        scale = (alpha + beta) / 0.999
        alpha, beta = alpha / scale, beta / scale
    return GarchParams(max(omega, 1e-9), max(alpha, 0.0), max(beta, 0.0), mu)


def forecast_var(
    params: GarchParams, last_sigma2: float, last_resid2: float, horizon: int
) -> np.ndarray:
    """Daily conditional-variance forecast for steps 1..horizon (scaled units)."""
    persistence = params.alpha + params.beta
    out = np.empty(horizon)
    prev = params.omega + params.alpha * last_resid2 + params.beta * last_sigma2
    out[0] = prev
    for k in range(1, horizon):
        prev = params.omega + persistence * prev
        out[k] = prev
    return out


def simulate_ci(
    params: GarchParams,
    last_sigma2: float,
    last_resid2: float,
    horizon: int,
    n_paths: int = 1000,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Simulation-based 95% band on the annualized vol forecast (percent) per step."""
    rng = np.random.default_rng(seed)
    sigma2 = np.full(n_paths, last_sigma2)
    resid2 = np.full(n_paths, last_resid2)
    vols = np.empty((horizon, n_paths))
    for k in range(horizon):
        sigma2 = params.omega + params.alpha * resid2 + params.beta * sigma2
        vols[k] = np.sqrt(sigma2 * TRADING_DAYS)  # annualized percent (scale cancels)
        resid = np.sqrt(sigma2) * rng.standard_normal(n_paths)
        resid2 = resid**2
    lo = np.percentile(vols, 2.5, axis=1)
    hi = np.percentile(vols, 97.5, axis=1)
    return lo, hi


def annualize_vol_pct(daily_var_scaled: np.ndarray | float) -> np.ndarray | float:
    """Scaled daily variance -> annualized vol PERCENT. The ×100 return-scaling and the
    ×100 percent conversion cancel, so this is just sqrt(var * 252)."""
    return np.sqrt(np.asarray(daily_var_scaled) * TRADING_DAYS)
