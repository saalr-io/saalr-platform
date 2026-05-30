# packages/core/saalr_core/backtest/engine.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from saalr_core.pricing.greeks import price as bsm_price
from saalr_core.pricing.types import OptionKind, OptionParams
from saalr_core.strategies.types import (
    OPTION_MULTIPLIER,
    EquityLeg,
    Leg,
    OptionLeg,
    OptionType,
)

from . import metrics as _m
from .template import RelativeTemplate
from .vol import realized_vol

ENGINE_VERSION = "bt-engine-1"


@dataclass(frozen=True)
class BacktestParams:
    start: date
    end: date
    initial_capital: float = 100_000.0
    rate: float = 0.04
    vol_lookback: int = 20
    include_costs: bool = True
    commission_per_contract: float = 0.65
    slippage_per_contract: float = 0.50
    strike_increment: float = 1.0


def _kind(ot: OptionType) -> OptionKind:
    return OptionKind.CALL if ot is OptionType.CALL else OptionKind.PUT


def _intrinsic(ot: OptionType, spot: float, strike: float) -> float:
    return max(0.0, spot - strike) if ot is OptionType.CALL else max(0.0, strike - spot)


def _option_unit_value(leg: OptionLeg, spot: float, sigma: float, t_years: float, rate: float) -> float:
    if t_years <= 0:
        return _intrinsic(leg.option_type, spot, leg.strike)
    return bsm_price(
        OptionParams(
            spot=spot, strike=leg.strike, t_years=t_years, rate=rate,
            sigma=sigma, div_yield=0.0, kind=_kind(leg.option_type),
        )
    )


def _position_value(legs: list[Leg], spot: float, sigma: float, d: date, rate: float) -> float:
    """Signed mark value of the position (what it is worth to liquidate now).
    Short legs contribute negative value; per-leg time decays to its own expiry."""
    total = 0.0
    for leg in legs:
        if isinstance(leg, OptionLeg):
            expiry = date.fromisoformat(leg.expiry)
            t = max(0, (expiry - d).days) / 365.0
            unit = _option_unit_value(leg, spot, sigma, t, rate)
            total += leg.side.sign * leg.qty * OPTION_MULTIPLIER * unit
        elif isinstance(leg, EquityLeg):
            total += leg.side.sign * leg.qty * spot
        # CashLeg contributes no P&L
    return total


def _cycle_cost(legs: list[Leg], params: BacktestParams) -> float:
    if not params.include_costs:
        return 0.0
    contracts = sum(leg.qty for leg in legs if isinstance(leg, OptionLeg))
    return contracts * (params.commission_per_contract + params.slippage_per_contract)


def run_backtest_engine(
    closes: dict[date, float], template: RelativeTemplate, params: BacktestParams
) -> dict:
    if not closes:
        raise ValueError("no bars supplied for the underlying")
    all_dates = sorted(closes)
    sim_days = [d for d in all_dates if params.start <= d <= params.end]
    if len(sim_days) < 2:
        raise ValueError("need at least 2 trading days with bars in [start, end]")

    def vol_at(d: date) -> float:
        series = [closes[x] for x in all_dates if x <= d]
        return realized_vol(series, params.vol_lookback)

    equity_curve: list[float] = []
    trade_pnls: list[float] = []
    realized = 0.0

    def open_cycle(d: date) -> tuple[list[Leg], float, float, date]:
        legs = template.instantiate(d, closes[d], params.strike_increment)
        entry_value = _position_value(legs, closes[d], vol_at(d), d, params.rate)
        cost = _cycle_cost(legs, params)
        front_expiry = d + timedelta(days=template.cycle_dte)
        return legs, entry_value, cost, front_expiry

    legs, entry_value, open_cost, front_expiry = open_cycle(sim_days[0])

    for d in sim_days:
        if d >= front_expiry:
            # settle the current cycle at d (front legs intrinsic, longer legs marked)
            settle_value = _position_value(legs, closes[d], vol_at(d), d, params.rate)
            total_cost = open_cost + _cycle_cost(legs, params)
            cycle_pnl = (settle_value - entry_value) - total_cost
            realized += cycle_pnl
            trade_pnls.append(cycle_pnl)
            # close-and-reopen the full structure on this day
            legs, entry_value, open_cost, front_expiry = open_cycle(d)
        cur_value = _position_value(legs, closes[d], vol_at(d), d, params.rate)
        equity_curve.append(params.initial_capital + realized + (cur_value - entry_value - open_cost))

    # realize the final still-open cycle (for trade stats) if it never hit its front expiry
    last_d = sim_days[-1]
    if last_d < front_expiry:
        settle_value = _position_value(legs, closes[last_d], vol_at(last_d), last_d, params.rate)
        total_cost = open_cost + _cycle_cost(legs, params)
        trade_pnls.append((settle_value - entry_value) - total_cost)

    days_span = (sim_days[-1] - sim_days[0]).days
    returns = _m.daily_returns(equity_curve)
    metrics = {
        "total_return": _m.total_return(equity_curve),
        "annualized_return": _m.annualized_return(equity_curve, days_span),
        "sharpe": _m.sharpe(returns, params.rate),
        "sortino": _m.sortino(returns, params.rate),
        "max_drawdown": _m.max_drawdown(equity_curve),
        "win_rate": _m.win_rate(trade_pnls),
        "trades": len(trade_pnls),
        "avg_trade_pnl": _m.avg_trade_pnl(trade_pnls),
    }
    return {
        "metrics": metrics,
        "model": "bsm",
        "iv_source": "realized_vol",
        "rate": params.rate,
        "vol_lookback": params.vol_lookback,
        "include_costs": params.include_costs,
        "engine_version": ENGINE_VERSION,
        "approximate": True,
        "equity_points": len(equity_curve),
        "start": params.start.isoformat(),
        "end": params.end.isoformat(),
        "initial_capital": params.initial_capital,
        "final_equity": equity_curve[-1],
    }
