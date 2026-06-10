"""Wires saalr_core.discovery + saalr_ml to the installed DiscoveryAdapter protocol
(tests/unit/test_strategy_invariants.py). The harness Leg/Strategy are per-share with
signed qty; we adapt to saalr_core types, whose payoff/greeks math is per-contract (x100),
and divide back to per-share so the harness's hand-computed expectations hold.

HarnessAdapter holds NO dependency on the `tests.*` tree. `harness_strategy_from_case`
builds a duck-typed, harness-shaped Strategy (attributes: legs[].kind/strike/expiry_days/
qty/entry_price, label, defined_risk) from a golden fixture case, so the golden test can
import it from here without making saalr_core depend on the test package.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from saalr_core.pricing.greeks import greeks as bsm_greeks
from saalr_core.pricing.types import OptionKind, OptionParams
from saalr_core.strategies import aggregate, payoff, pop
from saalr_core.strategies.types import (
    OPTION_MULTIPLIER,
    OptionLeg,
    OptionType,
    Side,
)
from saalr_ml.montecarlo import monte_carlo_pop

_MC_PATHS = 100_000  # matches the harness PROB-1/PROB-2 production path count
_EPOCH = date(2026, 1, 1)


# --- harness-shaped value objects (duck-typed; no tests.* import) ------------

@dataclass(frozen=True)
class _Leg:
    kind: str          # "C" or "P"
    strike: float
    expiry_days: float
    qty: int           # signed: +long, -short
    entry_price: float


@dataclass(frozen=True)
class _Strategy:
    legs: tuple
    label: str
    defined_risk: bool


def harness_strategy_from_case(case: dict):
    """Build a harness-style Strategy from a golden fixture case (for the golden test)."""
    legs = tuple(
        _Leg(
            kind=leg["kind"],
            strike=leg["strike"],
            expiry_days=leg["expiry_days"],
            qty=leg["qty"],
            entry_price=leg["entry_price"],
        )
        for leg in case["legs"]
    )
    return _Strategy(legs=legs, label=case["label"], defined_risk=True)


# --- harness leg -> saalr_core leg -------------------------------------------

def _expiry(days: float) -> str:
    return (_EPOCH + timedelta(days=int(days))).isoformat()


def _to_leg(hleg) -> OptionLeg:
    ot = OptionType.CALL if hleg.kind == "C" else OptionType.PUT
    side = Side.BUY if hleg.qty > 0 else Side.SELL
    return OptionLeg(
        ot, side, hleg.strike, _expiry(hleg.expiry_days),
        abs(hleg.qty), entry_price=hleg.entry_price,
    )


def _legs(s) -> list[OptionLeg]:
    return [_to_leg(leg) for leg in s.legs]


def _t_years(s) -> float:
    return max(min(leg.expiry_days for leg in s.legs), 1) / 365.0


def _option_kind(leg: OptionLeg) -> OptionKind:
    return OptionKind.CALL if leg.option_type is OptionType.CALL else OptionKind.PUT


class HarnessAdapter:
    """Per-share view over the per-contract saalr_core engine."""

    def payoff_at_expiry(self, s, terminal_price: float) -> float:
        legs = _legs(s)
        return payoff.expiration_curve(legs, [terminal_price])[0][1] / OPTION_MULTIPLIER

    def _curve(self, s):
        legs = _legs(s)
        return payoff.expiration_curve(legs, payoff.spot_grid(legs, max(leg.strike for leg in legs)))

    def max_loss(self, s) -> float:
        ext = payoff.max_pl(self._curve(s))
        if ext["max_loss"] is None:
            return float("inf")
        return abs(ext["max_loss"]) / OPTION_MULTIPLIER

    def max_profit(self, s) -> float:
        ext = payoff.max_pl(self._curve(s))
        if ext["max_profit"] is None:
            return float("inf")
        return ext["max_profit"] / OPTION_MULTIPLIER

    def breakevens(self, s) -> Sequence[float]:
        return payoff.breakevens(self._curve(s))

    def pop_monte_carlo(self, s, spot, vol, rate, seed) -> float:
        legs = _legs(s)
        return monte_carlo_pop(
            legs, spot, _t_years(s), vol, rate, seed=seed, paths=_MC_PATHS,
        )["pop"]

    def pop_closed_form(self, s, spot, vol, rate):
        legs = _legs(s)
        curve = payoff.expiration_curve(legs, payoff.spot_grid(legs, spot))
        return pop.probability_of_profit(
            spot, vol, _t_years(s), rate, 0.0, payoff.profit_intervals(curve),
        )["pop"]

    def position_greeks(self, s, spot, vol, rate) -> dict:
        legs = _legs(s)
        t = _t_years(s)
        priced = [
            (
                leg,
                bsm_greeks(
                    OptionParams(
                        spot=spot, strike=leg.strike, t_years=t, rate=rate,
                        sigma=vol, div_yield=0.0, kind=_option_kind(leg),
                    )
                ),
            )
            for leg in legs
        ]
        g = aggregate.net_greeks(priced)
        return {k: v / OPTION_MULTIPLIER for k, v in g.items()}

    def leg_greeks(self, leg, spot, vol, rate) -> dict:
        ot = OptionKind.CALL if leg.kind == "C" else OptionKind.PUT
        t = max(leg.expiry_days, 1) / 365.0
        g = bsm_greeks(
            OptionParams(
                spot=spot, strike=leg.strike, t_years=t, rate=rate,
                sigma=vol, div_yield=0.0, kind=ot,
            )
        )
        return {"delta": g.delta, "gamma": g.gamma, "theta": g.theta, "vega": g.vega, "rho": g.rho}

    def rank(self, candidates, profile: str = "default") -> list:
        from .gates import is_free_lunch
        from .score import score_for

        prof = "ev_to_risk" if profile == "default" else profile

        def _metrics(s) -> dict:
            legs = _legs(s)
            curve = payoff.expiration_curve(
                legs, payoff.spot_grid(legs, max(leg.strike for leg in legs))
            )
            ext = payoff.max_pl(curve)
            credit = -payoff.net_premium(legs)
            max_loss = abs(ext["max_loss"]) if ext["max_loss"] is not None else None
            return {
                "ev": credit,
                "max_loss": max_loss,
                "ev_to_risk": (credit / max_loss if max_loss else None),
                "pop": 0.5,
            }

        ranked = []
        for c in candidates:
            legs = _legs(c)
            curve = payoff.expiration_curve(
                legs, payoff.spot_grid(legs, max(leg.strike for leg in legs))
            )
            if is_free_lunch(payoff.net_premium(legs), curve):
                continue
            ranked.append(c)
        return sorted(ranked, key=lambda c: -score_for(prof, _metrics(c)))

    def user_facing_strings(self) -> Sequence[str]:
        from .serialize import _PROFILE_PHRASE
        return [f"Ranked #1 by {p} under your filters." for p in _PROFILE_PHRASE.values()]
