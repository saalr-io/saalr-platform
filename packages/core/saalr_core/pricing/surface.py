from __future__ import annotations

from datetime import date

from .types import ContractGreeks, OptionKind


def build_surface(contracts: list[ContractGreeks], as_of: date) -> list[dict]:
    """Fold contracts into the LLD §5.2 expiries[] -> strikes[] shape, using OUR iv."""
    by_expiry: dict[str, dict[float, dict]] = {}
    for c in contracts:
        strikes = by_expiry.setdefault(c.expiry, {})
        cell = strikes.setdefault(c.strike, {"strike": c.strike, "iv_call": None, "iv_put": None})
        if c.kind is OptionKind.CALL:
            cell["iv_call"] = c.ours.iv
        else:
            cell["iv_put"] = c.ours.iv

    out = []
    for expiry in sorted(by_expiry):
        dte = (date.fromisoformat(expiry) - as_of).days
        strikes = [by_expiry[expiry][k] for k in sorted(by_expiry[expiry])]
        out.append({"expiry": expiry, "days_to_expiry": dte, "strikes": strikes})
    return out
