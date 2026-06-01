from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class BrokerOrder:
    symbol: str
    side: str               # "buy" | "sell"
    qty: int
    order_type: str         # "market" | "limit" | "stop" | "stop_limit"
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "day"   # "day" | "gtc" | "ioc" | "fok"
    option_type: str | None = None
    strike: Decimal | None = None
    expiry: date | None = None


@dataclass(frozen=True)
class BrokerOrderResult:
    broker_order_id: str
    status: str             # "submitted" | "rejected"
    rejected_reason: str | None = None


@dataclass(frozen=True)
class BrokerFill:
    broker_order_id: str
    broker_execution_id: str
    qty: int
    price: Decimal
    commission: Decimal = Decimal(0)


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    qty: int
    avg_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
