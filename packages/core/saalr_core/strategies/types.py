from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


@dataclass(frozen=True)
class OptionLeg:
    option_type: OptionType
    side: Side
    strike: float
    expiry: str  # YYYY-MM-DD
    qty: int
    entry_price: float | None = None
    kind: str = "option"


@dataclass(frozen=True)
class EquityLeg:
    side: Side
    qty: int  # shares
    entry_price: float | None = None
    kind: str = "equity"


@dataclass(frozen=True)
class CashLeg:
    amount: float  # collateral
    kind: str = "cash"


Leg = OptionLeg | EquityLeg | CashLeg
OPTION_MULTIPLIER = 100


@dataclass(frozen=True)
class StrategyConfig:
    underlying: str
    legs: list = field(default_factory=list)  # list[Leg]
