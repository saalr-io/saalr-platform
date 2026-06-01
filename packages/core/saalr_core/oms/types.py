from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# risk reason codes
RISK_INVALID_QUANTITY = "RISK_INVALID_QUANTITY"
RISK_INVALID_ORDER_TYPE = "RISK_INVALID_ORDER_TYPE"
RISK_INVALID_SIDE = "RISK_INVALID_SIDE"
RISK_INVALID_TIF = "RISK_INVALID_TIF"
RISK_MISSING_LIMIT_PRICE = "RISK_MISSING_LIMIT_PRICE"
RISK_MISSING_STOP_PRICE = "RISK_MISSING_STOP_PRICE"
RISK_ACCOUNT_INACTIVE = "RISK_ACCOUNT_INACTIVE"
RISK_STRATEGY_NOT_EXECUTABLE = "RISK_STRATEGY_NOT_EXECUTABLE"
RISK_INSUFFICIENT_BUYING_POWER = "RISK_INSUFFICIENT_BUYING_POWER"
RISK_RATE_LIMIT_EXCEEDED = "RISK_RATE_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class OrderRequest:
    side: str
    qty: int
    order_type: str
    symbol: str
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "day"
    option_type: str | None = None
    strike: Decimal | None = None
    expiry: date | None = None


@dataclass(frozen=True)
class RiskContext:
    account_active: bool
    strategy_state: str | None
    available_balance: Decimal
    estimated_cost: Decimal
    recent_order_count: int = 0
    rate_limit: int | None = None


@dataclass(frozen=True)
class RiskDecision:
    ok: bool
    code: str | None = None
    message: str | None = None
