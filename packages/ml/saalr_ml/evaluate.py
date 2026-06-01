from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .garch import conditional_variance, fit_garch11


@dataclass(frozen=True)
class WalkForward:
    garch_mae: float
    hv21_mae: float
    lift: float
    primary: str
    holdout_days: int


def walk_forward(returns: np.ndarray, holdout_days: int = 40) -> WalkForward:
    """Fit GARCH on the training window, forward-filter across the holdout, and score
    GARCH vs HV21 one-step-ahead variance forecasts against the realized-variance proxy r^2."""
    returns = np.asarray(returns, dtype=float)
    n = len(returns)
    if n < holdout_days + 21:  # need ≥21 training returns before the first holdout day for HV21
        raise ValueError("series too short for the requested holdout")
    train = returns[:-holdout_days]
    params = fit_garch11(train)

    # GARCH 1-step variance forecast for each day = the filtered conditional variance
    # (variance for day t given info up to t-1), produced by running the fitted recursion
    # forward across the FULL series.
    sigma2, resid = conditional_variance(params, returns)
    idx = range(n - holdout_days, n)
    garch_fc = sigma2[n - holdout_days : n]
    realized = resid[n - holdout_days : n] ** 2

    # HV21 1-step forecast = variance of the trailing 21 returns ending the day before
    hv_fc = np.array([np.var(returns[i - 21 : i]) for i in idx])

    garch_mae = float(np.mean(np.abs(garch_fc - realized)))
    hv21_mae = float(np.mean(np.abs(hv_fc - realized)))
    lift = (hv21_mae - garch_mae) / hv21_mae if hv21_mae > 0 else 0.0
    primary = "garch" if garch_mae < hv21_mae else "hv21"
    return WalkForward(garch_mae, hv21_mae, lift, primary, holdout_days)
