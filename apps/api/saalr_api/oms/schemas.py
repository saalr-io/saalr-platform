from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class BrokerAccountCreate(BaseModel):
    broker: str = "paper"
    account_label: str = Field(min_length=1)
    is_paper: bool = True
    credential_ref: str | None = None


class OrderCreate(BaseModel):
    broker_account_id: str
    symbol: str = Field(min_length=1)
    side: str
    qty: int
    order_type: str
    strategy_id: str | None = None
    option_type: str | None = None
    strike: Decimal | None = None
    expiry: date | None = None
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "day"


class LegSpec(BaseModel):
    kind: str                       # "option" | "equity" | "cash"
    side: str | None = None         # BUY | SELL (option/equity)
    qty: int | None = None
    option_type: str | None = None  # CALL | PUT
    strike: Decimal | None = None
    expiry: date | None = None
    amount: Decimal | None = None   # cash legs (ignored for orders)


class StrategyOrderCreate(BaseModel):
    broker_account_id: str
    underlying: str = Field(min_length=1)
    legs: list[LegSpec] = Field(min_length=1)
