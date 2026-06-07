from __future__ import annotations

from decimal import Decimal

from .types import (
    RISK_ACCOUNT_INACTIVE,
    RISK_INSUFFICIENT_BUYING_POWER,
    RISK_INVALID_ORDER_TYPE,
    RISK_INVALID_QUANTITY,
    RISK_INVALID_SIDE,
    RISK_INVALID_TIF,
    RISK_MISSING_LIMIT_PRICE,
    RISK_MISSING_STOP_PRICE,
    RISK_RATE_LIMIT_EXCEEDED,
    RISK_STRATEGY_NOT_EXECUTABLE,
    OrderRequest,
    RiskContext,
    RiskDecision,
)

_OPTION_MULT = 100
_ORDER_TYPES = {"market", "limit", "stop", "stop_limit"}
_SIDES = {"buy", "sell"}
_TIFS = {"day", "gtc", "ioc", "fok"}
_EXECUTABLE_STATES = {"paper", "live"}


def _structural(o: OrderRequest, ctx: RiskContext) -> str | None:
    if o.qty <= 0:
        return RISK_INVALID_QUANTITY
    if o.side not in _SIDES:
        return RISK_INVALID_SIDE
    if o.order_type not in _ORDER_TYPES:
        return RISK_INVALID_ORDER_TYPE
    if o.time_in_force not in _TIFS:
        return RISK_INVALID_TIF
    if o.order_type in ("limit", "stop_limit") and (o.limit_price is None or o.limit_price <= 0):
        return RISK_MISSING_LIMIT_PRICE
    if o.order_type in ("stop", "stop_limit") and (o.stop_price is None or o.stop_price <= 0):
        return RISK_MISSING_STOP_PRICE
    return None


def _executable_state(o: OrderRequest, ctx: RiskContext) -> str | None:
    if not ctx.account_active:
        return RISK_ACCOUNT_INACTIVE
    if ctx.strategy_state is not None and ctx.strategy_state not in _EXECUTABLE_STATES:
        return RISK_STRATEGY_NOT_EXECUTABLE
    return None


def _buying_power(o: OrderRequest, ctx: RiskContext) -> str | None:
    if o.side == "buy" and ctx.estimated_cost > ctx.available_balance:
        return RISK_INSUFFICIENT_BUYING_POWER
    return None


def _rate_cap(o: OrderRequest, ctx: RiskContext) -> str | None:
    if ctx.rate_limit is not None and ctx.recent_order_count >= ctx.rate_limit:
        return RISK_RATE_LIMIT_EXCEEDED
    return None


_GATES = (_structural, _executable_state, _buying_power, _rate_cap)


def run_gates(order: OrderRequest, ctx: RiskContext) -> RiskDecision:
    """Run the pre-trade gates in order; return the FIRST failure, else ok."""
    for gate in _GATES:
        code = gate(order, ctx)
        if code is not None:
            return RiskDecision(ok=False, code=code, message=code.removeprefix("RISK_").replace("_", " ").lower())
    return RiskDecision(ok=True)


def estimate_cost(order: OrderRequest, mark: Decimal) -> Decimal:
    mult = _OPTION_MULT if order.option_type else 1
    return mark * order.qty * mult
