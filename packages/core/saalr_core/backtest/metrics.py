# packages/core/saalr_core/backtest/metrics.py
from __future__ import annotations

import math

TRADING_DAYS = 252


def total_return(equity: list[float]) -> float:
    if len(equity) < 2 or equity[0] == 0:
        return 0.0
    return equity[-1] / equity[0] - 1.0


def annualized_return(equity: list[float], days: int) -> float:
    if len(equity) < 2 or equity[0] <= 0 or days <= 0:
        return 0.0
    growth = equity[-1] / equity[0]
    if growth <= 0:
        return -1.0
    years = days / 365.0
    return growth ** (1.0 / years) - 1.0


def daily_returns(equity: list[float]) -> list[float]:
    out: list[float] = []
    for prev, cur in zip(equity, equity[1:]):
        out.append(cur / prev - 1.0 if prev != 0 else 0.0)
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def sharpe(returns: list[float], rf: float = 0.0, periods: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    rf_daily = rf / periods
    excess = [r - rf_daily for r in returns]
    sd = _stdev(excess)
    if sd == 0:
        return 0.0
    return _mean(excess) / sd * math.sqrt(periods)


def sortino(returns: list[float], rf: float = 0.0, periods: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    rf_daily = rf / periods
    excess = [r - rf_daily for r in returns]
    downside = [min(0.0, e) for e in excess]
    dd = math.sqrt(sum(d * d for d in downside) / len(downside))
    if dd == 0:
        return 0.0
    return _mean(excess) / dd * math.sqrt(periods)


def max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < mdd:
                mdd = dd
    return mdd


def win_rate(trade_pnls: list[float]) -> float:
    if not trade_pnls:
        return 0.0
    return sum(1 for p in trade_pnls if p > 0) / len(trade_pnls)


def avg_trade_pnl(trade_pnls: list[float]) -> float:
    return sum(trade_pnls) / len(trade_pnls) if trade_pnls else 0.0
