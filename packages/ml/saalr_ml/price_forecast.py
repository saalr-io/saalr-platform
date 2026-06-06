from __future__ import annotations

import numpy as np

from .arima import arima_forecast
from .lstm import lstm_forecast

_MIN_HISTORY = 250


def _naive_path(last_close: float, drift: float, horizon: int) -> np.ndarray:
    steps = np.arange(1, horizon + 1)
    return last_close * np.exp(drift * steps)


def _direction(expected_return_pct: float) -> str:
    if expected_return_pct > 0.5:
        return "up"
    if expected_return_pct < -0.5:
        return "down"
    return "flat"


def _origins(n: int, horizon: int, holdout_days: int, n_origins: int) -> list[int]:
    last = n - horizon - 1
    first = max(_MIN_HISTORY - 1, n - holdout_days)
    if last <= first:
        return [last] if last > 0 else []
    raw = np.linspace(first, last, n_origins, dtype=int)
    return sorted({int(o) for o in raw if o > 0})


def _walk_forward_multi(closes, horizon, holdout_days, n_origins, seed, lstm_epochs):
    closes = np.asarray(closes, dtype=float)
    agg = {m: {"errs": [], "dirs": []} for m in ("arima", "lstm", "naive")}
    for o in _origins(len(closes), horizon, holdout_days, n_origins):
        hist = closes[: o + 1]
        actual = closes[o + 1 : o + 1 + horizon]
        h = len(actual)
        if h == 0:
            continue
        log_hist = np.log(hist)
        rets = np.diff(log_hist)
        lc = float(hist[-1])
        preds = {
            "arima": np.asarray(arima_forecast(log_hist, h)[0], dtype=float),
            "lstm": np.asarray(lstm_forecast(rets, h, lc, seed=seed, epochs=lstm_epochs)[0], dtype=float),
            "naive": np.asarray(_naive_path(lc, float(rets.mean()), h), dtype=float),
        }
        for m, pth in preds.items():
            agg[m]["errs"].append(np.abs(pth - actual))
            agg[m]["dirs"].append(1.0 if np.sign(pth[-1] - lc) == np.sign(actual[-1] - lc) else 0.0)
    out = {}
    for m, a in agg.items():
        errs = np.concatenate(a["errs"]) if a["errs"] else np.array([0.0])
        out[m] = {"mae": float(np.mean(errs)), "dir_acc": float(np.mean(a["dirs"] or [0.0]))}
    return out


def price_forecast(
    closes,
    horizon: int,
    holdout_days: int = 60,
    n_origins: int = 5,
    seed: int = 0,
    lstm_epochs: int = 150,
) -> dict:
    """ARIMA + LSTM + naive price-path forecast with multi-origin walk-forward validation.
    Raises ValueError on < 250 closes."""
    closes = np.asarray(closes, dtype=float)
    if len(closes) < _MIN_HISTORY:
        raise ValueError("insufficient history")
    log_closes = np.log(closes)
    returns = np.diff(log_closes)
    last_close = float(closes[-1])
    drift = float(returns.mean())

    arima_path, arima_ci, _order = arima_forecast(log_closes, horizon)
    lstm_path, lstm_ci = lstm_forecast(returns, horizon, last_close, seed=seed, epochs=lstm_epochs)
    naive_path = [round(float(x), 4) for x in _naive_path(last_close, drift, horizon)]
    paths = {"arima": (arima_path, arima_ci), "lstm": (lstm_path, lstm_ci), "naive": (naive_path, None)}

    scores = _walk_forward_multi(closes, horizon, holdout_days, n_origins, seed, lstm_epochs)
    primary = min(scores, key=lambda m: scores[m]["mae"])

    models = []
    for m in ("arima", "lstm", "naive"):
        path, ci = paths[m]
        exp_ret = round((path[-1] / last_close - 1.0) * 100.0, 4)
        models.append({
            "model": m,
            "path": path,
            "ci_95": ci,
            "expected_return_pct": exp_ret,
            "direction": _direction(exp_ret),
            "holdout_mae": round(scores[m]["mae"], 6),
            "directional_accuracy": round(scores[m]["dir_acc"], 4),
        })
    return {
        "horizon_days": horizon,
        "last_close": round(last_close, 4),
        "primary_model": primary,
        "models": models,
        "validation": {"holdout_days": holdout_days, "n_origins": n_origins, "best_model": primary},
        "approximate": True,
        "disclaimer": "Educational. Daily price direction is near-random; the naive baseline often wins.",
    }
