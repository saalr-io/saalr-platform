from __future__ import annotations

from typing import Protocol

from . import greeks as _g
from . import iv as _iv
from .types import Greeks, OptionParams


class PricingModel(Protocol):
    name: str

    def price(self, p: OptionParams) -> float: ...
    def greeks(self, p: OptionParams) -> Greeks: ...
    def implied_vol(self, market_price: float, p: OptionParams) -> float | None: ...


class BSMModel:
    name = "bsm"

    def price(self, p: OptionParams) -> float:
        return _g.price(p)

    def greeks(self, p: OptionParams) -> Greeks:
        return _g.greeks(p)

    def implied_vol(self, market_price: float, p: OptionParams) -> float | None:
        return _iv.implied_vol(market_price, p)
