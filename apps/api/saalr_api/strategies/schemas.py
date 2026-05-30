from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from saalr_core.strategies.types import (
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
    Side,
    StrategyConfig,
)


class OptionLegIn(BaseModel):
    kind: Literal["option"] = "option"
    option_type: OptionType
    side: Side
    strike: float = Field(gt=0)
    expiry: str
    qty: int = Field(gt=0)
    entry_price: float | None = None

    def to_domain(self) -> OptionLeg:
        return OptionLeg(self.option_type, self.side, self.strike, self.expiry, self.qty, self.entry_price)


class EquityLegIn(BaseModel):
    kind: Literal["equity"] = "equity"
    side: Side
    qty: int = Field(gt=0)
    entry_price: float | None = None

    def to_domain(self) -> EquityLeg:
        return EquityLeg(self.side, self.qty, self.entry_price)


class CashLegIn(BaseModel):
    kind: Literal["cash"] = "cash"
    amount: float = Field(gt=0)

    def to_domain(self) -> CashLeg:
        return CashLeg(self.amount)


LegIn = Annotated[OptionLegIn | EquityLegIn | CashLegIn, Field(discriminator="kind")]


class StrategyConfigIn(BaseModel):
    underlying: str = Field(min_length=1)
    legs: list[LegIn] = Field(min_length=1)

    def to_domain(self) -> StrategyConfig:
        return StrategyConfig(self.underlying, [leg.to_domain() for leg in self.legs])


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    market: str = "US"
    config: StrategyConfigIn


class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: StrategyConfigIn | None = None


class TransitionIn(BaseModel):
    target_state: str


class AnalyzeIn(BaseModel):
    config: StrategyConfigIn
    target_date: str | None = None
    live: bool = False
