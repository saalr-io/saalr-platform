from __future__ import annotations

from datetime import date
from decimal import Decimal


class BrokerError(Exception):
    """Wraps an alpaca SDK/transport error so callers don't see raw alpaca exceptions."""


def occ_symbol(root: str, expiry: date, option_type: str, strike: float | Decimal) -> str:
    """OCC option symbol: ROOT + YYMMDD + C/P + strike*1000 zero-padded to 8 digits."""
    cp = "C" if option_type.upper() in ("CALL", "CE") else "P"
    strike_milli = int(round(float(strike) * 1000))
    return f"{root.upper()}{expiry:%y%m%d}{cp}{strike_milli:08d}"


_ALPACA_STATUS: dict[str, str] = {
    "new": "submitted", "accepted": "submitted", "pending_new": "submitted",
    "accepted_for_bidding": "submitted",
    "partially_filled": "partial",
    "filled": "filled",
    "canceled": "cancelled", "expired": "cancelled", "done_for_day": "cancelled",
    "pending_cancel": "cancelled",
    "rejected": "rejected", "suspended": "rejected", "stopped": "rejected",
}


def map_status(status) -> str:
    """Alpaca order status (str or enum) -> our OrderStatus value. Unknown -> 'submitted'."""
    s = str(getattr(status, "value", status)).lower()
    return _ALPACA_STATUS.get(s, "submitted")
