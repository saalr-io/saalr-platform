from __future__ import annotations

import numpy as np

MIN_CLOSES = 60

_DIR_TEXT = {
    "strong_bullish": "well above the 20- and 50-day averages, strong uptrend",
    "bullish": "above the 20- and 50-day averages, rising",
    "neutral": "hovering around the 20- and 50-day averages",
    "bearish": "below the 20- and 50-day averages, falling",
    "strong_bearish": "well below the 20- and 50-day averages, strong downtrend",
}
_DIR_HEAD = {"strong_bullish": "Strong bullish", "bullish": "Bullish", "neutral": "Neutral",
             "bearish": "Bearish", "strong_bearish": "Strong bearish"}
_VOL_HEAD = {"low": "Low vol", "normal": "Normal vol", "high": "High vol"}
_MOM_HEAD = {"trending": "Trending", "range_bound": "Range-bound"}


def trend_score(closes) -> float:
    c = np.asarray(closes, dtype=float)
    sma20 = float(np.mean(c[-20:]))
    sma50 = float(np.mean(c[-50:]))
    price = float(c[-1])
    blend = (np.sign(price - sma20) + np.sign(price - sma50) + np.sign(sma20 - sma50)) / 3.0
    prev20 = float(np.mean(c[-40:-20]))
    slope = (sma20 - prev20) / prev20 if prev20 else 0.0
    slope_c = max(-1.0, min(1.0, slope / 0.10))
    return float(0.4 * blend + 0.6 * slope_c)


def direction_label(t: float) -> str:
    if t >= 0.6:
        return "strong_bullish"
    if t >= 0.2:
        return "bullish"
    if t > -0.2:
        return "neutral"
    if t > -0.6:
        return "bearish"
    return "strong_bearish"


def _rolling_realized_vol(c, window: int = 20):
    logret = np.diff(np.log(c))
    out = []
    for i in range(window, len(logret) + 1):
        w = logret[i - window:i]
        out.append(float(np.std(w, ddof=1) * np.sqrt(252) * 100.0))
    return np.asarray(out, dtype=float)


def realized_vol_percentile(closes, window: int = 20, lookback: int = 252):
    c = np.asarray(closes, dtype=float)
    series = _rolling_realized_vol(c, window)
    if len(series) == 0:
        return 0.0, 1.0
    current = float(series[-1])
    tail = series[-min(lookback, len(series)):]
    pct = float(np.mean(tail <= current))
    return current, pct


def vol_label(pct: float) -> str:
    if pct > 0.66:
        return "high"
    if pct >= 0.33:
        return "normal"
    return "low"


def efficiency_ratio(closes, window: int = 20) -> float:
    c = np.asarray(closes, dtype=float)[-(window + 1):]
    net = abs(float(c[-1] - c[0]))
    path = float(np.sum(np.abs(np.diff(c))))
    return net / path if path else 0.0


def momentum_label(er: float) -> str:
    return "trending" if er >= 0.30 else "range_bound"


def vol_trend_label(garch_mean: float, realized: float) -> str:
    if garch_mean > realized * 1.10:
        return "rising"
    if garch_mean < realized * 0.90:
        return "falling"
    return "stable"


def _headline(d: str, v: str, m: str) -> str:
    return f"{_DIR_HEAD[d]} · {_VOL_HEAD[v]} · {_MOM_HEAD[m]}"


def classify_regime(closes) -> dict:
    c = np.asarray(closes, dtype=float)
    if len(c) < MIN_CLOSES:
        raise ValueError("insufficient history")
    t = trend_score(c)
    d_label = direction_label(t)
    cur_vol, pct = realized_vol_percentile(c)
    v_label = vol_label(pct)
    er = efficiency_ratio(c)
    m_label = momentum_label(er)
    return {
        "direction": {"label": d_label, "score": round(t, 4), "detail": f"price {_DIR_TEXT[d_label]}"},
        "volatility": {
            "label": v_label, "percentile": round(pct, 4), "realized_vol": round(cur_vol, 2),
            "detail": f"20-day realized vol {cur_vol:.1f}%, {round(pct * 100)}th percentile of the past year",
        },
        "momentum": {
            "label": m_label, "efficiency_ratio": round(er, 4),
            "detail": f"directional efficiency {er:.2f} — "
                      f"{'trending' if m_label == 'trending' else 'choppy / range-bound'}",
        },
        "headline": _headline(d_label, v_label, m_label),
        "last_close": round(float(c[-1]), 4),
        "n_closes": int(len(c)),
    }
