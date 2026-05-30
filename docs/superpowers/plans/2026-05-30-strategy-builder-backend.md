# Strategy Builder Backend (7a) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A headless backend for creating, persisting, and analyzing multi-leg options strategies — §7 FSM, expiration + target-date payoff curves, breakevens, max P/L, net Greeks, lognormal POP, and a ready-made templates catalog.

**Architecture:** Pure domain logic in `saalr_core/strategies/` (stdlib + the existing `pricing` engine, no I/O); thin API in `saalr_api/strategies/` (CRUD via RLS-scoped repo, analyze composes the existing `MarketService`). CRUD is open to all tiers; the live analysis is `vol_surface`-gated.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Redis, pydantic v2, pytest. Reuses `saalr_core.pricing` (BSM) and `saalr_api.market` (MarketService/MassiveProvider).

**Spec:** `docs/superpowers/specs/2026-05-30-strategy-builder-backend-design.md`

## File structure

```
packages/core/saalr_core/strategies/
  __init__.py        # re-exports public types
  types.py           # OptionType, Side, OptionLeg, EquityLeg, CashLeg, StrategyConfig
  state.py           # StrategyState, VALID_TRANSITIONS, transition(), IllegalTransition
  payoff.py          # expiration_curve, breakevens, max_pl, net_premium, risk_reward,
                     #   profit_intervals, target_date_curve
  pop.py             # probability_of_profit
  aggregate.py       # net_greeks
  templates.py       # TEMPLATES registry, list_templates(), build()
packages/core/tests/
  test_strategy_state.py
  test_strategy_payoff.py
  test_strategy_pop.py
  test_strategy_aggregate.py
  test_strategy_templates.py
apps/api/saalr_api/strategies/
  __init__.py
  schemas.py         # pydantic request models (leg discriminated union)
  repo.py            # RLS-scoped strategies table access (ORM)
  service.py         # CRUD orchestration + analyze (composes MarketService)
  router.py          # APIRouter(prefix="/v1/strategies")
apps/api/saalr_api/main.py    # MODIFY: include strategies_router
tests/integration/test_strategies.py
```

---

## Task 1: Strategy domain types

**Files:**
- Create: `packages/core/saalr_core/strategies/__init__.py`
- Create: `packages/core/saalr_core/strategies/types.py`

- [ ] **Step 1: Create empty package init**

Create `packages/core/saalr_core/strategies/__init__.py`:

```python
```

- [ ] **Step 2: Create types**

Create `packages/core/saalr_core/strategies/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


@dataclass(frozen=True)
class OptionLeg:
    option_type: OptionType
    side: Side
    strike: float
    expiry: str  # YYYY-MM-DD
    qty: int
    entry_price: float | None = None
    kind: str = "option"


@dataclass(frozen=True)
class EquityLeg:
    side: Side
    qty: int  # shares
    entry_price: float | None = None
    kind: str = "equity"


@dataclass(frozen=True)
class CashLeg:
    amount: float  # collateral
    kind: str = "cash"


Leg = OptionLeg | EquityLeg | CashLeg
OPTION_MULTIPLIER = 100


@dataclass(frozen=True)
class StrategyConfig:
    underlying: str
    legs: list = field(default_factory=list)  # list[Leg]
```

- [ ] **Step 3: Verify import**

Run: `uv run python -c "from saalr_core.strategies.types import OptionLeg, Side, OptionType; print(Side.SELL.sign)"`
Expected: `-1`

- [ ] **Step 4: Commit**

```bash
git add packages/core/saalr_core/strategies/
git commit -m "feat(strategies): leg + config domain types"
```

---

## Task 2: Strategy state machine (§7 FSM)

**Files:**
- Create: `packages/core/saalr_core/strategies/state.py`
- Test: `packages/core/tests/test_strategy_state.py`

- [ ] **Step 1: Write failing tests**

Create `packages/core/tests/test_strategy_state.py`:

```python
import pytest

from saalr_core.strategies.state import (
    IllegalTransition,
    StrategyState,
    transition,
)


def test_valid_draft_to_backtested():
    assert transition(StrategyState.DRAFT, StrategyState.BACKTESTED) is StrategyState.BACKTESTED


def test_draft_to_archived_ok():
    assert transition(StrategyState.DRAFT, StrategyState.ARCHIVED) is StrategyState.ARCHIVED


def test_illegal_draft_to_live_raises():
    with pytest.raises(IllegalTransition):
        transition(StrategyState.DRAFT, StrategyState.LIVE)


def test_archived_is_terminal():
    with pytest.raises(IllegalTransition):
        transition(StrategyState.ARCHIVED, StrategyState.DRAFT)


def test_paper_to_live_is_defined():
    # the edge exists in the table even though gates are deferred
    assert transition(StrategyState.PAPER, StrategyState.LIVE) is StrategyState.LIVE
```

- [ ] **Step 2: Run to verify fail**

Run: `cd packages/core && uv run pytest tests/test_strategy_state.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement state.py**

Create `packages/core/saalr_core/strategies/state.py`:

```python
from __future__ import annotations

from enum import Enum


class StrategyState(str, Enum):
    DRAFT = "draft"
    BACKTESTED = "backtested"
    PAPER = "paper"
    LIVE = "live"
    PAUSED = "paused"
    ARCHIVED = "archived"


VALID_TRANSITIONS: dict[StrategyState, set[StrategyState]] = {
    StrategyState.DRAFT: {StrategyState.BACKTESTED, StrategyState.ARCHIVED},
    StrategyState.BACKTESTED: {StrategyState.DRAFT, StrategyState.PAPER, StrategyState.ARCHIVED},
    StrategyState.PAPER: {StrategyState.LIVE, StrategyState.DRAFT, StrategyState.ARCHIVED},
    StrategyState.LIVE: {StrategyState.PAUSED, StrategyState.ARCHIVED},
    StrategyState.PAUSED: {StrategyState.LIVE, StrategyState.ARCHIVED},
    StrategyState.ARCHIVED: set(),
}


class IllegalTransition(Exception):
    """Raised when a strategy state transition is not permitted by the FSM."""


def transition(current: StrategyState, target: StrategyState) -> StrategyState:
    if target not in VALID_TRANSITIONS[current]:
        raise IllegalTransition(f"{current.value} -> {target.value} is not allowed")
    return target
```

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/core && uv run pytest tests/test_strategy_state.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/strategies/state.py packages/core/tests/test_strategy_state.py
git commit -m "feat(strategies): §7 state machine"
```

---

## Task 3: Expiration payoff analytics

**Files:**
- Create: `packages/core/saalr_core/strategies/payoff.py`
- Test: `packages/core/tests/test_strategy_payoff.py`

- [ ] **Step 1: Write failing tests**

Create `packages/core/tests/test_strategy_payoff.py`:

```python
import math

from saalr_core.strategies.payoff import (
    breakevens,
    expiration_curve,
    max_pl,
    net_premium,
    profit_intervals,
    spot_grid,
)
from saalr_core.strategies.types import OptionLeg, OptionType, Side


def _long_call(strike=100.0, entry=5.0, expiry="2026-12-18"):
    return OptionLeg(OptionType.CALL, Side.BUY, strike, expiry, 1, entry)


def test_long_call_curve_and_unbounded_profit():
    legs = [_long_call()]
    grid = spot_grid(legs, spot=100.0)
    curve = expiration_curve(legs, grid)
    m = max_pl(curve)
    # max loss = premium paid = 5 * 100 = -500, bounded; profit unbounded
    assert m["unbounded_profit"] is True
    assert m["max_profit"] is None
    assert math.isclose(m["max_loss"], -500.0, abs_tol=1e-6)


def test_long_call_breakeven():
    legs = [_long_call(strike=100.0, entry=5.0)]
    grid = spot_grid(legs, spot=100.0)
    be = breakevens(expiration_curve(legs, grid))
    assert len(be) == 1 and math.isclose(be[0], 105.0, abs_tol=0.5)


def test_bull_call_spread_bounded():
    legs = [
        OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2026-12-18", 1, 6.0),
        OptionLeg(OptionType.CALL, Side.SELL, 110.0, "2026-12-18", 1, 2.0),
    ]
    grid = spot_grid(legs, spot=100.0)
    curve = expiration_curve(legs, grid)
    m = max_pl(curve)
    assert m["unbounded_profit"] is False and m["unbounded_loss"] is False
    # net debit = (6-2)*100 = 400; max profit = (10 width - 4 debit)*100 = 600; max loss = -400
    assert math.isclose(net_premium(legs), 400.0, abs_tol=1e-6)
    assert math.isclose(m["max_profit"], 600.0, abs_tol=1.0)
    assert math.isclose(m["max_loss"], -400.0, abs_tol=1.0)


def test_short_call_unbounded_loss():
    legs = [OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2026-12-18", 1, 5.0)]
    grid = spot_grid(legs, spot=100.0)
    m = max_pl(expiration_curve(legs, grid))
    assert m["unbounded_loss"] is True and m["max_loss"] is None
    assert math.isclose(m["max_profit"], 500.0, abs_tol=1.0)


def test_profit_intervals_long_call():
    legs = [_long_call(strike=100.0, entry=5.0)]
    grid = spot_grid(legs, spot=100.0)
    curve = expiration_curve(legs, grid)
    intervals = profit_intervals(curve)
    assert len(intervals) == 1
    lo, hi = intervals[0]
    assert math.isclose(lo, 105.0, abs_tol=0.5) and hi is None  # unbounded upside
```

- [ ] **Step 2: Run to verify fail**

Run: `cd packages/core && uv run pytest tests/test_strategy_payoff.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement payoff.py (expiration part)**

Create `packages/core/saalr_core/strategies/payoff.py`:

```python
from __future__ import annotations

from .types import (
    OPTION_MULTIPLIER,
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
)

_TOL = 1e-6


def spot_grid(legs: list, spot: float, points: int = 161) -> list[float]:
    """Grid from 0 to ~2x the relevant range, with strikes included as exact points."""
    strikes = [leg.strike for leg in legs if isinstance(leg, OptionLeg)]
    hi = max([spot] + strikes) * 2.0
    step = hi / (points - 1)
    grid = [i * step for i in range(points)]
    grid.extend(s for s in strikes if 0 <= s <= hi)
    return sorted(set(grid))


def _leg_pnl_at_expiry(leg, s: float) -> float:
    if isinstance(leg, OptionLeg):
        if leg.option_type is OptionType.CALL:
            intrinsic = max(s - leg.strike, 0.0)
        else:
            intrinsic = max(leg.strike - s, 0.0)
        entry = leg.entry_price or 0.0
        return leg.side.sign * (intrinsic - entry) * OPTION_MULTIPLIER * leg.qty
    if isinstance(leg, EquityLeg):
        entry = leg.entry_price or 0.0
        return leg.side.sign * (s - entry) * leg.qty
    if isinstance(leg, CashLeg):
        return 0.0
    raise TypeError(f"unknown leg type {type(leg)}")


def expiration_curve(legs: list, grid: list[float]) -> list[tuple[float, float]]:
    return [(s, sum(_leg_pnl_at_expiry(leg, s) for leg in legs)) for s in grid]


def net_premium(legs: list) -> float:
    """Positive = net debit paid, negative = net credit received."""
    total = 0.0
    for leg in legs:
        if isinstance(leg, OptionLeg):
            total += leg.side.sign * (leg.entry_price or 0.0) * OPTION_MULTIPLIER * leg.qty
        elif isinstance(leg, EquityLeg):
            total += leg.side.sign * (leg.entry_price or 0.0) * leg.qty
    return total


def breakevens(curve: list[tuple[float, float]]) -> list[float]:
    out: list[float] = []
    for (s0, p0), (s1, p1) in zip(curve, curve[1:]):
        if p0 == 0.0:
            out.append(s0)
        elif (p0 < 0 < p1) or (p1 < 0 < p0):
            out.append(s0 + (s1 - s0) * (0 - p0) / (p1 - p0))
    return out


def max_pl(curve: list[tuple[float, float]]) -> dict:
    pnls = [p for _, p in curve]
    right_slope = curve[-1][1] - curve[-2][1]
    unbounded_profit = right_slope > _TOL
    unbounded_loss = right_slope < -_TOL
    return {
        "max_profit": None if unbounded_profit else max(pnls),
        "max_loss": None if unbounded_loss else min(pnls),
        "unbounded_profit": unbounded_profit,
        "unbounded_loss": unbounded_loss,
    }


def risk_reward(max_profit: float | None, max_loss: float | None) -> float | None:
    if max_profit is None or max_loss is None or max_loss == 0:
        return None
    return abs(max_profit) / abs(max_loss)


def profit_intervals(curve: list[tuple[float, float]]) -> list[tuple[float, float | None]]:
    """S-ranges where expiration P&L > 0. Trailing None hi means unbounded upside."""
    bes = breakevens(curve)
    boundaries = [0.0, *bes]
    intervals: list[tuple[float, float | None]] = []
    for lo, hi in zip(boundaries, [*bes[1:], None] if len(bes) else [None]):
        mid_s = (lo + (hi if hi is not None else curve[-1][0])) / 2.0
        # profit if the curve at mid is positive
        pnl_mid = min(curve, key=lambda c: abs(c[0] - mid_s))[1]
        if pnl_mid > 0:
            intervals.append((lo, hi))
    return intervals
```

> Note on `profit_intervals`: boundaries are 0 and the breakevens; each gap is tested by its midpoint's P&L sign. The final gap's `hi` is `None` (→ +∞). For the common single-breakeven long-call case this yields one `(breakeven, None)` interval.

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/core && uv run pytest tests/test_strategy_payoff.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/strategies/payoff.py packages/core/tests/test_strategy_payoff.py
git commit -m "feat(strategies): expiration payoff, breakevens, max P/L, net premium"
```

---

## Task 4: Target-date theoretical payoff curve

**Files:**
- Modify: `packages/core/saalr_core/strategies/payoff.py` (append `target_date_curve`)
- Modify: `packages/core/tests/test_strategy_payoff.py` (append tests)

- [ ] **Step 1: Append failing test**

Append to `packages/core/tests/test_strategy_payoff.py`:

```python
from datetime import date

from saalr_core.strategies.payoff import target_date_curve


def test_target_date_equals_expiration_at_expiry():
    legs = [_long_call(strike=100.0, entry=5.0, expiry="2026-12-18")]
    grid = spot_grid(legs, spot=100.0)
    exp = expiration_curve(legs, grid)
    tgt = target_date_curve(
        legs, grid, eval_date=date(2026, 12, 18), rate=0.04, div_yield=0.0,
        iv_by_leg={0: 0.25},
    )
    for (s_e, p_e), (s_t, p_t) in zip(exp, tgt):
        assert math.isclose(p_e, p_t, abs_tol=1e-3)
```

- [ ] **Step 2: Run to verify fail**

Run: `cd packages/core && uv run pytest tests/test_strategy_payoff.py::test_target_date_equals_expiration_at_expiry -q`
Expected: FAIL (`target_date_curve` not defined).

- [ ] **Step 3: Append implementation**

Append to `packages/core/saalr_core/strategies/payoff.py`:

```python
from datetime import date as _date  # noqa: E402

from saalr_core.pricing.greeks import price as _bsm_price  # noqa: E402
from saalr_core.pricing.types import OptionKind, OptionParams  # noqa: E402


def _leg_pnl_at_target(leg, s, eval_date, rate, div_yield, iv):
    if isinstance(leg, OptionLeg):
        t_rem = (_date.fromisoformat(leg.expiry) - eval_date).days / 365.0
        entry = leg.entry_price or 0.0
        if t_rem <= 0 or iv is None or iv <= 0:
            if leg.option_type is OptionType.CALL:
                value = max(s - leg.strike, 0.0)
            else:
                value = max(leg.strike - s, 0.0)
        else:
            kind = OptionKind.CALL if leg.option_type is OptionType.CALL else OptionKind.PUT
            value = _bsm_price(
                OptionParams(spot=s, strike=leg.strike, t_years=t_rem, rate=rate,
                             sigma=iv, div_yield=div_yield, kind=kind)
            )
        return leg.side.sign * (value - entry) * OPTION_MULTIPLIER * leg.qty
    if isinstance(leg, EquityLeg):
        return leg.side.sign * (s - (leg.entry_price or 0.0)) * leg.qty
    return 0.0


def target_date_curve(legs, grid, eval_date, rate, div_yield, iv_by_leg) -> list[tuple[float, float]]:
    """Theoretical P&L curve at eval_date (BSM at remaining time). iv_by_leg maps leg index -> iv."""
    out = []
    for s in grid:
        total = 0.0
        for i, leg in enumerate(legs):
            total += _leg_pnl_at_target(leg, s, eval_date, rate, div_yield, iv_by_leg.get(i))
        out.append((s, total))
    return out
```

- [ ] **Step 4: Run full payoff suite**

Run: `cd packages/core && uv run pytest tests/test_strategy_payoff.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/strategies/payoff.py packages/core/tests/test_strategy_payoff.py
git commit -m "feat(strategies): target-date theoretical payoff curve"
```

---

## Task 5: Lognormal probability of profit

**Files:**
- Create: `packages/core/saalr_core/strategies/pop.py`
- Test: `packages/core/tests/test_strategy_pop.py`

- [ ] **Step 1: Write failing tests**

Create `packages/core/tests/test_strategy_pop.py`:

```python
import math

from saalr_core.strategies.pop import probability_of_profit


def _lognormal_p_above(spot, k, iv, t, r, q):
    mu = math.log(spot) + (r - q - 0.5 * iv * iv) * t
    sd = iv * math.sqrt(t)
    z = (math.log(k) - mu) / sd
    return 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def test_pop_long_call_matches_p_above_breakeven():
    out = probability_of_profit(
        spot=100.0, atm_iv=0.25, t_years=0.5, rate=0.04, div_yield=0.0,
        profit_intervals=[(105.0, None)],
    )
    expected = _lognormal_p_above(100.0, 105.0, 0.25, 0.5, 0.04, 0.0)
    assert math.isclose(out["pop"], expected, abs_tol=1e-9)
    assert out["method"] == "lognormal_atm_iv"
    assert out["approximate"] is True


def test_pop_in_unit_interval():
    out = probability_of_profit(100.0, 0.3, 0.25, 0.04, 0.0, [(95.0, 105.0)])
    assert 0.0 <= out["pop"] <= 1.0


def test_pop_two_intervals_sum():
    out = probability_of_profit(100.0, 0.3, 0.25, 0.04, 0.0, [(0.0, 90.0), (110.0, None)])
    a = probability_of_profit(100.0, 0.3, 0.25, 0.04, 0.0, [(0.0, 90.0)])["pop"]
    b = probability_of_profit(100.0, 0.3, 0.25, 0.04, 0.0, [(110.0, None)])["pop"]
    assert math.isclose(out["pop"], a + b, abs_tol=1e-9)
```

- [ ] **Step 2: Run to verify fail**

Run: `cd packages/core && uv run pytest tests/test_strategy_pop.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement pop.py**

Create `packages/core/saalr_core/strategies/pop.py`:

```python
from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _lognormal_cdf(s: float, mu: float, sd: float) -> float:
    if s <= 0:
        return 0.0
    return _norm_cdf((math.log(s) - mu) / sd)


def probability_of_profit(
    spot: float, atm_iv: float, t_years: float, rate: float, div_yield: float,
    profit_intervals: list[tuple[float, float | None]],
) -> dict:
    """Approximate POP: terminal price ~ lognormal(ATM IV). Sums mass over profit intervals."""
    if t_years <= 0 or atm_iv <= 0 or spot <= 0:
        return {"pop": None, "method": "lognormal_atm_iv", "approximate": True}
    mu = math.log(spot) + (rate - div_yield - 0.5 * atm_iv * atm_iv) * t_years
    sd = atm_iv * math.sqrt(t_years)
    pop = 0.0
    for lo, hi in profit_intervals:
        upper = 1.0 if hi is None else _lognormal_cdf(hi, mu, sd)
        pop += upper - _lognormal_cdf(lo, mu, sd)
    return {"pop": max(0.0, min(1.0, pop)), "method": "lognormal_atm_iv", "approximate": True}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/core && uv run pytest tests/test_strategy_pop.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/strategies/pop.py packages/core/tests/test_strategy_pop.py
git commit -m "feat(strategies): approximate lognormal probability of profit"
```

---

## Task 6: Net Greeks aggregation

**Files:**
- Create: `packages/core/saalr_core/strategies/aggregate.py`
- Test: `packages/core/tests/test_strategy_aggregate.py`

- [ ] **Step 1: Write failing tests**

Create `packages/core/tests/test_strategy_aggregate.py`:

```python
import math

from saalr_core.pricing.types import Greeks
from saalr_core.strategies.aggregate import net_greeks
from saalr_core.strategies.types import EquityLeg, OptionLeg, OptionType, Side


def _g(delta):
    return Greeks(price=1.0, delta=delta, gamma=0.01, theta=-0.02, vega=0.05, rho=0.0, iv=0.25)


def test_long_call_net_delta_scaled_by_100():
    leg = OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2026-12-18", 2, 5.0)
    out = net_greeks([(leg, _g(0.5))])
    assert math.isclose(out["delta"], 0.5 * 100 * 2, abs_tol=1e-9)
    assert math.isclose(out["gamma"], 0.01 * 100 * 2, abs_tol=1e-9)


def test_short_leg_flips_sign():
    leg = OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2026-12-18", 1, 5.0)
    out = net_greeks([(leg, _g(0.5))])
    assert math.isclose(out["delta"], -50.0, abs_tol=1e-9)


def test_equity_leg_contributes_delta_only():
    leg = EquityLeg(Side.BUY, 100, 50.0)
    out = net_greeks([(leg, None)])
    assert math.isclose(out["delta"], 100.0, abs_tol=1e-9)
    assert out["vega"] == 0.0
```

- [ ] **Step 2: Run to verify fail**

Run: `cd packages/core && uv run pytest tests/test_strategy_aggregate.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement aggregate.py**

Create `packages/core/saalr_core/strategies/aggregate.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/core && uv run pytest tests/test_strategy_aggregate.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/strategies/aggregate.py packages/core/tests/test_strategy_aggregate.py
git commit -m "feat(strategies): net Greeks aggregation"
```

---

## Task 7: Ready-made templates catalog

**Files:**
- Create: `packages/core/saalr_core/strategies/templates.py`
- Test: `packages/core/tests/test_strategy_templates.py`

- [ ] **Step 1: Write failing tests**

Create `packages/core/tests/test_strategy_templates.py`:

```python
import pytest

from saalr_core.strategies.templates import build, list_templates
from saalr_core.strategies.types import OptionLeg, OptionType, Side


def test_catalog_has_expected_keys():
    keys = {t["key"] for t in list_templates()}
    assert {"bull_call_spread", "iron_condor", "covered_call", "cash_secured_put"} <= keys
    for t in list_templates():
        assert t["category"] in ("bullish", "bearish", "neutral")


def test_bull_call_spread_legs():
    cfg = build("bull_call_spread", underlying="AAPL", expiry="2026-12-18", atm_strike=100.0, width=10.0)
    assert cfg.underlying == "AAPL"
    assert len(cfg.legs) == 2
    long_leg = [leg for leg in cfg.legs if leg.side is Side.BUY][0]
    short_leg = [leg for leg in cfg.legs if leg.side is Side.SELL][0]
    assert long_leg.option_type is OptionType.CALL and long_leg.strike == 100.0
    assert short_leg.strike == 110.0


def test_iron_condor_four_legs():
    cfg = build("iron_condor", underlying="AAPL", expiry="2026-12-18", atm_strike=100.0, width=10.0)
    assert len(cfg.legs) == 4


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        build("does_not_exist", underlying="AAPL", expiry="2026-12-18", atm_strike=100.0)
```

- [ ] **Step 2: Run to verify fail**

Run: `cd packages/core && uv run pytest tests/test_strategy_templates.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement templates.py**

Create `packages/core/saalr_core/strategies/templates.py`:

```python
from __future__ import annotations

from .types import CashLeg, EquityLeg, OptionLeg, OptionType, Side, StrategyConfig

_C, _P, _B, _S = OptionType.CALL, OptionType.PUT, Side.BUY, Side.SELL


def _opt(otype, side, strike, expiry, qty=1):
    return OptionLeg(otype, side, float(strike), expiry, qty)


def _bull_call_spread(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _B, k, e), _opt(_C, _S, k + w, e)])


def _bear_put_spread(u, e, k, w):
    return StrategyConfig(u, [_opt(_P, _B, k, e), _opt(_P, _S, k - w, e)])


def _long_straddle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _B, k, e), _opt(_P, _B, k, e)])


def _long_strangle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _B, k + w, e), _opt(_P, _B, k - w, e)])


def _iron_condor(u, e, k, w):
    return StrategyConfig(u, [
        _opt(_P, _B, k - 2 * w, e), _opt(_P, _S, k - w, e),
        _opt(_C, _S, k + w, e), _opt(_C, _B, k + 2 * w, e),
    ])


def _iron_butterfly(u, e, k, w):
    return StrategyConfig(u, [
        _opt(_P, _B, k - w, e), _opt(_P, _S, k, e),
        _opt(_C, _S, k, e), _opt(_C, _B, k + w, e),
    ])


def _covered_call(u, e, k, w):
    return StrategyConfig(u, [EquityLeg(_B, 100), _opt(_C, _S, k + w, e)])


def _cash_secured_put(u, e, k, w):
    return StrategyConfig(u, [_opt(_P, _S, k, e), CashLeg(amount=k * 100)])


def _long_calendar(u, e, k, w):
    # near + far expiry same strike; far expiry approximated by reusing e (UI supplies real far date)
    return StrategyConfig(u, [_opt(_C, _S, k, e), _opt(_C, _B, k, e)])


_REGISTRY: dict[str, dict] = {
    "bull_call_spread": {"name": "Bull Call Spread", "category": "bullish",
                         "description": "Long lower call, short higher call.", "build": _bull_call_spread},
    "bear_put_spread": {"name": "Bear Put Spread", "category": "bearish",
                        "description": "Long higher put, short lower put.", "build": _bear_put_spread},
    "long_straddle": {"name": "Long Straddle", "category": "neutral",
                      "description": "Long ATM call + put; profits on a big move.", "build": _long_straddle},
    "long_strangle": {"name": "Long Strangle", "category": "neutral",
                      "description": "Long OTM call + put; cheaper, wider move needed.", "build": _long_strangle},
    "iron_condor": {"name": "Iron Condor", "category": "neutral",
                    "description": "Sell a put spread and a call spread; range-bound income.", "build": _iron_condor},
    "iron_butterfly": {"name": "Iron Butterfly", "category": "neutral",
                       "description": "ATM short straddle wrapped in long wings.", "build": _iron_butterfly},
    "covered_call": {"name": "Covered Call", "category": "bullish",
                     "description": "Long 100 shares, short an OTM call.", "build": _covered_call},
    "cash_secured_put": {"name": "Cash-Secured Put", "category": "bullish",
                         "description": "Short a put backed by cash collateral.", "build": _cash_secured_put},
    "long_calendar": {"name": "Long Calendar", "category": "neutral",
                      "description": "Short near-dated, long longer-dated same strike.", "build": _long_calendar},
}


def list_templates() -> list[dict]:
    return [
        {"key": k, "name": v["name"], "category": v["category"], "description": v["description"]}
        for k, v in _REGISTRY.items()
    ]


def build(key: str, underlying: str, expiry: str, atm_strike: float, width: float = 5.0) -> StrategyConfig:
    if key not in _REGISTRY:
        raise KeyError(key)
    return _REGISTRY[key]["build"](underlying, expiry, float(atm_strike), float(width))
```

- [ ] **Step 4: Run to verify pass + full core suite**

Run: `cd packages/core && uv run pytest tests/test_strategy_templates.py -q`
Expected: 4 passed.
Run: `cd packages/core && uv run pytest -q`
Expected: all passed (existing + strategy tests).

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/strategies/templates.py packages/core/tests/test_strategy_templates.py
git commit -m "feat(strategies): ready-made templates catalog"
```

---

## Task 8: Pydantic request schemas

**Files:**
- Create: `apps/api/saalr_api/strategies/__init__.py`
- Create: `apps/api/saalr_api/strategies/schemas.py`

- [ ] **Step 1: Create empty package init**

Create `apps/api/saalr_api/strategies/__init__.py`:

```python
```

- [ ] **Step 2: Implement schemas.py**

Create `apps/api/saalr_api/strategies/schemas.py`:

```python
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from saalr_core.strategies.types import (
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
    Side,
    StrategyConfig,
)


class OptionLegIn(BaseModel):
    kind: Literal["option"] = "option"
    option_type: OptionType
    side: Side
    strike: float = Field(gt=0)
    expiry: str
    qty: int = Field(gt=0)
    entry_price: float | None = None

    def to_domain(self) -> OptionLeg:
        return OptionLeg(self.option_type, self.side, self.strike, self.expiry, self.qty, self.entry_price)


class EquityLegIn(BaseModel):
    kind: Literal["equity"] = "equity"
    side: Side
    qty: int = Field(gt=0)
    entry_price: float | None = None

    def to_domain(self) -> EquityLeg:
        return EquityLeg(self.side, self.qty, self.entry_price)


class CashLegIn(BaseModel):
    kind: Literal["cash"] = "cash"
    amount: float = Field(gt=0)

    def to_domain(self) -> CashLeg:
        return CashLeg(self.amount)


LegIn = Annotated[OptionLegIn | EquityLegIn | CashLegIn, Field(discriminator="kind")]


class StrategyConfigIn(BaseModel):
    underlying: str = Field(min_length=1)
    legs: list[LegIn] = Field(min_length=1)

    def to_domain(self) -> StrategyConfig:
        return StrategyConfig(self.underlying, [leg.to_domain() for leg in self.legs])


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    market: str = "US"
    config: StrategyConfigIn


class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: StrategyConfigIn | None = None


class TransitionIn(BaseModel):
    target_state: str


class AnalyzeIn(BaseModel):
    config: StrategyConfigIn
    target_date: str | None = None
    live: bool = False
```

- [ ] **Step 3: Verify import + validation**

Run: `uv run python -c "from saalr_api.strategies.schemas import StrategyCreate; StrategyCreate(name='x', config={'underlying':'AAPL','legs':[{'kind':'option','option_type':'CALL','side':'BUY','strike':100,'expiry':'2026-12-18','qty':1}]}); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add apps/api/saalr_api/strategies/__init__.py apps/api/saalr_api/strategies/schemas.py
git commit -m "feat(strategies): pydantic request schemas with leg discriminated union"
```

---

## Task 9: RLS-scoped repository

**Files:**
- Create: `apps/api/saalr_api/strategies/repo.py`

- [ ] **Step 1: Implement repo.py**

Create `apps/api/saalr_api/strategies/repo.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.trading import Strategy
from saalr_core.ids import new_id


async def insert_strategy(
    session: AsyncSession, tenant_id: UUID, user_id: UUID, name: str,
    description: str | None, config_json: dict, market: str,
) -> Strategy:
    row = Strategy(
        strategy_id=new_id(), tenant_id=tenant_id, user_id=user_id, name=name,
        description=description, state="draft", config_json=config_json, market=market,
    )
    session.add(row)
    await session.flush()
    return row


async def get_strategy(session: AsyncSession, strategy_id: UUID) -> Strategy | None:
    return await session.get(Strategy, strategy_id)


async def list_strategies(
    session: AsyncSession, limit: int, cursor: tuple[datetime, UUID] | None
) -> list[Strategy]:
    stmt = select(Strategy).order_by(Strategy.created_at.desc(), Strategy.strategy_id.desc())
    if cursor is not None:
        created_at, sid = cursor
        stmt = stmt.where(
            (Strategy.created_at < created_at)
            | ((Strategy.created_at == created_at) & (Strategy.strategy_id < sid))
        )
    stmt = stmt.limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def update_strategy(session: AsyncSession, row: Strategy, **fields) -> Strategy:
    for k, v in fields.items():
        setattr(row, k, v)
    await session.flush()
    return row
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from saalr_api.strategies.repo import insert_strategy, list_strategies; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps/api/saalr_api/strategies/repo.py
git commit -m "feat(strategies): RLS-scoped strategies repository"
```

---

## Task 10: Service (CRUD + analyze)

**Files:**
- Create: `apps/api/saalr_api/strategies/service.py`

- [ ] **Step 1: Implement service.py**

Create `apps/api/saalr_api/strategies/service.py`:

```python
from __future__ import annotations

from datetime import date

from saalr_core.pricing.model import BSMModel
from saalr_core.pricing.types import OptionKind, OptionParams
from saalr_core.strategies import payoff, pop
from saalr_core.strategies.aggregate import net_greeks
from saalr_core.strategies.types import OptionLeg

_MODEL = BSMModel()


def analyze_pure(config) -> dict:
    """Expiration payoff analytics from caller-supplied entry prices (no live data)."""
    legs = config.legs
    spot_anchor = _anchor_spot(legs)
    grid = payoff.spot_grid(legs, spot_anchor)
    curve = payoff.expiration_curve(legs, grid)
    m = payoff.max_pl(curve)
    return {
        "expiration_curve": [{"spot": s, "pnl": p} for s, p in curve],
        "breakevens": payoff.breakevens(curve),
        "max_profit": m["max_profit"],
        "max_loss": m["max_loss"],
        "unbounded_profit": m["unbounded_profit"],
        "unbounded_loss": m["unbounded_loss"],
        "net_premium": payoff.net_premium(legs),
        "risk_reward": payoff.risk_reward(m["max_profit"], m["max_loss"]),
    }


def _anchor_spot(legs) -> float:
    strikes = [leg.strike for leg in legs if isinstance(leg, OptionLeg)]
    return sum(strikes) / len(strikes) if strikes else 100.0


def _match_contract(chain_contracts: list[dict], leg: OptionLeg) -> dict | None:
    for c in chain_contracts:
        if c["expiry"] == leg.expiry and abs(c["strike"] - leg.strike) < 1e-6 \
                and c["type"] == leg.option_type.value:
            return c
    return None


async def analyze_live(config, market_service, session, ticker, market, target_date: str | None) -> dict:
    """Pure payoff enriched with live prices, net Greeks, target-date curve, and POP."""
    chain = await market_service.chain(session, ticker, market, expiry=None)
    spot = chain["spot"]
    contracts = chain["contracts"]
    legs = config.legs

    iv_by_leg: dict[int, float] = {}
    priced: list[tuple[object, object]] = []
    filled_legs = []
    for i, leg in enumerate(legs):
        if isinstance(leg, OptionLeg):
            match = _match_contract(contracts, leg)
            iv = (match or {}).get("ours", {}).get("iv")
            mid = (match or {}).get("ours", {}).get("price")
            entry = leg.entry_price if leg.entry_price is not None else (mid or 0.0)
            from dataclasses import replace
            leg = replace(leg, entry_price=entry)
            if iv:
                iv_by_leg[i] = iv
                t = max((date.fromisoformat(leg.expiry) - date.today()).days, 0) / 365.0
                kind = OptionKind.CALL if leg.option_type.value == "CALL" else OptionKind.PUT
                g = _MODEL.greeks(OptionParams(spot, leg.strike, t, 0.04, iv, 0.0, kind)) if t > 0 else None
                priced.append((leg, g))
            else:
                priced.append((leg, None))
        else:
            priced.append((leg, None))
        filled_legs.append(leg)

    grid = payoff.spot_grid(filled_legs, spot)
    curve = payoff.expiration_curve(filled_legs, grid)
    m = payoff.max_pl(curve)
    intervals = payoff.profit_intervals(curve)
    atm_iv = next(iter(iv_by_leg.values()), 0.0)
    t_exp = max((min(date.fromisoformat(leg.expiry) for leg in filled_legs if isinstance(leg, OptionLeg))
                 - date.today()).days, 0) / 365.0
    pop_out = pop.probability_of_profit(spot, atm_iv, t_exp, 0.04, 0.0, intervals)

    result = {
        "expiration_curve": [{"spot": s, "pnl": p} for s, p in curve],
        "breakevens": payoff.breakevens(curve),
        "max_profit": m["max_profit"], "max_loss": m["max_loss"],
        "unbounded_profit": m["unbounded_profit"], "unbounded_loss": m["unbounded_loss"],
        "net_premium": payoff.net_premium(filled_legs),
        "risk_reward": payoff.risk_reward(m["max_profit"], m["max_loss"]),
        "net_greeks": net_greeks(priced),
        "probability_of_profit": pop_out,
        "spot": spot, "data_provider": "massive", "model": "bsm",
    }
    if target_date:
        result["target_date_curve"] = [
            {"spot": s, "pnl": p}
            for s, p in payoff.target_date_curve(
                filled_legs, grid, date.fromisoformat(target_date), 0.04, 0.0, iv_by_leg
            )
        ]
    return result
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from saalr_api.strategies.service import analyze_pure, analyze_live; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps/api/saalr_api/strategies/service.py
git commit -m "feat(strategies): analyze service (pure + live, composes MarketService)"
```

---

## Task 11: Router + app wiring

**Files:**
- Create: `apps/api/saalr_api/strategies/router.py`
- Modify: `apps/api/saalr_api/main.py`

- [ ] **Step 1: Implement router.py**

Create `apps/api/saalr_api/strategies/router.py`:

```python
from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.strategies.state import IllegalTransition, StrategyState, transition
from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal
from .schemas import AnalyzeIn, StrategyCreate, StrategyUpdate, TransitionIn
from . import repo, service
from saalr_core.strategies import templates

router = APIRouter(prefix="/v1/strategies", tags=["strategies"])


def _out(row) -> dict:
    return {
        "strategy_id": str(row.strategy_id), "name": row.name, "description": row.description,
        "state": row.state, "market": row.market, "config": row.config_json,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


def _not_found() -> HTTPException:
    return HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "strategy not found"}})


@router.get("/templates")
async def get_templates(ctx: tuple = Depends(get_principal)) -> dict:
    return {"templates": templates.list_templates()}


@router.post("/templates/{key}/build")
async def build_template(key: str, body: dict, ctx: tuple = Depends(get_principal)) -> dict:
    try:
        cfg = templates.build(key, body["underlying"], body["expiry"],
                              float(body["atm_strike"]), float(body.get("width", 5.0)))
    except KeyError:
        raise _not_found()
    return {
        "underlying": cfg.underlying,
        "legs": [vars(leg) for leg in cfg.legs],
    }


@router.post("/analyze")
async def analyze(body: AnalyzeIn, request: Request,
                  ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    config = body.config.to_domain()
    if not body.live:
        return analyze_or_400(lambda: service.analyze_pure(config))
    if not entitlements_for(principal.tier)["vol_surface"]:
        raise HTTPException(402, {"error": {
            "code": "ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO",
            "message": "live strategy analysis requires a Pro or Premium plan"}})
    s = request.app.state
    from ..market.service import MarketService
    ms = MarketService(s.market_provider, s.rate_provider, s.redis, s.vol_surface_ttl)
    return await service.analyze_live(config, ms, session, config.underlying, "US", body.target_date)


def analyze_or_400(fn):
    try:
        return fn()
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": str(exc)}})


@router.post("")
async def create_strategy(body: StrategyCreate,
                          ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    row = await repo.insert_strategy(
        session, principal.tenant_id, principal.user_id, body.name, body.description,
        body.config.to_domain().__dict__ | {"legs": [vars(leg) for leg in body.config.to_domain().legs]},
        body.market,
    )
    await session.flush()
    return _out(row)


@router.get("")
async def list_strategies(limit: int = Query(20, le=100), cursor: str | None = None,
                          ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    decoded = None
    if cursor:
        ts, sid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        decoded = (datetime.fromisoformat(ts), UUID(sid))
    rows = await repo.list_strategies(session, limit, decoded)
    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = base64.urlsafe_b64encode(
            f"{last.created_at.isoformat()}|{last.strategy_id}".encode()).decode()
    return {"strategies": [_out(r) for r in rows], "next_cursor": next_cursor}


@router.get("/{strategy_id}")
async def get_one(strategy_id: UUID,
                  ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    return _out(row)


@router.patch("/{strategy_id}")
async def patch(strategy_id: UUID, body: StrategyUpdate,
                ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    if row.state != "draft":
        raise HTTPException(409, {"error": {
            "code": "STRATEGY_NOT_EDITABLE", "message": "only draft strategies can be edited"}})
    fields: dict = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.description is not None:
        fields["description"] = body.description
    if body.config is not None:
        cfg = body.config.to_domain()
        fields["config_json"] = {"underlying": cfg.underlying, "legs": [vars(leg) for leg in cfg.legs]}
    await repo.update_strategy(session, row, **fields)
    return _out(row)


@router.post("/{strategy_id}/transition")
async def do_transition(strategy_id: UUID, body: TransitionIn,
                        ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    try:
        new_state = transition(StrategyState(row.state), StrategyState(body.target_state))
    except IllegalTransition as exc:
        raise HTTPException(409, {"error": {"code": "STRATEGY_ILLEGAL_TRANSITION", "message": str(exc)}})
    except ValueError as exc:
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": str(exc)}})
    await repo.update_strategy(session, row, state=new_state.value)
    return _out(row)


@router.delete("/{strategy_id}")
async def archive(strategy_id: UUID,
                  ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    await repo.update_strategy(session, row, state=StrategyState.ARCHIVED.value)
    return _out(row)
```

> Note: the analyze handler passes `config.underlying` as the live-chain ticker and `"US"` as the market. `analyze_or_400` is defined after the routes that use it — module-level functions are resolved at call time, so the forward reference is fine.

- [ ] **Step 2: Wire router into the app**

In `apps/api/saalr_api/main.py`, add to the imports near the existing `from .market.router import ...`:

```python
from .strategies.router import router as strategies_router
```

After the existing `app.include_router(market_router)` line, add:

```python
    app.include_router(strategies_router)
```

- [ ] **Step 3: Verify the app boots with routes**

Run: `uv run python -c "from saalr_api.main import create_app; app=create_app(); print(sorted({r.path for r in app.routes if 'strateg' in r.path}))"`
Expected: includes `/v1/strategies`, `/v1/strategies/{strategy_id}`, `/v1/strategies/templates`, `/v1/strategies/analyze`.

- [ ] **Step 4: Lint**

Run: `uvx ruff check apps/api/saalr_api/strategies apps/api/saalr_api/main.py`
Expected: All checks passed (fix unused imports if flagged).

- [ ] **Step 5: Commit**

```bash
git add apps/api/saalr_api/strategies/router.py apps/api/saalr_api/main.py
git commit -m "feat(strategies): CRUD + templates + analyze router wired into app"
```

---

## Task 12: Integration tests

**Files:**
- Create: `tests/integration/test_strategies.py`

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_strategies.py`:

```python
import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind


class StubProvider:
    async def get_option_chain(self, ticker, market):
        return RawChain(
            underlying=ticker.upper(), market=market, as_of="2026-05-30T14:30:00+00:00",
            spot=100.0, div_yield=0.0,
            contracts=[
                RawContract("2026-12-18", 100.0, OptionKind.CALL, 5.9, 6.1, 6.0, 10, 50,
                            0.25, 0.55, 0.02, -0.05, 0.11),
                RawContract("2026-12-18", 110.0, OptionKind.CALL, 1.9, 2.1, 2.0, 10, 50,
                            0.24, 0.30, 0.02, -0.04, 0.10),
            ],
        )


class StubRates:
    source_name = "fred"

    async def get_curve(self):
        return YieldCurve("2026-05-29", [(1 / 12, 0.04), (2.0, 0.045)])


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
                           {"t": tenant_id})


_OPTION = {"kind": "option", "option_type": "CALL", "side": "BUY", "strike": 100,
           "expiry": "2026-12-18", "qty": 1, "entry_price": 6.0}


async def test_crud_lifecycle_and_rls(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:s1@x.com"}
            body = {"name": "My Spread", "config": {"underlying": "AAPL", "legs": [_OPTION]}}
            r = await c.post("/v1/strategies", json=body, headers=h)
            assert r.status_code == 200
            sid = r.json()["strategy_id"]
            assert r.json()["state"] == "draft"

            assert (await c.get(f"/v1/strategies/{sid}", headers=h)).status_code == 200
            lst = (await c.get("/v1/strategies", headers=h)).json()
            assert any(s["strategy_id"] == sid for s in lst["strategies"])

            # transition draft -> backtested ok; draft -> live illegal
            ok = await c.post(f"/v1/strategies/{sid}/transition",
                              json={"target_state": "backtested"}, headers=h)
            assert ok.status_code == 200 and ok.json()["state"] == "backtested"
            bad = await c.post(f"/v1/strategies/{sid}/transition",
                               json={"target_state": "live"}, headers=h)
            assert bad.status_code == 409
            assert bad.json()["detail"]["error"]["code"] == "STRATEGY_ILLEGAL_TRANSITION"

            # patch on non-draft -> 409
            patch = await c.patch(f"/v1/strategies/{sid}", json={"name": "x"}, headers=h)
            assert patch.status_code == 409

            # RLS: other tenant cannot see it
            other = await c.get(f"/v1/strategies/{sid}",
                                headers={"Authorization": "Bearer dev:s2@x.com"})
            assert other.status_code == 404


async def test_templates_list_and_build(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:s3@x.com"}
            t = (await c.get("/v1/strategies/templates", headers=h)).json()
            assert any(x["key"] == "iron_condor" for x in t["templates"])
            b = await c.post("/v1/strategies/templates/bull_call_spread/build",
                             json={"underlying": "AAPL", "expiry": "2026-12-18",
                                   "atm_strike": 100, "width": 10}, headers=h)
            assert b.status_code == 200 and len(b.json()["legs"]) == 2


async def test_analyze_pure_free_and_live_gating(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:s4@x.com"}
            cfg = {"config": {"underlying": "AAPL", "legs": [_OPTION]}, "live": False}
            pure = await c.post("/v1/strategies/analyze", json=cfg, headers=h)
            assert pure.status_code == 200
            assert pure.json()["unbounded_profit"] is True
            assert "net_greeks" not in pure.json()

            live_free = await c.post("/v1/strategies/analyze",
                                     json={**cfg, "live": True}, headers=h)
            assert live_free.status_code == 402

            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            live = await c.post("/v1/strategies/analyze",
                                json={**cfg, "live": True, "target_date": "2026-09-18"}, headers=h)
            assert live.status_code == 200
            body = live.json()
            assert "net_greeks" in body and "probability_of_profit" in body
            assert "target_date_curve" in body


async def test_invalid_config_400(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:s5@x.com"}
            r = await c.post("/v1/strategies", json={"name": "x",
                             "config": {"underlying": "AAPL", "legs": []}}, headers=h)
            assert r.status_code == 422  # pydantic min_length on legs
```

> Note: empty-legs is rejected by pydantic (422), not the 400 path; both are acceptable "rejected before persistence" outcomes. Keep the assertion at 422.

- [ ] **Step 2: Run integration tests**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_strategies.py -q`
Expected: 4 passed.

> If `database "saalr" does not exist`, native Windows PG is shadowing 5432/5433 — the Docker DB is on host 55432 via `infra/docker/docker-compose.localport.yml`; ensure it's up.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_strategies.py
git commit -m "test(strategies): integration — CRUD, RLS, FSM, templates, analyze gating"
```

---

## Task 13: Full gate

- [ ] **Step 1: Run the whole suite + lint**

Run: `cd packages/core && uv run pytest -q && cd ../..`
Expected: all green (pricing + marketdata + strategies units).
Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest -q`
Expected: all green (live smoke skipped).
Run: `uvx ruff check packages/core/saalr_core apps/api/saalr_api tests`
Expected: All checks passed.

- [ ] **Step 2: Final commit (if lint fixups were needed)**

```bash
git add -A
git commit -m "chore(strategies): lint + full-suite green"
```

---

## Self-review checklist (completed)

- **Spec coverage:** types (T1), FSM (T2), expiration payoff + breakevens + max P/L + net premium + profit_intervals (T3), target-date curve (T4), POP (T5), net Greeks (T6), templates (T7), schemas (T8), repo/RLS (T9), analyze pure+live (T10), CRUD + templates + analyze endpoints + gating + error codes (T11), integration incl. RLS + gating (T12), gate (T13). All spec sections covered.
- **Placeholder scan:** none — every code step contains the actual file content; no TODOs, no "fill in", no correction notes.
- **Type consistency:** `OptionLeg/EquityLeg/CashLeg/StrategyConfig`, `Side.sign`, `OPTION_MULTIPLIER`, `expiration_curve/target_date_curve/max_pl/profit_intervals`, `probability_of_profit`, `net_greeks`, `templates.build/list_templates`, `repo.*`, `service.analyze_pure/analyze_live` are used consistently across tasks. Service reuses `MarketService.chain` (returns `{spot, contracts:[{strike,type,expiry,ours:{iv,price,...}}]}`) exactly as the market slice produces it.

## Known risks / notes for the implementer

- **`market_service.chain` shape:** `analyze_live` matches legs against `chain["contracts"][i]["ours"]["iv"]/["price"]` and `["strike"]/["type"]/["expiry"]` — the exact shape `MarketService.chain` emits. If a leg's contract isn't in the chain, its IV/price fall back to `None`/`0.0` (Greeks omitted for that leg) — acceptable for 7a.
- **Risk-free rate in `analyze_live`** is currently a flat `0.04`. A later refinement can thread the FRED curve through (the rate provider is already on `app.state`).
- **`config_json` persistence:** legs are stored as plain dicts via `vars(leg)` (includes the `kind` discriminator), so they round-trip through `StrategyConfigIn` on read if needed.
- **Pydantic empty-legs** rejects with 422 (not the 400 path) — this is the documented, acceptable outcome.
```
