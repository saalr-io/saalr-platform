from __future__ import annotations

import numpy as np

from saalr_core.strategies.types import (
    OPTION_MULTIPLIER,
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
)


def _leg_pnl_vec(leg, terminal: np.ndarray) -> np.ndarray:
    """Vectorized per-leg expiry P&L over an array of terminal prices.
    Mirrors saalr_core.strategies.payoff._leg_pnl_at_expiry (kept in sync by a test)."""
    if isinstance(leg, OptionLeg):
        if leg.option_type is OptionType.CALL:
            intrinsic = np.maximum(terminal - leg.strike, 0.0)
        else:
            intrinsic = np.maximum(leg.strike - terminal, 0.0)
        entry = leg.entry_price or 0.0
        return leg.side.sign * (intrinsic - entry) * OPTION_MULTIPLIER * leg.qty
    if isinstance(leg, EquityLeg):
        entry = leg.entry_price or 0.0
        return leg.side.sign * (terminal - entry) * leg.qty
    if isinstance(leg, CashLeg):
        return np.zeros_like(terminal)
    raise TypeError(f"unknown leg type {type(leg)}")


def strategy_pnl(legs, terminal: np.ndarray) -> np.ndarray:
    total = np.zeros_like(terminal)
    for leg in legs:
        total = total + _leg_pnl_vec(leg, terminal)
    return total


def sentiment_adjusted_drift(sentiment: float, sigma: float, t_years: float) -> float:
    """LLD §4.4: shift drift by ±0.5σ√t at sentiment extremes."""
    return float(sentiment * 0.5 * sigma * np.sqrt(t_years))


def monte_carlo_pop(
    legs,
    spot: float,
    t_years: float,
    sigma: float,
    rate: float,
    div_yield: float = 0.0,
    drift_adjust: float = 0.0,
    paths: int = 10000,
    seed: int = 0,
    hist_bins: int = 100,
) -> dict:
    """GBM Monte-Carlo of expiry P&L. Returns POP, EV, a P&L histogram, and percentiles."""
    if spot <= 0 or t_years <= 0 or sigma <= 0:
        raise ValueError("spot, t_years and sigma must be positive")
    rng = np.random.default_rng(seed)
    drift = (rate - div_yield - 0.5 * sigma**2) * t_years + drift_adjust
    diffusion = sigma * np.sqrt(t_years)
    z = rng.standard_normal(paths)
    terminal = spot * np.exp(drift + diffusion * z)
    pnl = strategy_pnl(legs, terminal)
    counts, edges = np.histogram(pnl, bins=hist_bins)
    return {
        "pop": float(np.mean(pnl > 0)),
        "ev": float(np.mean(pnl)),
        "paths": int(paths),
        "histogram": {
            "counts": [int(c) for c in counts],
            "bin_edges": [float(e) for e in edges],
        },
        "percentiles": {
            "p5": float(np.percentile(pnl, 5)),
            "p50": float(np.percentile(pnl, 50)),
            "p95": float(np.percentile(pnl, 95)),
        },
        "max_profit_observed": float(np.max(pnl)),
        "max_loss_observed": float(np.min(pnl)),
        "model": "gbm_mc",
        "approximate": True,
        "seed": int(seed),
    }
