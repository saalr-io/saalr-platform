from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal

from .base import BrokerAdapter, BrokerError
from .occ import occ_symbol
from .types import BrokerFill, BrokerOrder, BrokerOrderResult, BrokerPosition

__all__ = ["AlpacaAdapter", "BrokerError", "map_status", "occ_symbol"]


_ALPACA_STATUS: dict[str, str] = {
    "new": "submitted", "accepted": "submitted", "pending_new": "submitted",
    "accepted_for_bidding": "submitted", "held": "submitted", "calculated": "submitted",
    "partially_filled": "partial",
    "filled": "filled",
    "canceled": "cancelled", "expired": "cancelled", "done_for_day": "cancelled",
    "pending_cancel": "cancelled",
    # 'replaced' is terminal (superseded by a new order) -> must NOT default to 'submitted'
    "replaced": "cancelled", "pending_replace": "cancelled",
    "rejected": "rejected", "suspended": "rejected", "stopped": "rejected",
}


def map_status(status) -> str:
    """Alpaca order status (str or enum) -> our OrderStatus value. Unknown -> 'submitted'."""
    s = str(getattr(status, "value", status)).lower()
    return _ALPACA_STATUS.get(s, "submitted")


class AlpacaAdapter(BrokerAdapter):
    """BrokerAdapter backed by alpaca-py. alpaca is imported lazily (so importing this module
    needs no SDK); the synchronous TradingClient is called via asyncio.to_thread."""

    def __init__(self, api_key: str, api_secret: str, is_paper: bool = True, *, client=None) -> None:
        self._key = api_key
        self._secret = api_secret
        self._is_paper = is_paper
        self._client = client

    def _trading(self):
        if self._client is None:
            try:
                from alpaca.trading.client import TradingClient
            except ImportError as exc:  # pragma: no cover - exercised only without the extra
                raise BrokerError("alpaca-py not installed (pip install alpaca-py)") from exc
            self._client = TradingClient(self._key, self._secret, paper=self._is_paper)
        return self._client

    def _build_request(self, order: BrokerOrder, idempotency_key: str):
        try:
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import (
                LimitOrderRequest,
                MarketOrderRequest,
                StopLimitOrderRequest,
                StopOrderRequest,
            )
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise BrokerError("alpaca-py not installed (pip install alpaca-py)") from exc

        symbol = (
            occ_symbol(order.symbol, order.expiry, order.option_type, order.strike)
            if order.option_type
            else order.symbol
        )
        kw = dict(
            symbol=symbol, qty=order.qty, side=OrderSide(order.side),
            time_in_force=TimeInForce(order.time_in_force), client_order_id=idempotency_key,
        )
        t = order.order_type
        if t == "market":
            return MarketOrderRequest(**kw)
        if t == "limit":
            return LimitOrderRequest(limit_price=float(order.limit_price), **kw)
        if t == "stop":
            return StopOrderRequest(stop_price=float(order.stop_price), **kw)
        if t == "stop_limit":
            return StopLimitOrderRequest(
                limit_price=float(order.limit_price), stop_price=float(order.stop_price), **kw
            )
        raise BrokerError(f"unsupported order_type {t!r}")

    async def submit_order(self, order: BrokerOrder, idempotency_key: str) -> BrokerOrderResult:
        def _work():  # build the request + submit off the event loop (Pydantic + network)
            return self._trading().submit_order(self._build_request(order, idempotency_key))

        try:
            o = await asyncio.to_thread(_work)
        except BrokerError:
            raise
        except Exception as exc:
            raise BrokerError(str(exc)) from exc
        if map_status(o.status) == "rejected":
            return BrokerOrderResult(str(o.id), "rejected",
                                     getattr(o, "rejected_reason", None) or str(o.status))
        return BrokerOrderResult(str(o.id), "submitted")

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await asyncio.to_thread(self._trading().cancel_order_by_id, broker_order_id)
            return True
        except Exception:
            return False

    async def get_orders(self, since: datetime | None = None) -> list[dict]:
        def _work():
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest

            # status=ALL so reconciliation sees closed/filled orders, not just open ones;
            # after=since lets the OMS-3b reconciliation poll incrementally.
            req = GetOrdersRequest(status=QueryOrderStatus.ALL, after=since)
            return self._trading().get_orders(req)

        try:
            orders = await asyncio.to_thread(_work)
        except Exception as exc:
            raise BrokerError(str(exc)) from exc
        out: list[dict] = []
        for o in orders:
            fap = getattr(o, "filled_avg_price", None)
            out.append({
                "broker_order_id": str(o.id),
                "status": map_status(o.status),
                "symbol": o.symbol,
                "qty": int(o.qty),
                "side": str(getattr(o.side, "value", o.side)),
                "filled_qty": int(o.filled_qty or 0),
                "filled_avg_price": Decimal(str(fap)) if fap else None,
                "client_order_id": getattr(o, "client_order_id", None),
            })
        return out

    async def get_positions(self) -> list[BrokerPosition]:
        try:
            ps = await asyncio.to_thread(self._trading().get_all_positions)
        except Exception as exc:
            raise BrokerError(str(exc)) from exc
        return [
            BrokerPosition(
                symbol=p.symbol, qty=int(p.qty), avg_price=Decimal(str(p.avg_entry_price)),
                market_value=Decimal(str(p.market_value)), unrealized_pnl=Decimal(str(p.unrealized_pl)),
            )
            for p in ps
        ]

    async def get_account_balance(self) -> Decimal:
        try:
            acct = await asyncio.to_thread(self._trading().get_account)
        except Exception as exc:
            raise BrokerError(str(exc)) from exc
        return Decimal(str(acct.buying_power))

    async def stream_executions(self) -> AsyncIterator[BrokerFill]:
        raise NotImplementedError("reconcile via get_orders polling (OMS-3b)")
        yield  # unreachable; makes this an async generator so it satisfies the ABC contract
