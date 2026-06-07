from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal

import httpx

from .base import BrokerAdapter, BrokerError
from .occ import occ_symbol
from .types import BrokerFill, BrokerOrder, BrokerOrderResult, BrokerPosition

_SANDBOX = "https://sandbox.tradier.com/v1"
_LIVE = "https://api.tradier.com/v1"


class TradierError(BrokerError):
    """Wraps a Tradier transport/HTTP error so callers don't see raw httpx exceptions."""


_OPTION_SIDE = {"buy": "buy_to_open", "sell": "sell_to_open"}  # open-only (see spec limitations)
_DURATION = {"day": "day", "gtc": "gtc"}                       # ioc/fok -> day

_STATUS = {
    "filled": "filled",
    "partially_filled": "partial", "partial": "partial",
    "canceled": "cancelled", "cancelled": "cancelled", "expired": "cancelled",
    "rejected": "rejected", "error": "rejected",
}


def map_status(status: str) -> str:
    """Tradier order status -> our OrderStatus value. Unknown/open/ok -> 'submitted'."""
    return _STATUS.get(str(status).lower(), "submitted")


def build_order_form(order, tag: str) -> dict[str, str]:
    """Pure: BrokerOrder -> Tradier order form params (equity or single option leg)."""
    duration = _DURATION.get(order.time_in_force, "day")
    form: dict[str, str] = {
        "class": "", "symbol": order.symbol.upper(), "side": "",
        "quantity": str(order.qty), "type": order.order_type, "duration": duration,
        "tag": tag[:40],
    }
    if order.option_type:
        side = _OPTION_SIDE.get(order.side.lower())
        if side is None:
            raise TradierError(f"unsupported option side {order.side!r}")
        form["class"] = "option"
        form["option_symbol"] = occ_symbol(order.symbol, order.expiry, order.option_type, order.strike)
        form["side"] = side
    else:
        form["class"] = "equity"
        form["side"] = order.side.lower()
    if order.limit_price is not None and order.order_type in ("limit", "stop_limit"):
        form["price"] = str(order.limit_price)
    if order.stop_price is not None and order.order_type in ("stop", "stop_limit"):
        form["stop"] = str(order.stop_price)
    return form


def _as_list(node) -> list:
    """Tradier returns 'null', a single object, or a list. Normalize to a list."""
    if node in (None, "null", ""):
        return []
    return node if isinstance(node, list) else [node]


def _items(body: dict, key: str, child: str) -> list:
    """Tradier wraps collections as {key: {child: <obj|list>}} (or 'null'). Return the rows."""
    node = body.get(key)
    return _as_list(node.get(child) if isinstance(node, dict) else node)


def parse_orders(body: dict) -> list[dict]:
    orders = _items(body, "orders", "order")
    out: list[dict] = []
    for o in orders:
        fap = o.get("avg_fill_price")
        out.append({
            "broker_order_id": str(o.get("id")),
            "status": map_status(o.get("status", "")),
            "symbol": o.get("symbol"),
            "qty": int(o.get("quantity") or 0),
            "side": o.get("side"),
            "filled_qty": int(o.get("exec_quantity") or 0),
            "filled_avg_price": Decimal(str(fap)) if fap else None,
            "client_order_id": o.get("tag"),
        })
    return out


def parse_positions(body: dict) -> list[BrokerPosition]:
    positions = _items(body, "positions", "position")
    out: list[BrokerPosition] = []
    for p in positions:
        qty = int(p.get("quantity") or 0)
        cost = Decimal(str(p.get("cost_basis") or 0))
        avg = (cost / qty) if qty else Decimal(0)
        out.append(BrokerPosition(symbol=p.get("symbol"), qty=qty, avg_price=avg,
                                  market_value=cost, unrealized_pnl=Decimal(0)))
    return out


def parse_balance(body: dict) -> Decimal:
    b = body.get("balances") or {}
    for k in ("option_buying_power", "stock_buying_power", "total_cash", "total_equity"):
        if b.get(k) is not None:
            return Decimal(str(b[k]))
    return Decimal(0)


class TradierAdapter(BrokerAdapter):
    """BrokerAdapter over the Tradier REST API (sandbox when is_paper)."""

    def __init__(self, access_token: str, account_id: str, is_paper: bool = True, *, client=None) -> None:
        self._token = access_token
        self._account_id = account_id
        self._base = _SANDBOX if is_paper else _LIVE
        self._client = client

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base, timeout=20.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    async def _request(self, method: str, path: str, *, data=None, params=None) -> dict:
        try:
            r = await self._http().request(method, path, headers=self._headers(),
                                           data=data, params=params)
            if r.status_code >= 400:
                # Tradier error payloads carry {"errors": {"error": [...]}}; surface the text.
                try:
                    errs = r.json().get("errors", {}).get("error")
                except Exception:
                    errs = None
                raise TradierError(
                    "; ".join(errs) if isinstance(errs, list) else (str(errs) or f"http {r.status_code}"))
            return r.json()
        except TradierError:
            raise
        except httpx.HTTPError as exc:
            raise TradierError(str(exc)) from exc

    async def submit_order(self, order: BrokerOrder, idempotency_key: str) -> BrokerOrderResult:
        try:
            body = await self._request(
                "POST", f"/accounts/{self._account_id}/orders",
                data=build_order_form(order, idempotency_key))
        except TradierError as exc:
            return BrokerOrderResult("", "rejected", str(exc))
        o = body.get("order", {})
        if map_status(o.get("status", "")) == "rejected":
            return BrokerOrderResult(str(o.get("id", "")), "rejected", str(o.get("status")))
        return BrokerOrderResult(str(o.get("id", "")), "submitted")

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await self._request("DELETE", f"/accounts/{self._account_id}/orders/{broker_order_id}")
            return True
        except TradierError:
            return False

    async def get_orders(self, since: datetime | None = None) -> list[dict]:
        body = await self._request("GET", f"/accounts/{self._account_id}/orders")
        return parse_orders(body)  # since-filtering is best-effort; Tradier lacks a clean 'after' param

    async def get_positions(self) -> list[BrokerPosition]:
        body = await self._request("GET", f"/accounts/{self._account_id}/positions")
        return parse_positions(body)

    async def get_account_balance(self) -> Decimal:
        body = await self._request("GET", f"/accounts/{self._account_id}/balances")
        return parse_balance(body)

    async def stream_executions(self) -> AsyncIterator[BrokerFill]:
        raise NotImplementedError("reconcile via get_orders polling")
        yield  # unreachable; makes this an async generator so it satisfies the ABC contract
