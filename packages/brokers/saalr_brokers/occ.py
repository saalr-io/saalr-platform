from __future__ import annotations

from datetime import date
from decimal import Decimal


def occ_symbol(root: str, expiry: date, option_type: str, strike: float | Decimal) -> str:
    """OCC option symbol: ROOT + YYMMDD + C/P + strike*1000 zero-padded to 8 digits."""
    cp = "C" if option_type.upper() in ("CALL", "CE") else "P"
    strike_milli = int((Decimal(str(strike)) * 1000).to_integral_value())  # Decimal-native: no float drift
    return f"{root.upper()}{expiry:%y%m%d}{cp}{strike_milli:08d}"
