from __future__ import annotations

from datetime import date

from saalr_core.strategies import templates
from saalr_core.strategies.types import CashLeg, EquityLeg, OptionLeg, StrategyConfig

from .types import Candidate, CleanChain


# Option-only templates (skip equity/cash-leg structures this slice). Derived once from the
# registry by building each at a probe strike and checking leg types.
def _is_option_only(key: str) -> bool:
    cfg = templates.build(key, "PROBE", "2026-01-01", 100.0, 5.0)
    return all(isinstance(leg, OptionLeg) for leg in cfg.legs)


OPTION_ONLY_TEMPLATES = tuple(t["key"] for t in templates.list_templates() if _is_option_only(t["key"]))


def atm_strike(strikes: list[float], spot: float) -> float:
    """Nearest listed strike to spot (ties resolve to the higher strike)."""
    return min(strikes, key=lambda k: (abs(k - spot), -k))


def _window(strikes: list[float], spot: float, n: int) -> list[float]:
    """The ATM strike plus n listed strikes above and n below (<= 2n+1 strikes)."""
    srt = sorted(strikes)
    atm = atm_strike(srt, spot)
    i = srt.index(atm)
    return srt[max(0, i - n): i + n + 1]


def enumerate_candidates(
    chain: CleanChain,
    families: list[str],
    dte_min: int,
    dte_max: int,
    strike_window: int,
    as_of_date: date,
) -> list[Candidate]:
    """Generate concrete, priced candidates for the given families.

    STRUCT-1: every leg strike must be listed in the chain. STRUCT-2: template
    constraints come from templates.build. STRUCT-4: zero-width / non-distinct-strike
    structures are rejected. Equity/cash-leg templates are skipped this slice.
    """
    keys = [k for k in families if k in OPTION_ONLY_TEMPLATES]
    out: list[Candidate] = []
    for expiry in chain.expiries():
        dte = (date.fromisoformat(expiry) - as_of_date).days
        if dte < dte_min or dte > dte_max or dte <= 0:
            continue
        strikes = chain.strikes_for_expiry(expiry)
        if len(strikes) < 2:
            continue
        window = _window(strikes, chain.spot, strike_window)
        for key in keys:
            for center in window:
                for width in _widths(window, center):
                    cand = _build_priced(chain, key, expiry, center, width, dte)
                    if cand is not None:
                        out.append(cand)
    return out


def _widths(window: list[float], center: float) -> list[float]:
    """Positive listed gaps above the center strike — candidate spread widths."""
    return sorted({round(k - center, 4) for k in window if k - center > 0})


def _build_priced(chain: CleanChain, key: str, expiry: str, center: float, width: float, dte: int) -> Candidate | None:
    cfg = templates.build(key, chain.underlying, expiry, center, width)
    legs = cfg.legs
    if any(isinstance(leg, (EquityLeg, CashLeg)) for leg in legs):
        return None
    strikes = {leg.strike for leg in legs if isinstance(leg, OptionLeg)}
    if len(strikes) < 2:  # STRUCT-4: zero-width / degenerate
        return None
    priced: list[OptionLeg] = []
    for leg in legs:
        c = chain.contract(expiry, leg.strike, leg.option_type)
        if c is None:  # STRUCT-1: leg strike not listed -> reject whole candidate
            return None
        priced.append(
            OptionLeg(leg.option_type, leg.side, leg.strike, leg.expiry, leg.qty, entry_price=c.mid)
        )
    return Candidate(key, StrategyConfig(chain.underlying, priced), expiry, dte)
