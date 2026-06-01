from __future__ import annotations

from decimal import Decimal


def net_position(
    old_qty: int, old_avg: Decimal, signed_qty: int, price: Decimal
) -> tuple[int, Decimal]:
    """Apply a signed fill (qty>0 buy, qty<0 sell) to a position. Returns (new_qty, new_avg).
    Weighted-average on opening/adding the same direction; average unchanged on a partial close;
    basis reset to the fill price when the position crosses through zero; (0, 0) when flat."""
    new = old_qty + signed_qty
    if new == 0:
        return 0, Decimal(0)
    if old_qty == 0 or (old_qty > 0) == (signed_qty > 0):
        total = old_avg * abs(old_qty) + price * abs(signed_qty)
        return new, total / abs(new)
    if (old_qty > 0) != (new > 0):  # crossed through zero
        return new, price
    return new, old_avg  # partial close, same direction
