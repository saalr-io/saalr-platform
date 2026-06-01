from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from saalr_core.oms.positions import net_position

from .base import BrokerAdapter
from .types import BrokerFill, BrokerOrder, BrokerOrderResult, BrokerPosition

_OPTION_MULT = 100


@dataclass
class _BookOrder:
    broker_order_id: str
    order: BrokerOrder
    status: str  # "open" | "filled" | "cancelled"
    fill_price: Decimal | None = None


class PaperBrokerAdapter(BrokerAdapter):
    """Deterministic mark-price paper fills. Synchronous; no RNG, no wall-clock in fills."""

    def __init__(self, starting_cash: Decimal, mark_provider: Callable[[BrokerOrder], Decimal]) -> None:
        self._cash = Decimal(starting_cash)
        self._mark = mark_provider
        self._orders: dict[str, _BookOrder] = {}
        self._idem: dict[str, BrokerOrderResult] = {}
        self._positions: dict[tuple, dict] = {}
        self._fills: list[BrokerFill] = []
        self._seq = 0

    def _next(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq}"

    @staticmethod
    def _mult(order: BrokerOrder) -> int:
        return _OPTION_MULT if order.option_type else 1

    @staticmethod
    def _key(order: BrokerOrder) -> tuple:
        return (order.symbol, order.option_type, str(order.strike), str(order.expiry))

    def _marketable(self, order: BrokerOrder, mark: Decimal) -> tuple[bool, Decimal | None]:
        t = order.order_type
        if t == "market":
            return True, mark
        if t == "limit":
            if order.side == "buy" and mark <= order.limit_price:
                return True, order.limit_price
            if order.side == "sell" and mark >= order.limit_price:
                return True, order.limit_price
            return False, None
        if t in ("stop", "stop_limit"):
            triggered = (order.side == "buy" and mark >= order.stop_price) or (
                order.side == "sell" and mark <= order.stop_price
            )
            if not triggered:
                return False, None
            if t == "stop":
                return True, mark
            # stop_limit: now behave as a limit
            if order.side == "buy" and mark <= order.limit_price:
                return True, order.limit_price
            if order.side == "sell" and mark >= order.limit_price:
                return True, order.limit_price
            return False, None
        return False, None

    def _apply_fill(self, boid: str, order: BrokerOrder, price: Decimal) -> None:
        notional = price * order.qty * self._mult(order)
        self._cash += -notional if order.side == "buy" else notional
        self._add_position(order, order.qty if order.side == "buy" else -order.qty, price)
        self._fills.append(
            BrokerFill(broker_order_id=boid, broker_execution_id=self._next("pe"),
                       qty=order.qty, price=price, commission=Decimal(0))
        )

    def _add_position(self, order: BrokerOrder, signed_qty: int, price: Decimal) -> None:
        key = self._key(order)
        pos = self._positions.get(key, {"qty": 0, "avg_price": Decimal(0), "order": order})
        new_qty, new_avg = net_position(pos["qty"], pos["avg_price"], signed_qty, price)
        pos["qty"], pos["avg_price"] = new_qty, new_avg
        if new_qty == 0:
            self._positions.pop(key, None)
        else:
            self._positions[key] = pos

    async def submit_order(self, order: BrokerOrder, idempotency_key: str) -> BrokerOrderResult:
        if idempotency_key in self._idem:
            return self._idem[idempotency_key]
        boid = self._next("po")
        marketable, fill_price = self._marketable(order, self._mark(order))
        if marketable:
            self._apply_fill(boid, order, fill_price)
            self._orders[boid] = _BookOrder(boid, order, "filled", fill_price)
        elif order.time_in_force in ("ioc", "fok"):
            self._orders[boid] = _BookOrder(boid, order, "cancelled")
        else:
            self._orders[boid] = _BookOrder(boid, order, "open")
        result = BrokerOrderResult(broker_order_id=boid, status="submitted")
        self._idem[idempotency_key] = result
        return result

    async def cancel_order(self, broker_order_id: str) -> bool:
        bo = self._orders.get(broker_order_id)
        if bo is None or bo.status != "open":
            return False
        bo.status = "cancelled"
        return True

    async def get_orders(self, since: datetime | None = None) -> list[dict]:
        return [
            {"broker_order_id": b.broker_order_id, "status": b.status, "symbol": b.order.symbol,
             "qty": b.order.qty, "side": b.order.side, "fill_price": b.fill_price}
            for b in self._orders.values()
        ]

    async def get_positions(self) -> list[BrokerPosition]:
        out: list[BrokerPosition] = []
        for pos in self._positions.values():
            order = pos["order"]
            qty, avg, mult = pos["qty"], pos["avg_price"], self._mult(order)
            mark = self._mark(order)
            out.append(
                BrokerPosition(
                    symbol=order.symbol, qty=qty, avg_price=avg,
                    market_value=mark * qty * mult, unrealized_pnl=(mark - avg) * qty * mult,
                )
            )
        return out

    async def get_account_balance(self) -> Decimal:
        return self._cash

    async def stream_executions(self) -> AsyncIterator[BrokerFill]:
        while self._fills:
            yield self._fills.pop(0)
