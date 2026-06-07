from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def hv21(returns: np.ndarray) -> float:
    """Annualized stdev of the last 21 (scaled) daily returns -> vol PERCENT."""
    window = np.asarray(returns, dtype=float)[-21:]
    return float(np.std(window) * np.sqrt(TRADING_DAYS))
