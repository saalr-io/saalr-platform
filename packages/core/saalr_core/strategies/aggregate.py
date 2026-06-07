from __future__ import annotations

from saalr_core.pricing.types import Greeks

from .types import OPTION_MULTIPLIER, EquityLeg, OptionLeg


def net_greeks(priced_legs: list[tuple[object, Greeks | None]]) -> dict:
    """Sum position Greeks. priced_legs: (leg, computed Greeks or None) pairs."""
    total = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    for leg, g in priced_legs:
        if isinstance(leg, OptionLeg) and g is not None:
            f = OPTION_MULTIPLIER * leg.qty * leg.side.sign
            total["delta"] += g.delta * f
            total["gamma"] += g.gamma * f
            total["theta"] += g.theta * f
            total["vega"] += g.vega * f
            total["rho"] += g.rho * f
        elif isinstance(leg, EquityLeg):
            total["delta"] += leg.qty * leg.side.sign
    return total
