from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .garch import conditional_variance, fit_garch11
from .har import fit_har, har_one_step


@dataclass(frozen=True)
class WalkForward:
    garch_mae: float
    hv21_mae: float
    har_mae: float
    lift: float
    primary: str
    holdout_days: int


def walk_forward(returns: np.ndarray, holdout_days: int = 40) -> WalkForward:
    """Score GARCH, HV21 and HAR one-step-ahead variance forecasts across the holdout against
    the realized-variance proxy r^2, and pick the lowest-MAE model as `primary`."""
    returns = np.asarray(returns, dtype=float)
    n = len(returns)
    if n < holdout_days + 22:  # HAR monthly lag needs 22 training days before the first holdout day
        raise ValueError("series too short for the requested holdout")
    train = returns[:-holdout_days]
    params = fit_garch11(train)

    sigma2, resid = conditional_variance(params, returns)
    idx = range(n - holdout_days, n)
    garch_fc = sigma2[n - holdout_days : n]
    realized = resid[n - holdout_days : n] ** 2
    hv_fc = np.array([np.var(returns[i - 21 : i]) for i in idx])

    rv = returns ** 2
    har_beta = fit_har(rv[:-holdout_days])
    har_fc = np.array([har_one_step(rv[:i], har_beta) for i in idx])

    garch_mae = float(np.mean(np.abs(garch_fc - realized)))
    hv21_mae = float(np.mean(np.abs(hv_fc - realized)))
    har_mae = float(np.mean(np.abs(har_fc - realized)))
    lift = (hv21_mae - garch_mae) / hv21_mae if hv21_mae > 0 else 0.0
    maes = {"garch": garch_mae, "hv21": hv21_mae, "har": har_mae}
    primary = min(maes, key=maes.get)
    return WalkForward(garch_mae, hv21_mae, har_mae, lift, primary, holdout_days)
