from __future__ import annotations

from .types import (
    OPTION_MULTIPLIER,
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
)

_TOL = 1e-6


def spot_grid(legs: list, spot: float, points: int = 161) -> list[float]:
    """Grid from 0 to ~2x the relevant range, with strikes included as exact points."""
    strikes = [leg.strike for leg in legs if isinstance(leg, OptionLeg)]
    hi = max([spot] + strikes) * 2.0
    step = hi / (points - 1)
    grid = [i * step for i in range(points)]
    grid.extend(s for s in strikes if 0 <= s <= hi)
    return sorted(set(grid))


def _leg_pnl_at_expiry(leg, s: float) -> float:
    if isinstance(leg, OptionLeg):
        if leg.option_type is OptionType.CALL:
            intrinsic = max(s - leg.strike, 0.0)
        else:
            intrinsic = max(leg.strike - s, 0.0)
        entry = leg.entry_price or 0.0
        return leg.side.sign * (intrinsic - entry) * OPTION_MULTIPLIER * leg.qty
    if isinstance(leg, EquityLeg):
        entry = leg.entry_price or 0.0
        return leg.side.sign * (s - entry) * leg.qty
    if isinstance(leg, CashLeg):
        return 0.0
    raise TypeError(f"unknown leg type {type(leg)}")


def expiration_curve(legs: list, grid: list[float]) -> list[tuple[float, float]]:
    return [(s, sum(_leg_pnl_at_expiry(leg, s) for leg in legs)) for s in grid]


def net_premium(legs: list) -> float:
    """Positive = net debit paid, negative = net credit received."""
    total = 0.0
    for leg in legs:
        if isinstance(leg, OptionLeg):
            total += leg.side.sign * (leg.entry_price or 0.0) * OPTION_MULTIPLIER * leg.qty
        elif isinstance(leg, EquityLeg):
            total += leg.side.sign * (leg.entry_price or 0.0) * leg.qty
    return total


def breakevens(curve: list[tuple[float, float]]) -> list[float]:
    out: list[float] = []
    for (s0, p0), (s1, p1) in zip(curve, curve[1:]):
        if p0 == 0.0:
            out.append(s0)
        elif (p0 < 0 < p1) or (p1 < 0 < p0):
            out.append(s0 + (s1 - s0) * (0 - p0) / (p1 - p0))
    return out


def max_pl(curve: list[tuple[float, float]]) -> dict:
    pnls = [p for _, p in curve]
    right_slope = curve[-1][1] - curve[-2][1]
    unbounded_profit = right_slope > _TOL
    unbounded_loss = right_slope < -_TOL
    return {
        "max_profit": None if unbounded_profit else max(pnls),
        "max_loss": None if unbounded_loss else min(pnls),
        "unbounded_profit": unbounded_profit,
        "unbounded_loss": unbounded_loss,
    }


def risk_reward(max_profit: float | None, max_loss: float | None) -> float | None:
    if max_profit is None or max_loss is None or max_loss == 0:
        return None
    return abs(max_profit) / abs(max_loss)


def profit_intervals(curve: list[tuple[float, float]]) -> list[tuple[float, float | None]]:
    """S-ranges where expiration P&L > 0. Trailing None hi means unbounded upside."""
    bes = breakevens(curve)
    # N breakevens produce N+1 segments: [0, be0], [be0, be1], ..., [beN, inf)
    lows = [0.0, *bes]
    highs: list[float | None] = [*bes, None]
    intervals: list[tuple[float, float | None]] = []
    for lo, hi in zip(lows, highs):
        mid_s = (lo + (hi if hi is not None else curve[-1][0])) / 2.0
        pnl_mid = min(curve, key=lambda c: abs(c[0] - mid_s))[1]
        if pnl_mid > 0:
            intervals.append((lo, hi))
    return intervals
