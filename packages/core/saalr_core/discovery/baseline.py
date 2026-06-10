from __future__ import annotations

from collections.abc import Callable

from saalr_core.strategies.types import OptionLeg, OptionType, Side

from .generate import atm_strike
from .types import CleanChain


def naive_atm_short_put(
    chain: CleanChain, expiry: str, dte: int, rate: float, mc_pop: Callable[..., dict], seed: int,
) -> dict:
    """DATA-4: the honest benchmark every discovery result is reported against —
    a single systematic ATM short put on the same snapshot."""
    strikes = chain.strikes_for_expiry(expiry)
    k = atm_strike(strikes, chain.spot)
    c = chain.contract(expiry, k, OptionType.PUT)
    leg = OptionLeg(OptionType.PUT, Side.SELL, k, expiry, 1, entry_price=(c.mid if c else 0.0))
    t_years = max(dte, 0) / 365.0
    mc = mc_pop([leg], chain.spot, t_years, (c.iv if c and c.iv else 0.3), rate, chain.div_yield, seed)
    return {"naive": "atm_short_put", "strike": k, "expiry": expiry,
            "pop": mc["pop"], "ev": mc["ev"]}
