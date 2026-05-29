from __future__ import annotations

from typing import Protocol

from .types import RawChain, YieldCurve


class MarketDataProvider(Protocol):
    async def get_option_chain(self, ticker: str, market: str) -> RawChain: ...


class RiskFreeRateProvider(Protocol):
    async def get_curve(self) -> YieldCurve: ...


class ProviderError(Exception):
    """Raised when an upstream market-data provider is unreachable or returns an error."""
