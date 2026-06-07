from __future__ import annotations

import numpy as np

_TRADING_DAYS = 252


def _har_design(rv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Build (X, y) for HAR: target rv[t]; features [1, rv_d, rv_w, rv_m] from info up to t-1.
    Rows start at t=22 (monthly lag needs 22 trailing days)."""
    rv = np.asarray(rv, dtype=float)
    n = len(rv)
    rows_x, rows_y = [], []
    for t in range(22, n):
        rv_d = rv[t - 1]
        rv_w = rv[t - 5:t].mean()
        rv_m = rv[t - 22:t].mean()
        rows_x.append([1.0, rv_d, rv_w, rv_m])
        rows_y.append(rv[t])
    return np.asarray(rows_x, dtype=float), np.asarray(rows_y, dtype=float)


def fit_har(rv: np.ndarray) -> np.ndarray:
    """OLS fit of the 4 HAR coefficients [intercept, daily, weekly, monthly]."""
    x, y = _har_design(rv)
    if len(y) == 0:
        raise ValueError("series too short for HAR (need > 22 daily variances)")
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return beta


def har_one_step(rv_hist: np.ndarray, beta: np.ndarray) -> float:
    """Next-day variance from a variance history (>= 22 long), clamped non-negative."""
    rv_hist = np.asarray(rv_hist, dtype=float)
    feats = np.array([1.0, rv_hist[-1], rv_hist[-5:].mean(), rv_hist[-22:].mean()])
    return max(float(beta @ feats), 1e-12)


def har_rv_forecast(returns: np.ndarray, horizon: int) -> list[float]:
    """Annualized vol-PERCENT path of length `horizon`. `returns` are scaled (×100) log-returns;
    the daily realized-variance proxy is rv = returns**2 (no intraday data available)."""
    returns = np.asarray(returns, dtype=float)
    rv = returns ** 2
    beta = fit_har(rv)
    hist = list(rv)
    out = []
    for _ in range(horizon):
        nxt = har_one_step(np.asarray(hist), beta)
        out.append(round(float(np.sqrt(nxt * _TRADING_DAYS)), 4))
        hist.append(nxt)
    return out
