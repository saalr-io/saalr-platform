from __future__ import annotations

import numpy as np

from .baseline import hv21
from .evaluate import walk_forward
from .garch import GarchParams, conditional_variance, fit_garch11, forecast_var, simulate_ci

_SCALE = 100.0
_MIN_HISTORY = 250


def _round_list(xs) -> list[float]:
    return [round(float(x), 4) for x in xs]


def vol_forecast(closes, horizon: int, holdout_days: int = 40, seed: int = 0) -> dict:
    """Annualized vol forecast (percent) from a daily close series. Always reports GARCH
    and HV21; `primary` is chosen by the walk-forward holdout. Raises ValueError on too
    little history."""
    closes = np.asarray(closes, dtype=float)
    if len(closes) < _MIN_HISTORY:
        raise ValueError("insufficient history")
    returns = np.diff(np.log(closes)) * _SCALE

    wf = walk_forward(returns, holdout_days)

    params: GarchParams = fit_garch11(returns)
    sigma2, resid = conditional_variance(params, returns)
    fc_var = forecast_var(params, sigma2[-1], resid[-1] ** 2, horizon)
    garch_path = np.sqrt(fc_var * 252)  # annualized percent
    lo, hi = simulate_ci(params, sigma2[-1], resid[-1] ** 2, horizon, seed=seed)
    garch_ci = [[round(float(a), 4), round(float(b), 4)] for a, b in zip(lo, hi)]

    hv_path = np.full(horizon, hv21(returns))

    forecasts = {
        "garch": (_round_list(garch_path), garch_ci),
        "hv21": (_round_list(hv_path), None),
    }
    primary = wf.primary
    alt = "hv21" if primary == "garch" else "garch"
    alt_status = "baseline" if alt == "hv21" else "underperforming_baseline"

    return {
        "horizon_days": horizon,
        "primary_model": primary,
        "primary_forecast": forecasts[primary][0],
        "primary_ci_95": forecasts[primary][1],
        "alternative_models": [
            {
                "model": alt,
                "forecast": forecasts[alt][0],
                "status": alt_status,
                "delta_mae_vs_baseline": round(float(wf.garch_mae - wf.hv21_mae), 6),
            }
        ],
        "validation": {
            "holdout_days": wf.holdout_days,
            "garch_mae": round(float(wf.garch_mae), 6),
            "hv21_mae": round(float(wf.hv21_mae), 6),
            "lift": round(float(wf.lift), 6),
        },
        "model": "garch(1,1)",
        "iv_source": "realized_returns",
        "approximate": True,
        "params": {
            "omega": round(params.omega, 8),
            "alpha": round(params.alpha, 6),
            "beta": round(params.beta, 6),
        },
    }
