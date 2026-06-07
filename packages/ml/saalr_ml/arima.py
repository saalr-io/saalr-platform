from __future__ import annotations

import warnings

import numpy as np

_ORDERS = [(p, d, q) for p in (0, 1, 2) for d in (0, 1) for q in (0, 1, 2)]


def arima_forecast(log_closes, horizon: int) -> tuple[list[float], list[list[float]], tuple]:
    """Fit ARIMA on log-price (AIC over a small grid) and forecast a PRICE path with a 95%
    prediction band. Returns (price_path, ci95_price, order)."""
    from statsmodels.tsa.arima.model import ARIMA

    y = np.asarray(log_closes, dtype=float)
    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for order in _ORDERS:
            try:
                res = ARIMA(y, order=order).fit()
            except Exception:  # noqa: BLE001 - skip non-converging orders
                continue
            if np.isfinite(res.aic) and (best is None or res.aic < best[0]):
                best = (res.aic, order, res)
    if best is None:
        raise ValueError("ARIMA failed to fit")
    _, order, res = best
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fc = res.get_forecast(steps=horizon)
        mean_log = np.asarray(fc.predicted_mean, dtype=float)
        ci_log = np.asarray(fc.conf_int(alpha=0.05), dtype=float)  # (horizon, 2)
    path = np.exp(mean_log)
    ci = np.exp(ci_log)
    return (
        [round(float(x), 4) for x in path],
        [[round(float(lo), 4), round(float(hi), 4)] for lo, hi in ci],
        tuple(int(v) for v in order),
    )
