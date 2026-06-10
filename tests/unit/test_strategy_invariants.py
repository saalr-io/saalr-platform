"""
Saalr strategy-discovery invariant harness.

Wire-up: implement `DiscoveryAdapter` against your actual module, point
`make_adapter()` at it, and the suite runs. Until then, tests skip cleanly so
this file can sit in CI from day one and "go green" as the module lands.

Each test names the invariant IDs it enforces (see references/INVARIANTS.md).
Dependencies: pytest, hypothesis, numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

# ----------------------------------------------------------------------------
# Adapter protocol — the ONLY thing you need to implement.
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Leg:
    kind: str          # "C" or "P"
    strike: float
    expiry_days: float
    qty: int           # signed: +long, -short  (STRUCT-0)
    entry_price: float # per share, always positive


@dataclass(frozen=True)
class Strategy:
    legs: tuple[Leg, ...]
    label: str                 # e.g. "put_credit_spread"
    defined_risk: bool


class DiscoveryAdapter(Protocol):
    def payoff_at_expiry(self, s: Strategy, terminal_price: float) -> float: ...
    def max_loss(self, s: Strategy) -> float: ...
    def max_profit(self, s: Strategy) -> float: ...
    def breakevens(self, s: Strategy) -> Sequence[float]: ...
    def pop_monte_carlo(self, s: Strategy, spot: float, vol: float,
                        rate: float, seed: int) -> float: ...
    def pop_closed_form(self, s: Strategy, spot: float, vol: float,
                        rate: float) -> float | None: ...
    def position_greeks(self, s: Strategy, spot: float, vol: float,
                        rate: float) -> dict[str, float]: ...
    def leg_greeks(self, leg: Leg, spot: float, vol: float,
                   rate: float) -> dict[str, float]: ...
    def rank(self, candidates: Sequence[Strategy],
             profile: str = "default") -> list[Strategy]: ...
    def user_facing_strings(self) -> Sequence[str]:
        """All output templates / serializer literals discovery can emit."""
        ...


def make_adapter() -> DiscoveryAdapter:
    from saalr_core.discovery.testing import HarnessAdapter
    return HarnessAdapter()


@pytest.fixture(scope="module")
def adapter() -> DiscoveryAdapter:
    return make_adapter()


# ----------------------------------------------------------------------------
# Generators
# ----------------------------------------------------------------------------

@st.composite
def put_credit_spreads(draw) -> Strategy:
    """Random valid put credit spread (STRUCT-2 vertical constraints)."""
    short_k = draw(st.floats(50, 500).map(lambda x: round(x, 0)))
    width = draw(st.sampled_from([1.0, 2.5, 5.0, 10.0]))
    long_k = short_k - width
    dte = draw(st.floats(7, 90))
    # credit must be < width (else free lunch — generated as plausible)
    credit = draw(st.floats(0.05, float(width) * 0.9))
    short_px = credit + draw(st.floats(0.01, 1.0))
    long_px = short_px - credit
    legs = (
        Leg("P", short_k, dte, -1, round(short_px, 2)),
        Leg("P", long_k, dte, +1, round(long_px, 2)),
    )
    return Strategy(legs, "put_credit_spread", defined_risk=True)


# ----------------------------------------------------------------------------
# PAYOFF
# ----------------------------------------------------------------------------

@given(s=put_credit_spreads(),
       terminal=st.floats(0.01, 1000, allow_nan=False))
@settings(max_examples=200, deadline=None)
def test_expiry_payoff_exactness(adapter, s, terminal):
    """PAYOFF-1: expiry payoff equals hand-computed piecewise-linear value."""
    expected = 0.0
    for leg in s.legs:
        intrinsic = (max(terminal - leg.strike, 0.0) if leg.kind == "C"
                     else max(leg.strike - terminal, 0.0))
        expected += leg.qty * (intrinsic - leg.entry_price)
    assert math.isclose(adapter.payoff_at_expiry(s, terminal), expected,
                        abs_tol=1e-9), (
        f"PAYOFF-1 violated for {s.label} at S_T={terminal}: "
        f"expected {expected}")


@given(s=put_credit_spreads())
@settings(max_examples=200, deadline=None)
def test_vertical_closed_forms(adapter, s):
    """PAYOFF-2 / STRUCT-3: textbook extremes for a put credit spread."""
    short = next(l for l in s.legs if l.qty < 0)
    long_ = next(l for l in s.legs if l.qty > 0)
    credit = short.entry_price - long_.entry_price
    width = short.strike - long_.strike
    assert math.isclose(adapter.max_profit(s), credit, abs_tol=1e-6)
    assert math.isclose(adapter.max_loss(s), width - credit, abs_tol=1e-6)
    (be,) = adapter.breakevens(s)
    assert math.isclose(be, short.strike - credit, abs_tol=1e-6)


# ----------------------------------------------------------------------------
# PROB
# ----------------------------------------------------------------------------

@given(s=put_credit_spreads(),
       spot_mult=st.floats(0.95, 1.15),
       vol=st.floats(0.10, 0.80))
@settings(max_examples=25, deadline=None)
def test_mc_agrees_with_closed_form(adapter, s, spot_mult, vol):
    """PROB-1: MC PoP within 3 SE of closed form (lognormal)."""
    spot = s.legs[0].strike * spot_mult
    cf = adapter.pop_closed_form(s, spot, vol, rate=0.05)
    if cf is None:
        pytest.skip("no closed form for this structure")
    n_paths = 100_000  # match production config
    mc = adapter.pop_monte_carlo(s, spot, vol, rate=0.05, seed=42)
    se = math.sqrt(max(cf * (1 - cf), 1e-12) / n_paths)
    assert abs(mc - cf) <= 3 * se + 1e-4, (
        f"PROB-1: mc={mc:.4f} cf={cf:.4f} (3se={3*se:.4f}) "
        f"for {s.label} spot={spot:.2f} vol={vol:.2f}")


def test_pop_seed_invariance(adapter):
    """PROB-2: PoP spread across seeds < 1pp at production path count."""
    s = Strategy(
        (Leg("P", 100, 30, -1, 2.00), Leg("P", 95, 30, +1, 0.80)),
        "put_credit_spread", True)
    pops = [adapter.pop_monte_carlo(s, spot=105, vol=0.3, rate=0.05, seed=k)
            for k in range(5)]
    assert max(pops) - min(pops) < 0.01, f"PROB-2: spread {pops}"


def test_pop_monotonic_in_short_strike(adapter):
    """PROB-3: further-OTM short vertical => higher PoP."""
    pops = []
    for short_k in (100, 97, 94, 91):
        s = Strategy(
            (Leg("P", short_k, 30, -1, 1.50),
             Leg("P", short_k - 5, 30, +1, 0.60)),
            "put_credit_spread", True)
        pops.append(adapter.pop_monte_carlo(s, spot=105, vol=0.3,
                                            rate=0.05, seed=7))
    assert all(b >= a - 0.005 for a, b in zip(pops, pops[1:])), (
        f"PROB-3 violated: {pops}")


# ----------------------------------------------------------------------------
# GREEK
# ----------------------------------------------------------------------------

@given(s=put_credit_spreads(), vol=st.floats(0.1, 0.6))
@settings(max_examples=50, deadline=None)
def test_greek_additivity(adapter, s, vol):
    """GREEK-1: position greeks are the signed sum of leg greeks."""
    spot = s.legs[0].strike * 1.02
    pos = adapter.position_greeks(s, spot, vol, rate=0.05)
    for g in ("delta", "gamma", "vega", "theta"):
        leg_sum = sum(l.qty * adapter.leg_greeks(l, spot, vol, 0.05)[g]
                      for l in s.legs)
        assert math.isclose(pos[g], leg_sum, rel_tol=1e-8, abs_tol=1e-10), (
            f"GREEK-1: {g} pos={pos[g]} sum={leg_sum}")


# ----------------------------------------------------------------------------
# RANK
# ----------------------------------------------------------------------------

def _dominated_pair() -> tuple[Strategy, Strategy]:
    """A strictly dominates B: same structure, A collects more credit."""
    a = Strategy((Leg("P", 100, 30, -1, 2.20), Leg("P", 95, 30, +1, 0.80)),
                 "put_credit_spread", True)
    b = Strategy((Leg("P", 100, 30, -1, 1.90), Leg("P", 95, 30, +1, 0.80)),
                 "put_credit_spread", True)
    return a, b


def test_dominance(adapter):
    """RANK-1: dominated strategy never outranks the dominator."""
    a, b = _dominated_pair()
    ranked = adapter.rank([b, a])
    assert ranked.index(a) < ranked.index(b), "RANK-1 violated"


def test_free_lunch_quarantined(adapter):
    """RANK-2: net-credit, no-loss 'arbitrage' must not appear in results."""
    fl = Strategy(  # credit 5.10 on a 5-wide spread: bad quote, not alpha
        (Leg("P", 100, 30, -1, 5.50), Leg("P", 95, 30, +1, 0.40)),
        "put_credit_spread", True)
    a, _ = _dominated_pair()
    ranked = adapter.rank([fl, a])
    assert fl not in ranked, "RANK-2: data-error arbitrage surfaced to user"


def test_rank_determinism(adapter):
    """RANK-4: identical inputs => identical ordering."""
    a, b = _dominated_pair()
    assert adapter.rank([a, b]) == adapter.rank([a, b])


# ----------------------------------------------------------------------------
# COMPLY
# ----------------------------------------------------------------------------

FORBIDDEN = ("we recommend", "you should", "best trade", "buy now",
             "sell now", "act now", "guaranteed", "can't lose")

def test_no_advice_language(adapter):
    """COMPLY-1: discovery output templates contain no advice phrasing."""
    bad = [t for t in adapter.user_facing_strings()
           if any(p in t.lower() for p in FORBIDDEN)]
    assert not bad, f"COMPLY-1 violated in templates: {bad}"
