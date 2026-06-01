from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal

from .types import BrokerFill, BrokerOrder, BrokerOrderResult, BrokerPosition


class BrokerAdapter(ABC):
    """The contract every broker adapter implements (LLD §6). Paper and live alike."""

    @abstractmethod
    async def submit_order(self, order: BrokerOrder, idempotency_key: str) -> BrokerOrderResult: ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool: ...

    @abstractmethod
    async def get_orders(self, since: datetime | None = None) -> list[dict]: ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    async def get_account_balance(self) -> Decimal: ...

    @abstractmethod
    def stream_executions(self) -> AsyncIterator[BrokerFill]: ...
