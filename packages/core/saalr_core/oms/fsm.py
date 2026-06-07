from __future__ import annotations

from .types import OrderStatus

VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.SUBMITTED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.SUBMITTED: {OrderStatus.PARTIAL, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED},
    OrderStatus.PARTIAL: {OrderStatus.FILLED, OrderStatus.CANCELLED},
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
}


class IllegalOrderTransition(Exception):
    """Raised when an order status transition is not permitted by the FSM."""


def transition(current: OrderStatus, target: OrderStatus) -> OrderStatus:
    if target not in VALID_TRANSITIONS[current]:
        raise IllegalOrderTransition(f"{current.value} -> {target.value} is not allowed")
    return target
