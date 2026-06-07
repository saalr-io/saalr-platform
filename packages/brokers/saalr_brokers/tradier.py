from __future__ import annotations

from decimal import Decimal

from .base import BrokerError
from .occ import occ_symbol
from .types import BrokerPosition


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
        form["class"] = "option"
        form["option_symbol"] = occ_symbol(order.symbol, order.expiry, order.option_type, order.strike)
        form["side"] = _OPTION_SIDE[order.side]
    else:
        form["class"] = "equity"
        form["side"] = order.side
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


def parse_orders(body: dict) -> list[dict]:
    node = body.get("orders")
    orders = _as_list(node.get("order") if isinstance(node, dict) else node)
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
    node = body.get("positions")
    positions = _as_list(node.get("position") if isinstance(node, dict) else node)
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
