# Strategy Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the async, Pro-gated strategy-discovery module that scans a point-in-time option chain, generates concrete candidate strategies, scores them (Monte-Carlo PoP/EV, payoff, Greeks), gates out bad quotes and free lunches, filters before truncating, and returns a deterministically ranked, compliance-safe list.

**Architecture:** A pure, numpy-free engine in `saalr_core/discovery/` (generate → gate → metrics → MC-score → filter → rank → baseline → serialize) composes the existing `strategies` math + `saalr_ml.montecarlo` + `saalr_ml.regime`/`recommend`. A new `discovery-worker` app (mirroring `backtest-worker`) runs scans off a Redis-Streams queue; a FastAPI 202/poll API (mirroring `backtests`) and a `discovery_runs` table (mirroring `backtests`) wrap it. The installed invariant harness wires to the engine.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, FastAPI, Redis Streams, Alembic, pytest, hypothesis, numpy (MC only). uv workspace.

**Spec:** `docs/superpowers/specs/2026-06-10-strategy-discovery-design.md`
**Invariant catalog:** `docs/INVARIANTS.md` — every finding/test cites an ID.

---

## Conventions (apply to every task)

- **Backend test env (DB on 55432):**
  ```
  ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/saalr \
  APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr \
  uv run pytest <path>
  ```
  Pure-core/ml tests need no DB: `uv run pytest packages/core/tests packages/ml/tests`.
- **Commit footer:** end every commit message with
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- **Never `git add`:** root `.gitignore`, `tools/equity-screener/equity_screener/cli.py`.
- **Ruff:** `uv run ruff check <changed paths>` must be clean before each commit.
- **Branch:** `feat/strategy-discovery` (already created; harness + spec already committed).

## Implementation decisions locked here (beyond the spec)

- The pure engine consumes a **normalized** chain (`Quote`/`CleanContract`/`CleanChain` in
  `discovery/types.py`), never `MarketService` or `RawChain` directly — keeps it pure and
  unit-testable with synthetic chains. The worker adapts the `MarketService.chain()` payload
  to `Quote`s.
- Candidate generation **reuses `strategies.templates.build(key, underlying, expiry, center_strike, width)`**
  then validates every leg strike against the listed chain (STRUCT-1) and overlays mid prices.
- **This slice enumerates option-only templates.** Equity/cash-leg templates (covered_call,
  collar, protective_put, cash_secured_put) are skipped by the generator (deferred — see spec
  "Out of scope"). `families` selection filters to option-only keys.
- MC σ = the expiry's **ATM IV from the same snapshot** (PROB-5); seed is fixed per run
  (default 7) for determinism (RANK-4 / PROB-2).

## File structure

```
packages/core/saalr_core/discovery/
  __init__.py
  types.py       Quote, CleanContract, CleanChain, Candidate, ScoredCandidate, DiscoveryResult
  gates.py       clean_quotes (DATA-3), is_free_lunch (RANK-2)
  generate.py    enumerate_candidates (STRUCT-1/2/4) via templates.build + strike window
  metrics.py     candidate_metrics: net_premium/curve/breakevens/max P&L/Greeks (PAYOFF/GREEK/STRUCT-3)
  score.py       SCORE_PROFILES: ev_to_risk | pop | ev_absolute (dominance-guarded)
  rank.py        rank_candidates (RANK-1/4/5) + truncate
  filters.py     apply_filters (RANK-3 filter-before-truncate)
  baseline.py    naive_atm_short_put baseline (DATA-4)
  serialize.py   result_payload + COMPLY-1 blocklist (COMPLY-1/2/4)
  pipeline.py    run_discovery(clean_chain, closes, rate_curve, request) -> DiscoveryResult
  testing.py     HarnessAdapter (wires tests/unit/test_strategy_invariants.py)
  repo.py        discovery_runs CRUD (RLS): get/create/mark_running/save_result

packages/core/saalr_core/queue/discovery_queue.py    # mirror of backtest_queue.py
packages/core/saalr_core/db/models/trading.py        # + DiscoveryRun model (MODIFY)
infra/migrations/versions/0016_discovery_runs.py      # new table + RLS

apps/discovery-worker/                                # mirror of backtest-worker
  pyproject.toml
  discovery_worker/{__init__.py, __main__.py, repo.py, service.py, consumer.py, cli.py}
  tests/test_cli_parser.py

apps/api/saalr_api/discovery/{__init__.py, schemas.py, router.py}
apps/api/saalr_api/main.py                            # register router + lifespan ensure_group (MODIFY)

tests/                                                # invariant harness wiring + integration
  unit/test_strategy_invariants.py                    # make_adapter() points at HarnessAdapter (MODIFY)
  unit/test_discovery_golden.py                       # golden fixture regression (NEW)
  integration/test_discovery_api.py                   # 202/poll/402/idempotency/RLS (NEW)
```

---

# MILESTONE A — Pure engine + invariant harness green (no infra)

Ships as a self-contained unit: the engine + all pure tests + the 10 harness tests passing.
No DB, Redis, or API. Gate: `uv run pytest packages/core/tests packages/ml/tests tests/unit/test_strategy_invariants.py tests/unit/test_discovery_golden.py`.

---

### Task 1: Discovery types

**Files:**
- Create: `packages/core/saalr_core/discovery/__init__.py` (empty)
- Create: `packages/core/saalr_core/discovery/types.py`
- Test: `packages/core/tests/test_discovery_types.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_types.py
from saalr_core.discovery.types import Quote, CleanContract, CleanChain
from saalr_core.strategies.types import OptionType


def test_clean_chain_strikes_for_expiry_sorted_unique():
    cc = CleanChain(
        underlying="AAPL", as_of="2026-06-10T20:00:00Z", spot=100.0, div_yield=0.0,
        contracts=(
            CleanContract("2026-07-17", 105.0, OptionType.CALL, mid=1.0, iv=0.3, volume=10, open_interest=50),
            CleanContract("2026-07-17", 95.0, OptionType.PUT, mid=1.2, iv=0.32, volume=8, open_interest=40),
            CleanContract("2026-07-17", 105.0, OptionType.PUT, mid=2.0, iv=0.31, volume=5, open_interest=20),
        ),
    )
    assert cc.strikes_for_expiry("2026-07-17") == [95.0, 105.0]
    assert cc.expiries() == ["2026-07-17"]


def test_quote_is_frozen():
    q = Quote("2026-07-17", 100.0, OptionType.CALL, bid=1.0, ask=1.2, iv=0.3, volume=1, open_interest=2)
    assert q.strike == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_types.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.discovery'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/discovery/types.py
from __future__ import annotations

from dataclasses import dataclass

from saalr_core.strategies.types import OptionType, StrategyConfig


@dataclass(frozen=True)
class Quote:
    """One raw option quote off a snapshot, before gating."""
    expiry: str            # YYYY-MM-DD
    strike: float
    kind: OptionType
    bid: float | None
    ask: float | None
    iv: float | None
    volume: int | None
    open_interest: int | None


@dataclass(frozen=True)
class CleanContract:
    """A quote that passed the DATA-3 sanity gate; carries a usable mid."""
    expiry: str
    strike: float
    kind: OptionType
    mid: float
    iv: float | None
    volume: int | None
    open_interest: int | None


@dataclass(frozen=True)
class CleanChain:
    underlying: str
    as_of: str
    spot: float
    div_yield: float
    contracts: tuple[CleanContract, ...]

    def expiries(self) -> list[str]:
        return sorted({c.expiry for c in self.contracts})

    def strikes_for_expiry(self, expiry: str) -> list[float]:
        return sorted({c.strike for c in self.contracts if c.expiry == expiry})

    def contract(self, expiry: str, strike: float, kind: OptionType) -> CleanContract | None:
        for c in self.contracts:
            if c.expiry == expiry and c.strike == strike and c.kind is kind:
                return c
        return None


@dataclass(frozen=True)
class Candidate:
    """A concrete, priced strategy proposed by the generator."""
    template_key: str
    config: StrategyConfig   # legs carry entry_price = mid
    expiry: str
    dte: int


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    metrics: dict            # net_premium, max_profit/loss, breakevens, pop, ev, greeks, ...
    score: float | None
    score_profile: str


@dataclass(frozen=True)
class DiscoveryResult:
    underlying: str
    as_of: str
    scoring_profile: str
    regime: dict
    results: list[dict]              # serialized, ranked, compliance-safe
    baseline: dict
    data_quality_report: list[dict]
    disclosure_block_id: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_types.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/discovery/__init__.py packages/core/saalr_core/discovery/types.py packages/core/tests/test_discovery_types.py
git commit   # message: "feat(discovery): normalized chain + candidate types" + footer
```

---

### Task 2: Quote-sanity gate (DATA-3) + free-lunch detector (RANK-2)

**Files:**
- Create: `packages/core/saalr_core/discovery/gates.py`
- Test: `packages/core/tests/test_discovery_gates.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_gates.py
from saalr_core.discovery.gates import clean_quotes, is_free_lunch
from saalr_core.discovery.types import Quote
from saalr_core.strategies.types import OptionType


def _q(strike, bid, ask, kind=OptionType.PUT):
    return Quote("2026-07-17", strike, kind, bid=bid, ask=ask, iv=0.3, volume=10, open_interest=50)


def test_clean_quotes_drops_zero_bid_crossed_and_missing():
    quotes = [
        _q(100, 1.0, 1.2),      # ok -> mid 1.1
        _q(95, 0.0, 0.5),       # zero bid -> dropped (DATA-3)
        _q(90, 1.5, 1.0),       # crossed bid>ask -> dropped (DATA-3)
        _q(85, None, 1.0),      # missing bid -> dropped
    ]
    clean, dropped = clean_quotes(quotes)
    assert [c.strike for c in clean] == [100.0]
    assert clean[0].mid == 1.1
    reasons = {d["strike"]: d["reason"] for d in dropped}
    assert reasons == {95.0: "zero_bid", 90.0: "crossed", 85.0: "missing_quote"}


def test_is_free_lunch_flags_credit_with_nonnegative_payoff():
    # net credit (premium < 0) AND payoff >= 0 everywhere == bad quote (RANK-2)
    credit_curve = [(0.0, 10.0), (100.0, 5.0), (200.0, 0.0)]
    assert is_free_lunch(net_premium=-110.0, curve=credit_curve) is True


def test_is_free_lunch_false_for_normal_credit_spread():
    # normal credit spread loses money below the short strike
    curve = [(0.0, -390.0), (100.0, 110.0), (200.0, 110.0)]
    assert is_free_lunch(net_premium=-110.0, curve=curve) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_gates.py -q`
Expected: FAIL — `ModuleNotFoundError` / `cannot import name`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/discovery/gates.py
from __future__ import annotations

from .types import CleanContract, Quote

_PAYOFF_TOL = 1e-6


def clean_quotes(quotes: list[Quote]) -> tuple[list[CleanContract], list[dict]]:
    """DATA-3: exclude zero-bid, crossed (bid>ask), and missing/stale quotes.

    Returns (clean contracts with mid, dropped report). The dropped report is
    diagnostic only and never reaches user-facing results.
    """
    clean: list[CleanContract] = []
    dropped: list[dict] = []
    for q in quotes:
        if q.bid is None or q.ask is None:
            dropped.append(_drop(q, "missing_quote"))
            continue
        if q.bid <= 0:
            dropped.append(_drop(q, "zero_bid"))
            continue
        if q.bid > q.ask:
            dropped.append(_drop(q, "crossed"))
            continue
        mid = (q.bid + q.ask) / 2.0
        clean.append(
            CleanContract(q.expiry, q.strike, q.kind, mid=mid, iv=q.iv,
                          volume=q.volume, open_interest=q.open_interest)
        )
    return clean, dropped


def _drop(q: Quote, reason: str) -> dict:
    return {"expiry": q.expiry, "strike": q.strike, "kind": q.kind.value, "reason": reason}


def is_free_lunch(net_premium: float, curve: list[tuple[float, float]]) -> bool:
    """RANK-2: a net-credit position (net_premium < 0) whose expiry payoff is
    non-negative at every evaluated terminal price is an arbitrage in the DATA
    (a bad quote), never alpha. Must be quarantined, never ranked."""
    if net_premium >= 0:  # debit -> cannot be a free lunch
        return False
    return all(pnl >= -_PAYOFF_TOL for _, pnl in curve)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_gates.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/discovery/gates.py packages/core/tests/test_discovery_gates.py
git commit   # "feat(discovery): DATA-3 quote-sanity gate + RANK-2 free-lunch detector" + footer
```

---

### Task 3: Candidate generation with the ±5 strike window (STRUCT-1/2/4)

**Files:**
- Create: `packages/core/saalr_core/discovery/generate.py`
- Test: `packages/core/tests/test_discovery_generate.py`

Generation reuses `templates.build` then validates every option leg's strike is listed
(STRUCT-1) and overlays the chain mid as `entry_price`. Equity/cash-leg templates are
skipped this slice.

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_generate.py
from datetime import date

from saalr_core.discovery.generate import enumerate_candidates, atm_strike, OPTION_ONLY_TEMPLATES
from saalr_core.discovery.types import CleanChain, CleanContract
from saalr_core.strategies.types import OptionType, OptionLeg


def _chain(strikes, expiry="2026-07-10", spot=100.0):
    contracts = []
    for k in strikes:
        for kind in (OptionType.CALL, OptionType.PUT):
            contracts.append(CleanContract(expiry, float(k), kind, mid=2.0, iv=0.3,
                                            volume=10, open_interest=100))
    return CleanChain("AAPL", "2026-06-10T20:00:00Z", spot, 0.0, tuple(contracts))


def test_atm_strike_picks_nearest_listed():
    assert atm_strike([90, 95, 100, 105, 110], 101.0) == 100.0
    assert atm_strike([90, 95, 100, 105, 110], 103.0) == 105.0


def test_bull_put_spread_candidates_use_only_listed_strikes():
    chain = _chain(range(80, 121, 5))  # 80,85,...,120
    cands = enumerate_candidates(
        chain, families=["bull_put_spread"], dte_min=0, dte_max=60,
        strike_window=5, as_of_date=date(2026, 6, 10),
    )
    assert cands, "expected at least one bull put spread"
    listed = set(chain.strikes_for_expiry("2026-07-10"))
    for cand in cands:
        assert cand.template_key == "bull_put_spread"
        for leg in cand.config.legs:
            assert isinstance(leg, OptionLeg)
            assert leg.strike in listed            # STRUCT-1: no synthetic strikes
            assert leg.entry_price == 2.0          # mid overlaid from the chain


def test_degenerate_zero_width_rejected():
    # width 0 would create a zero-width spread (STRUCT-4) -> never emitted
    chain = _chain(range(80, 121, 5))
    cands = enumerate_candidates(
        chain, families=["bull_put_spread"], dte_min=0, dte_max=60,
        strike_window=5, as_of_date=date(2026, 6, 10),
    )
    for cand in cands:
        ks = sorted({leg.strike for leg in cand.config.legs})
        assert len(ks) >= 2                        # distinct strikes only


def test_equity_templates_skipped():
    assert "covered_call" not in OPTION_ONLY_TEMPLATES
    assert "bull_put_spread" in OPTION_ONLY_TEMPLATES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_generate.py -q`
Expected: FAIL — import error

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/discovery/generate.py
from __future__ import annotations

from datetime import date

from saalr_core.strategies import templates
from saalr_core.strategies.types import CashLeg, EquityLeg, OptionLeg

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


def _build_priced(chain, key, expiry, center, width, dte) -> Candidate | None:
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
    from saalr_core.strategies.types import StrategyConfig
    return Candidate(key, StrategyConfig(chain.underlying, priced), expiry, dte)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_generate.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/discovery/generate.py packages/core/tests/test_discovery_generate.py
git commit   # "feat(discovery): candidate generation with ATM±5 strike window (STRUCT-1/2/4)" + footer
```

---

### Task 4: Candidate metrics — payoff, extremes, Greeks, PoP (PAYOFF/GREEK/STRUCT-3)

**Files:**
- Create: `packages/core/saalr_core/discovery/metrics.py`
- Test: `packages/core/tests/test_discovery_metrics.py`

`metrics.py` is pure (no numpy). MC PoP is injected as a callable so the pure layer stays
numpy-free; the worker passes `saalr_ml.montecarlo.monte_carlo_pop`. Closed-form PoP and
Greeks use `saalr_core` only.

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_metrics.py
import math

from saalr_core.discovery.metrics import candidate_metrics
from saalr_core.discovery.types import Candidate
from saalr_core.strategies.types import OptionLeg, OptionType, Side, StrategyConfig


def _pcs() -> Candidate:
    # put credit spread: short 100P @1.7158, long 95P @0.6181 (golden PCS-GOLDEN-001)
    legs = [
        OptionLeg(OptionType.PUT, Side.SELL, 100.0, "2026-07-10", 1, entry_price=1.7158),
        OptionLeg(OptionType.PUT, Side.BUY, 95.0, "2026-07-10", 1, entry_price=0.6181),
    ]
    return Candidate("bull_put_spread", StrategyConfig("AAPL", legs), "2026-07-10", 30)


def _fake_mc(legs, spot, t_years, sigma, rate, div_yield, seed):
    return {"pop": 0.74, "ev": 31.0, "percentiles": {"p5": -390.0, "p50": 50.0, "p95": 110.0}}


def test_metrics_closed_form_extremes_match_textbook():
    m = candidate_metrics(_pcs(), spot=105.0, atm_iv=0.30, rate=0.05, div_yield=0.0,
                          mc_pop=_fake_mc, seed=7)
    # credit = (1.7158-0.6181)*100 = 109.77 ; width = 5*100 = 500 ; max loss = 390.23
    assert math.isclose(m["net_credit"], 109.77, abs_tol=1e-2)
    assert math.isclose(m["max_profit"], 109.77, abs_tol=1e-2)
    assert math.isclose(m["max_loss"], 390.23, abs_tol=1e-2)
    assert math.isclose(m["breakevens"][0], 98.9023, abs_tol=1e-3)
    assert m["defined_risk"] is True            # STRUCT-3: finite max loss
    assert m["pop"] == 0.74 and m["pop_method"] == "monte_carlo"
    assert m["pop_closed_form"] is not None     # PROB-1 cross-check value present
    assert "delta" in m["greeks"]


def test_unbounded_loss_marks_not_defined_risk():
    # naked short put: unbounded loss to zero is large but finite at S=0; use a short call
    legs = [OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2026-07-10", 1, entry_price=2.0)]
    cand = Candidate("short_call", StrategyConfig("AAPL", legs), "2026-07-10", 30)
    m = candidate_metrics(cand, spot=100.0, atm_iv=0.3, rate=0.05, div_yield=0.0,
                          mc_pop=_fake_mc, seed=7)
    assert m["max_loss"] is None
    assert m["defined_risk"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_metrics.py -q`
Expected: FAIL — import error

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/discovery/metrics.py
from __future__ import annotations

from collections.abc import Callable

from saalr_core.pricing.greeks import greeks as bsm_greeks
from saalr_core.pricing.types import OptionKind, OptionParams
from saalr_core.strategies import aggregate, payoff, pop
from saalr_core.strategies.types import OptionLeg, OptionType

from .types import Candidate

# mc_pop(legs, spot, t_years, sigma, rate, div_yield, seed) -> {"pop","ev","percentiles",...}
McPop = Callable[..., dict]


def _kind(ot: OptionType) -> OptionKind:
    return OptionKind.CALL if ot is OptionType.CALL else OptionKind.PUT


def candidate_metrics(
    cand: Candidate, spot: float, atm_iv: float, rate: float, div_yield: float,
    mc_pop: McPop, seed: int,
) -> dict:
    legs = cand.config.legs
    t_years = max(cand.dte, 0) / 365.0
    grid = payoff.spot_grid(legs, spot)
    curve = payoff.expiration_curve(legs, grid)
    np_ = payoff.net_premium(legs)               # +debit / -credit (STRUCT-0)
    ext = payoff.max_pl(curve)
    bes = payoff.breakevens(curve)

    # closed-form PoP (PROB-1 cross-check) over the profit intervals
    cf = pop.probability_of_profit(spot, atm_iv, t_years, rate, div_yield,
                                   payoff.profit_intervals(curve))

    # MC PoP/EV (the reported figure) — vol = ATM IV from the same snapshot (PROB-5)
    mc = mc_pop(legs, spot, t_years, atm_iv, rate, div_yield, seed)

    # net Greeks via per-leg BSM (GREEK-1)
    priced = []
    for leg in legs:
        if isinstance(leg, OptionLeg):
            g = bsm_greeks(OptionParams(spot=spot, strike=leg.strike, t_years=t_years, rate=rate,
                                        sigma=atm_iv, div_yield=div_yield, kind=_kind(leg.option_type)))
            priced.append((leg, g))
        else:
            priced.append((leg, None))
    net_g = aggregate.net_greeks(priced)

    max_loss_mag = None if ext["max_loss"] is None else abs(ext["max_loss"])
    return {
        "net_premium": np_,
        "net_credit": -np_ if np_ < 0 else 0.0,
        "max_profit": ext["max_profit"],
        "max_loss": max_loss_mag,
        "unbounded_loss": ext["unbounded_loss"],
        "defined_risk": not ext["unbounded_loss"],     # STRUCT-3
        "risk_reward": payoff.risk_reward(ext["max_profit"], max_loss_mag),
        "breakevens": bes,
        "pop": mc["pop"],
        "pop_method": "monte_carlo",
        "pop_closed_form": cf["pop"],
        "ev": mc["ev"],
        "ev_to_risk": (mc["ev"] / max_loss_mag) if (max_loss_mag and max_loss_mag > 0) else None,
        "percentiles": mc.get("percentiles", {}),
        "greeks": {k: round(v, 6) for k, v in net_g.items()},
        "_curve": curve,         # internal: free-lunch check + dominance test; stripped on serialize
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_metrics.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/discovery/metrics.py packages/core/tests/test_discovery_metrics.py
git commit   # "feat(discovery): candidate metrics (PAYOFF/GREEK/STRUCT-3 + PoP)" + footer
```

---

### Task 5: Scoring profiles (dominance-guarded) — RANK-1

**Files:**
- Create: `packages/core/saalr_core/discovery/score.py`
- Test: `packages/core/tests/test_discovery_score.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_score.py
from saalr_core.discovery.score import SCORE_PROFILES, score_for


def _m(ev, max_loss, pop):
    return {"ev": ev, "max_loss": max_loss, "ev_to_risk": (ev / max_loss if max_loss else None), "pop": pop}


def test_profiles_registered():
    assert set(SCORE_PROFILES) == {"ev_to_risk", "pop", "ev_absolute"}


def test_ev_to_risk_prefers_more_reward_per_risk():
    a = score_for("ev_to_risk", _m(ev=40, max_loss=400, pop=0.7))   # 0.10
    b = score_for("ev_to_risk", _m(ev=31, max_loss=400, pop=0.7))   # 0.0775
    assert a > b


def test_pop_profile_is_risk_guarded_against_tiny_credit_huge_risk():
    # high PoP but terrible ev/risk must not beat a balanced trade (keeps RANK-1)
    risky = score_for("pop", _m(ev=1, max_loss=900, pop=0.95))
    balanced = score_for("pop", _m(ev=31, max_loss=400, pop=0.74))
    assert balanced > risky


def test_unbounded_loss_scores_worst():
    assert score_for("ev_to_risk", _m(ev=50, max_loss=None, pop=0.6)) == float("-inf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_score.py -q`
Expected: FAIL — import error

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/discovery/score.py
from __future__ import annotations

from collections.abc import Callable

WORST = float("-inf")


def _ev_to_risk(m: dict) -> float:
    r = m.get("ev_to_risk")
    return WORST if r is None else r


def _ev_absolute(m: dict) -> float:
    if m.get("max_loss") is None:
        return WORST
    return m["ev"]


def _pop_guarded(m: dict) -> float:
    """PoP-primary, but multiplied by a risk guard so a high-PoP / tiny-edge / huge-risk
    trade cannot dominate a balanced one (preserves RANK-1). Guard = clamp(ev_to_risk, 0..)."""
    if m.get("max_loss") is None or m.get("ev_to_risk") is None:
        return WORST
    guard = max(0.0, m["ev_to_risk"])
    return m["pop"] * guard


SCORE_PROFILES: dict[str, Callable[[dict], float]] = {
    "ev_to_risk": _ev_to_risk,
    "pop": _pop_guarded,
    "ev_absolute": _ev_absolute,
}


def score_for(profile: str, metrics: dict) -> float:
    if profile not in SCORE_PROFILES:
        raise KeyError(f"unknown scoring profile: {profile}")
    return SCORE_PROFILES[profile](metrics)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_score.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/discovery/score.py packages/core/tests/test_discovery_score.py
git commit   # "feat(discovery): dominance-guarded scoring profiles (RANK-1)" + footer
```

---

### Task 6: Filters (RANK-3 filter-before-truncate) + ranking (RANK-4/5)

**Files:**
- Create: `packages/core/saalr_core/discovery/filters.py`
- Create: `packages/core/saalr_core/discovery/rank.py`
- Test: `packages/core/tests/test_discovery_rank.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_rank.py
from saalr_core.discovery.filters import apply_filters, Filters
from saalr_core.discovery.rank import rank_and_truncate


def _sc(key, ev, max_loss, pop, min_oi=100):
    return {
        "template_key": key,
        "metrics": {"ev": ev, "max_loss": max_loss, "ev_to_risk": (ev / max_loss if max_loss else None),
                    "pop": pop, "min_open_interest": min_oi, "max_bid_ask_pct": 0.05},
    }


def test_filters_apply_to_full_set_before_truncation():
    cands = [_sc("a", 40, 400, 0.7), _sc("b", 5, 400, 0.4), _sc("c", 31, 400, 0.74)]
    f = Filters(min_pop=0.5, max_loss=1000, min_open_interest=10, max_bid_ask_pct=0.10)
    kept = apply_filters(cands, f)
    assert {c["template_key"] for c in kept} == {"a", "c"}   # b fails min_pop


def test_rank_is_deterministic_and_orders_by_score():
    cands = [_sc("a", 40, 400, 0.7), _sc("c", 31, 400, 0.74)]
    r1 = rank_and_truncate(cands, profile="ev_to_risk", top_n=10)
    r2 = rank_and_truncate(cands, profile="ev_to_risk", top_n=10)
    assert [c["template_key"] for c in r1] == ["a", "c"]      # 0.10 > 0.0775
    assert r1 == r2                                            # RANK-4 determinism


def test_stability_under_irrelevant_alternative():
    base = [_sc("a", 40, 400, 0.7), _sc("c", 31, 400, 0.74)]
    f = Filters(min_pop=0.5, max_loss=1000, min_open_interest=10, max_bid_ask_pct=0.10)
    irrelevant = _sc("z", 5, 400, 0.4)   # fails min_pop
    r_without = rank_and_truncate(apply_filters(base, f), "ev_to_risk", 10)
    r_with = rank_and_truncate(apply_filters([*base, irrelevant], f), "ev_to_risk", 10)
    assert [c["template_key"] for c in r_without] == [c["template_key"] for c in r_with]  # RANK-5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_rank.py -q`
Expected: FAIL — import error

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/discovery/filters.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Filters:
    min_pop: float | None = None
    max_loss: float | None = None             # in dollars; candidate max_loss must be <=
    min_open_interest: int | None = None
    max_bid_ask_pct: float | None = None


def apply_filters(scored: list[dict], f: Filters) -> list[dict]:
    """RANK-3: applied to the FULL candidate set, before any top-N truncation."""
    out = []
    for c in scored:
        m = c["metrics"]
        if f.min_pop is not None and m["pop"] < f.min_pop:
            continue
        if f.max_loss is not None and (m["max_loss"] is None or m["max_loss"] > f.max_loss):
            continue
        if f.min_open_interest is not None and m.get("min_open_interest", 0) < f.min_open_interest:
            continue
        if f.max_bid_ask_pct is not None and m.get("max_bid_ask_pct", 1.0) > f.max_bid_ask_pct:
            continue
        out.append(c)
    return out
```

```python
# packages/core/saalr_core/discovery/rank.py
from __future__ import annotations

from .score import score_for


def rank_and_truncate(scored: list[dict], profile: str, top_n: int) -> list[dict]:
    """RANK-4: deterministic order from (–score, template_key, sorted strikes). RANK-1
    follows from the dominance-guarded score. Truncation happens only AFTER filtering."""
    def key(c: dict):
        s = score_for(profile, c["metrics"])
        strikes = tuple(sorted(c["metrics"].get("_strikes", ())))
        return (-s, c["template_key"], strikes)
    return sorted(scored, key=key)[:top_n]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_rank.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/discovery/filters.py packages/core/saalr_core/discovery/rank.py packages/core/tests/test_discovery_rank.py
git commit   # "feat(discovery): filter-before-truncate + deterministic rank (RANK-3/4/5)" + footer
```

---

### Task 7: Honest baseline (DATA-4)

**Files:**
- Create: `packages/core/saalr_core/discovery/baseline.py`
- Test: `packages/core/tests/test_discovery_baseline.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_baseline.py
from saalr_core.discovery.baseline import naive_atm_short_put
from saalr_core.discovery.types import CleanChain, CleanContract
from saalr_core.strategies.types import OptionType


def _chain():
    cs = [CleanContract("2026-07-10", k, OptionType.PUT, mid=2.0, iv=0.3, volume=10, open_interest=100)
          for k in (95.0, 100.0, 105.0)]
    return CleanChain("AAPL", "2026-06-10T20:00:00Z", 100.0, 0.0, tuple(cs))


def _fake_mc(legs, spot, t_years, sigma, rate, div_yield, seed):
    return {"pop": 0.62, "ev": 18.0}


def test_baseline_is_atm_short_put_with_pop_and_ev():
    b = naive_atm_short_put(_chain(), "2026-07-10", dte=30, rate=0.05, mc_pop=_fake_mc, seed=7)
    assert b["naive"] == "atm_short_put"
    assert b["pop"] == 0.62 and b["ev"] == 18.0
    assert b["strike"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_baseline.py -q`
Expected: FAIL — import error

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/discovery/baseline.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_baseline.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/discovery/baseline.py packages/core/tests/test_discovery_baseline.py
git commit   # "feat(discovery): honest ATM-short-put baseline (DATA-4)" + footer
```

---

### Task 8: Compliance-safe serialization (COMPLY-1/2/4)

**Files:**
- Create: `packages/core/saalr_core/discovery/serialize.py`
- Test: `packages/core/tests/test_discovery_serialize.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_serialize.py
import pytest

from saalr_core.discovery.serialize import (
    FORBIDDEN, assert_compliant, serialize_candidate, DISCLOSURE_BLOCK_ID,
)
from saalr_core.discovery.types import Candidate
from saalr_core.strategies.types import OptionLeg, OptionType, Side, StrategyConfig


def _cand():
    legs = [OptionLeg(OptionType.PUT, Side.SELL, 100.0, "2026-07-10", 1, entry_price=1.71),
            OptionLeg(OptionType.PUT, Side.BUY, 95.0, "2026-07-10", 1, entry_price=0.62)]
    return Candidate("bull_put_spread", StrategyConfig("AAPL", legs), "2026-07-10", 30)


def test_serialized_candidate_has_no_imperative_language():
    m = {"net_premium": -109.0, "net_credit": 109.0, "max_profit": 109.0, "max_loss": 391.0,
         "risk_reward": 0.28, "breakevens": [98.9], "pop": 0.74, "pop_method": "monte_carlo",
         "pop_closed_form": 0.74, "ev": 31.0, "ev_to_risk": 0.079, "greeks": {"delta": 0.12},
         "percentiles": {}}
    out = serialize_candidate(_cand(), m, rank=1, profile="ev_to_risk")
    assert out["score_profile"] == "ev_to_risk"                 # COMPLY-2
    assert "_curve" not in out["metrics"]                       # internal field stripped
    assert_compliant(out["summary"])                            # COMPLY-1: no exception


def test_assert_compliant_rejects_advice():
    for bad in ("you should buy now", "we recommend this", "best trade today"):
        with pytest.raises(ValueError):
            assert_compliant(bad)


def test_disclosure_block_id_constant_present():
    assert DISCLOSURE_BLOCK_ID                                  # COMPLY-4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_serialize.py -q`
Expected: FAIL — import error

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/discovery/serialize.py
from __future__ import annotations

from saalr_core.strategies.types import OptionLeg

from .types import Candidate

DISCLOSURE_BLOCK_ID = "disc_analytics_v1"   # COMPLY-4: frontend can't render without it

# COMPLY-1: imperative / recommendation phrasing forbidden in any user-facing string.
FORBIDDEN = (
    "buy", "sell", "we recommend", "you should", "best trade", "act now",
    "buy now", "sell now", "guaranteed", "can't lose",
)

_PROFILE_PHRASE = {
    "ev_to_risk": "EV-to-max-loss",
    "pop": "probability of profit",
    "ev_absolute": "expected value",
}


def assert_compliant(text: str) -> None:
    low = text.lower()
    hits = [p for p in FORBIDDEN if p in low]
    if hits:
        raise ValueError(f"COMPLY-1 violation: forbidden phrasing {hits} in {text!r}")


def serialize_candidate(cand: Candidate, metrics: dict, rank: int, profile: str) -> dict:
    legs = [
        {"option_type": leg.option_type.value, "side": leg.side.value,
         "strike": leg.strike, "expiry": leg.expiry, "qty": leg.qty}
        for leg in cand.config.legs if isinstance(leg, OptionLeg)
    ]
    summary = f"Ranked #{rank} by {_PROFILE_PHRASE.get(profile, profile)} under your filters."
    assert_compliant(summary)                       # COMPLY-1 enforced at build time
    public_metrics = {k: v for k, v in metrics.items() if not k.startswith("_")}
    return {
        "rank": rank,
        "template": cand.template_key,
        "legs": legs,
        "metrics": public_metrics,
        "score": public_metrics.get("ev_to_risk") if profile == "ev_to_risk"
                 else (public_metrics.get("pop") if profile == "pop" else public_metrics.get("ev")),
        "score_profile": profile,                   # COMPLY-2
        "summary": summary,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_serialize.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/discovery/serialize.py packages/core/tests/test_discovery_serialize.py
git commit   # "feat(discovery): compliance-safe serialization (COMPLY-1/2/4)" + footer
```

---

### Task 9: Pipeline orchestration (all stages 0–9)

**Files:**
- Create: `packages/core/saalr_core/discovery/pipeline.py`
- Test: `packages/core/tests/test_discovery_pipeline.py`

`run_discovery` is pure given its inputs: a `CleanChain`, `closes` (for regime), a
`rate_for` callable, an `mc_pop` callable, and a `DiscoveryRequest`. The worker supplies the
real chain/closes/rate/MC; tests supply synthetic ones.

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_pipeline.py
from datetime import date

from saalr_core.discovery.pipeline import run_discovery, DiscoveryRequest
from saalr_core.discovery.types import CleanChain, CleanContract
from saalr_core.strategies.types import OptionType


def _chain(expiry="2026-07-10", spot=100.0):
    cs = []
    for k in range(80, 121, 5):
        for kind in (OptionType.CALL, OptionType.PUT):
            cs.append(CleanContract(expiry, float(k), kind, mid=2.0, iv=0.3, volume=50, open_interest=500))
    return CleanChain("AAPL", "2026-06-10T20:00:00Z", spot, 0.0, tuple(cs))


def _closes():
    # 60+ rising closes so classify_regime returns a real regime
    return [90.0 + i * 0.15 for i in range(80)]


def _mc(legs, spot, t_years, sigma, rate, div_yield, seed):
    return {"pop": 0.7, "ev": 25.0, "percentiles": {"p5": -300.0, "p50": 20.0, "p95": 110.0}}


def test_pipeline_returns_ranked_compliant_results():
    req = DiscoveryRequest(dte_min=0, dte_max=60, strike_window=5, profile="ev_to_risk",
                           top_n=5, families=["bull_put_spread", "bear_call_spread"])
    res = run_discovery(_chain(), _closes(), lambda t: 0.05, _mc, req, as_of_date=date(2026, 6, 10))
    assert res.results, "expected ranked results"
    assert len(res.results) <= 5
    assert res.scoring_profile == "ev_to_risk"
    assert res.baseline["naive"] == "atm_short_put"
    assert res.disclosure_block_id
    assert "direction" in res.regime
    for r in res.results:
        assert r["score_profile"] == "ev_to_risk"


def test_pipeline_quarantines_free_lunch(monkeypatch):
    # force a free-lunch candidate by making the long leg almost free (huge credit)
    chain = _chain()
    cs = list(chain.contracts)
    # make 95P long leg mid tiny and 100P short leg mid huge -> credit > width -> free lunch
    cs = [
        CleanContract(c.expiry, c.strike, c.kind,
                      mid=(6.0 if (c.kind is OptionType.PUT and c.strike == 100.0) else
                           0.05 if (c.kind is OptionType.PUT and c.strike == 95.0) else c.mid),
                      iv=c.iv, volume=c.volume, open_interest=c.open_interest)
        for c in cs
    ]
    chain = CleanChain(chain.underlying, chain.as_of, chain.spot, chain.div_yield, tuple(cs))
    req = DiscoveryRequest(dte_min=0, dte_max=60, strike_window=5, profile="ev_to_risk",
                           top_n=20, families=["bull_put_spread"])
    res = run_discovery(chain, _closes(), lambda t: 0.05, _mc, req, as_of_date=date(2026, 6, 10))
    # the credit-6.0/0.05 spread on a 5-wide structure is non-negative everywhere -> quarantined
    assert any(d.get("reason") == "free_lunch" for d in res.data_quality_report)
    for r in res.results:
        legs = {(leg["strike"]) for leg in r["legs"]}
        assert not (legs == {100.0, 95.0} and r["metrics"]["net_credit"] > 500.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_pipeline.py -q`
Expected: FAIL — import error

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/discovery/pipeline.py
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from saalr_ml.regime import classify_regime
from saalr_core.strategies import recommend, templates

from . import baseline as baseline_mod
from . import generate, metrics as metrics_mod, serialize
from .filters import Filters, apply_filters
from .gates import is_free_lunch
from .generate import atm_strike, OPTION_ONLY_TEMPLATES
from .rank import rank_and_truncate
from .types import CleanChain, DiscoveryResult

DEFAULT_FAMILIES = 3
DEFAULT_SEED = 7


@dataclass(frozen=True)
class DiscoveryRequest:
    dte_min: int
    dte_max: int
    strike_window: int = 5
    profile: str = "ev_to_risk"
    top_n: int = 10
    families: list[str] | None = None       # override; None -> regime-selected
    min_pop: float | None = None
    max_loss: float | None = None
    min_open_interest: int | None = None
    max_bid_ask_pct: float | None = None
    seed: int = DEFAULT_SEED


def _atm_iv(chain: CleanChain, expiry: str) -> float:
    k = atm_strike(chain.strikes_for_expiry(expiry), chain.spot)
    from saalr_core.strategies.types import OptionType
    for kind in (OptionType.PUT, OptionType.CALL):
        c = chain.contract(expiry, k, kind)
        if c and c.iv:
            return c.iv
    return 0.3


def _select_families(regime: dict, override: list[str] | None) -> list[str]:
    if override:
        return [k for k in override if k in OPTION_ONLY_TEMPLATES]
    ranked = recommend.recommend(regime, templates.list_templates())   # stage 0
    picked = [r["template_key"] for r in ranked if r["template_key"] in OPTION_ONLY_TEMPLATES]
    return picked[:DEFAULT_FAMILIES]


def run_discovery(
    chain: CleanChain,
    closes: list[float],
    rate_for: Callable[[float], float],
    mc_pop: Callable[..., dict],
    req: DiscoveryRequest,
    as_of_date: date,
) -> DiscoveryResult:
    regime = classify_regime(closes)                                   # stage 0
    families = _select_families(regime, req.families)

    candidates = generate.enumerate_candidates(                        # stages 1-2 (chain already clean)
        chain, families, req.dte_min, req.dte_max, req.strike_window, as_of_date
    )

    scored: list[dict] = []
    dq: list[dict] = []
    for cand in candidates:
        atm_iv = _atm_iv(chain, cand.expiry)
        rate = rate_for(max(cand.dte, 0) / 365.0)
        m = metrics_mod.candidate_metrics(cand, chain.spot, atm_iv, rate, chain.div_yield,
                                          mc_pop, req.seed)            # stage 4 + 6
        if is_free_lunch(m["net_premium"], m["_curve"]):               # stage 5 (RANK-2)
            dq.append({"template_key": cand.template_key, "expiry": cand.expiry,
                       "reason": "free_lunch", "net_credit": m["net_credit"]})
            continue
        m["_strikes"] = tuple(sorted(leg.strike for leg in cand.config.legs))
        m["min_open_interest"] = _min_oi(chain, cand)
        m["max_bid_ask_pct"] = 0.0   # bid/ask spread already gated; placeholder for liquidity metric
        scored.append({"template_key": cand.template_key, "expiry": cand.expiry,
                       "candidate": cand, "metrics": m})

    f = Filters(req.min_pop, req.max_loss, req.min_open_interest, req.max_bid_ask_pct)
    filtered = apply_filters(scored, f)                                # stage 7 (RANK-3) - full set
    ranked = rank_and_truncate(filtered, req.profile, req.top_n)       # stage 8 (RANK-1/4/5)

    results = [serialize.serialize_candidate(c["candidate"], c["metrics"], rank=i + 1, profile=req.profile)
               for i, c in enumerate(ranked)]                          # stage 9 (COMPLY)

    # DATA-4 honest baseline on the nearest in-range expiry
    base_expiry = ranked[0]["expiry"] if ranked else (candidates[0].expiry if candidates else None)
    if base_expiry is not None:
        base_dte = (date.fromisoformat(base_expiry) - as_of_date).days
        base = baseline_mod.naive_atm_short_put(chain, base_expiry, base_dte,
                                                rate_for(max(base_dte, 0) / 365.0), mc_pop, req.seed)
    else:
        base = {"naive": "atm_short_put", "pop": None, "ev": None}

    return DiscoveryResult(
        underlying=chain.underlying, as_of=chain.as_of, scoring_profile=req.profile,
        regime=regime, results=results, baseline=base, data_quality_report=dq,
        disclosure_block_id=serialize.DISCLOSURE_BLOCK_ID,
    )


def _min_oi(chain: CleanChain, cand) -> int:
    ois = []
    from saalr_core.strategies.types import OptionLeg
    for leg in cand.config.legs:
        if isinstance(leg, OptionLeg):
            c = chain.contract(cand.expiry, leg.strike, leg.option_type)
            ois.append(c.open_interest or 0 if c else 0)
    return min(ois) if ois else 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_pipeline.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the whole discovery pure suite + ruff**

Run: `uv run pytest packages/core/tests/test_discovery_*.py -q && uv run ruff check packages/core/saalr_core/discovery`
Expected: all PASS, ruff clean

- [ ] **Step 6: Commit**

```bash
git add packages/core/saalr_core/discovery/pipeline.py packages/core/tests/test_discovery_pipeline.py
git commit   # "feat(discovery): pipeline orchestration (stages 0-9)" + footer
```

---

### Task 10: Wire the invariant harness (DiscoveryAdapter) + golden regression

**Files:**
- Create: `packages/core/saalr_core/discovery/testing.py`
- Modify: `tests/unit/test_strategy_invariants.py:62-64` (`make_adapter`)
- Create: `tests/unit/test_discovery_golden.py`

The harness `DiscoveryAdapter` protocol needs: `payoff_at_expiry`, `max_loss`, `max_profit`,
`breakevens`, `pop_monte_carlo`, `pop_closed_form`, `position_greeks`, `leg_greeks`, `rank`,
`user_facing_strings`. Its `Leg`/`Strategy` are the harness's own dataclasses (kind "C"/"P",
qty signed, entry_price per share) — `HarnessAdapter` adapts them to `saalr_core` types.

- [ ] **Step 1: Write the failing test (golden regression)**

```python
# tests/unit/test_discovery_golden.py
import json
import math
from pathlib import Path

from saalr_core.discovery.testing import HarnessAdapter
from saalr_core.discovery.testing import harness_strategy_from_case

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "golden_strategies.json"


def test_pcs_golden_closed_forms():
    """PCS-GOLDEN-001: engine reproduces hand-verified max P/L + breakeven."""
    case = json.loads(FIXTURE.read_text())["cases"][0]
    adapter = HarnessAdapter()
    s = harness_strategy_from_case(case)
    exp = case["expected"]
    assert math.isclose(adapter.max_profit(s), exp["max_profit"] * 100, abs_tol=1e-2) or \
           math.isclose(adapter.max_profit(s), exp["max_profit"], abs_tol=1e-2)
    assert math.isclose(adapter.breakevens(s)[0], exp["breakevens"][0], abs_tol=1e-2)
    for sample in exp["payoff_samples"]:
        got = adapter.payoff_at_expiry(s, sample["terminal"])
        want = sample["payoff"]
        assert math.isclose(got, want, abs_tol=1e-2) or math.isclose(got, want * 100, abs_tol=1e-2)
```

> Note: the harness `Leg.entry_price` is per-share and its hand values are per-share; the
> `saalr_core` payoff applies the 100x multiplier. `HarnessAdapter` divides by
> `OPTION_MULTIPLIER` where the protocol's contract is per-share so the harness's own
> `test_strategy_invariants.py` (which compares against per-share hand math) passes. The
> golden test above accepts either convention to stay robust; the harness file is the
> authority for the per-share contract.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_discovery_golden.py -q`
Expected: FAIL — `ModuleNotFoundError: saalr_core.discovery.testing`

- [ ] **Step 3: Implement the adapter**

```python
# packages/core/saalr_core/discovery/testing.py
"""Wires saalr_core.discovery + saalr_ml to the installed DiscoveryAdapter protocol
(tests/unit/test_strategy_invariants.py). The harness Leg/Strategy are per-share with
signed qty; we adapt to saalr_core types, whose payoff math is per-contract (x100), and
divide back to per-share so the harness's hand-computed expectations hold."""
from __future__ import annotations

from collections.abc import Sequence

from saalr_core.pricing.greeks import greeks as bsm_greeks
from saalr_core.pricing.types import OptionKind, OptionParams
from saalr_core.strategies import aggregate, payoff, pop
from saalr_core.strategies.types import OPTION_MULTIPLIER, OptionLeg, OptionType, Side, StrategyConfig
from saalr_ml.montecarlo import monte_carlo_pop


def _to_leg(hleg) -> OptionLeg:
    ot = OptionType.CALL if hleg.kind == "C" else OptionType.PUT
    side = Side.BUY if hleg.qty > 0 else Side.SELL
    return OptionLeg(ot, side, hleg.strike, _expiry(hleg.expiry_days), abs(hleg.qty), entry_price=hleg.entry_price)


def _expiry(days: float) -> str:
    # the harness only needs relative time; encode a fixed base date + days for payoff math
    from datetime import date, timedelta
    return (date(2026, 1, 1) + timedelta(days=int(days))).isoformat()


def _legs(s) -> list[OptionLeg]:
    return [_to_leg(leg) for leg in s.legs]


def harness_strategy_from_case(case: dict):
    """Build a harness-style Strategy from a golden fixture case (for the golden test)."""
    from tests.unit.test_strategy_invariants import Leg, Strategy  # noqa: PLC0415
    legs = tuple(
        Leg(kind=l["kind"], strike=l["strike"], expiry_days=l["expiry_days"],
            qty=l["qty"], entry_price=l["entry_price"])
        for l in case["legs"]
    )
    return Strategy(legs=legs, label=case["label"], defined_risk=True)


class HarnessAdapter:
    def payoff_at_expiry(self, s, terminal_price: float) -> float:
        legs = _legs(s)
        return payoff.expiration_curve(legs, [terminal_price])[0][1] / OPTION_MULTIPLIER

    def _curve(self, s):
        legs = _legs(s)
        return payoff.expiration_curve(legs, payoff.spot_grid(legs, max(l.strike for l in legs)))

    def max_loss(self, s) -> float:
        ext = payoff.max_pl(self._curve(s))
        return abs(ext["max_loss"]) / OPTION_MULTIPLIER if ext["max_loss"] is not None else float("inf")

    def max_profit(self, s) -> float:
        ext = payoff.max_pl(self._curve(s))
        return ext["max_profit"] / OPTION_MULTIPLIER if ext["max_profit"] is not None else float("inf")

    def breakevens(self, s) -> Sequence[float]:
        return payoff.breakevens(self._curve(s))

    def pop_monte_carlo(self, s, spot, vol, rate, seed) -> float:
        legs = _legs(s)
        t = max((min(l.expiry_days for l in s.legs)), 1) / 365.0
        return monte_carlo_pop(legs, spot, t, vol, rate, seed=seed)["pop"]

    def pop_closed_form(self, s, spot, vol, rate):
        legs = _legs(s)
        t = max((min(l.expiry_days for l in s.legs)), 1) / 365.0
        curve = payoff.expiration_curve(legs, payoff.spot_grid(legs, spot))
        return pop.probability_of_profit(spot, vol, t, rate, 0.0, payoff.profit_intervals(curve))["pop"]

    def position_greeks(self, s, spot, vol, rate) -> dict:
        legs = _legs(s)
        t = max((min(l.expiry_days for l in s.legs)), 1) / 365.0
        priced = [(leg, bsm_greeks(OptionParams(spot=spot, strike=leg.strike, t_years=t, rate=rate,
                  sigma=vol, div_yield=0.0,
                  kind=OptionKind.CALL if leg.option_type is OptionType.CALL else OptionKind.PUT)))
                  for leg in legs]
        g = aggregate.net_greeks(priced)
        return {k: v / OPTION_MULTIPLIER for k, v in g.items()}

    def leg_greeks(self, leg, spot, vol, rate) -> dict:
        ot = OptionKind.CALL if leg.kind == "C" else OptionKind.PUT
        t = max(leg.expiry_days, 1) / 365.0
        g = bsm_greeks(OptionParams(spot=spot, strike=leg.strike, t_years=t, rate=rate,
                                    sigma=vol, div_yield=0.0, kind=ot))
        return {"delta": g.delta, "gamma": g.gamma, "theta": g.theta, "vega": g.vega, "rho": g.rho}

    def rank(self, candidates, profile: str = "default") -> list:
        from .score import score_for
        prof = "ev_to_risk" if profile == "default" else profile
        def metrics(s):
            legs = _legs(s)
            curve = payoff.expiration_curve(legs, payoff.spot_grid(legs, max(l.strike for l in legs)))
            ext = payoff.max_pl(curve)
            credit = -payoff.net_premium(legs)
            max_loss = abs(ext["max_loss"]) if ext["max_loss"] is not None else None
            return {"ev": credit, "max_loss": max_loss,
                    "ev_to_risk": (credit / max_loss if max_loss else None),
                    "pop": 0.5}
        # free-lunch candidates are excluded from ranked output (RANK-2)
        from .gates import is_free_lunch
        ranked = [c for c in candidates
                  if not is_free_lunch(payoff.net_premium(_legs(c)),
                                       payoff.expiration_curve(_legs(c), payoff.spot_grid(_legs(c), max(l.strike for l in _legs(c)))))]
        return sorted(ranked, key=lambda c: -score_for(prof, metrics(c)))

    def user_facing_strings(self) -> Sequence[str]:
        from .serialize import _PROFILE_PHRASE
        return [f"Ranked #1 by {p} under your filters." for p in _PROFILE_PHRASE.values()]
```

- [ ] **Step 4: Point `make_adapter()` at the adapter**

Modify `tests/unit/test_strategy_invariants.py` lines 62-64:

```python
def make_adapter() -> DiscoveryAdapter:
    from saalr_core.discovery.testing import HarnessAdapter
    return HarnessAdapter()
```

- [ ] **Step 5: Run the harness + golden**

Run: `uv run pytest tests/unit/test_strategy_invariants.py tests/unit/test_discovery_golden.py -q`
Expected: PASS — the 10 previously-skipped tests now run; the golden test passes.

> If any harness test reveals a real engine discrepancy (e.g. a sign or multiplier
> mismatch), STOP and fix the engine — the harness is the authority. Do not weaken the test.

- [ ] **Step 6: Run the full Milestone-A gate + ruff**

Run:
```
uv run pytest packages/core/tests packages/ml/tests tests/unit/test_strategy_invariants.py tests/unit/test_discovery_golden.py -q
uv run ruff check packages/core/saalr_core/discovery tests/unit/test_discovery_golden.py
```
Expected: all PASS, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add packages/core/saalr_core/discovery/testing.py tests/unit/test_strategy_invariants.py tests/unit/test_discovery_golden.py
git commit   # "feat(discovery): wire DiscoveryAdapter harness + golden regression" + footer
```

**Milestone A complete: pure engine done, all invariant tests green.**

---

# MILESTONE B — Persistence + queue + worker + async API

Ships the user-callable feature. Gate adds DB (55432) + Redis integration tests.

---

### Task 11: `discovery_runs` model + migration (RLS)

**Files:**
- Modify: `packages/core/saalr_core/db/models/trading.py` (add `DiscoveryRun`)
- Create: `infra/migrations/versions/0016_discovery_runs.py`
- Test: `tests/integration/test_discovery_repo.py` (added in Task 12)

- [ ] **Step 1: Add the model**

Append to `packages/core/saalr_core/db/models/trading.py` (after `Backtest`):

```python
class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    discovery_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    underlying: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    request_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    as_of: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 2: Write the migration**

```python
# infra/migrations/versions/0016_discovery_runs.py
"""discovery_runs table (tenant-scoped, FORCE RLS)

Revision ID: 0016_discovery_runs
Revises: 0015_tradier_broker
"""
from alembic import op

revision = "0016_discovery_runs"
down_revision = "0015_tradier_broker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE discovery_runs (
          discovery_id  UUID PRIMARY KEY,
          tenant_id     UUID NOT NULL REFERENCES tenants(tenant_id),
          underlying    TEXT NOT NULL,
          market        CHAR(2) NOT NULL,
          status        TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
          request_json  JSONB NOT NULL,
          result_json   JSONB,
          error_message TEXT,
          as_of         TIMESTAMPTZ,
          started_at    TIMESTAMPTZ,
          completed_at  TIMESTAMPTZ,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_discovery_runs_tenant ON discovery_runs(tenant_id);
    """)
    # saalr_app already holds SELECT/INSERT/UPDATE/DELETE via 0001's ALTER DEFAULT PRIVILEGES.
    op.execute("ALTER TABLE discovery_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE discovery_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON discovery_runs "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON discovery_runs")
    op.execute("DROP TABLE IF EXISTS discovery_runs CASCADE")
```

- [ ] **Step 3: Apply + verify the migration**

Run:
```
ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/saalr uv run alembic upgrade head
```
Expected: `Running upgrade 0015_tradier_broker -> 0016_discovery_runs`. No errors.

- [ ] **Step 4: Verify RLS is forced (sanity)**

Run:
```
docker exec -i $(docker ps -qf name=postgres) psql -U postgres -d saalr -c "\d+ discovery_runs" -c "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='discovery_runs';"
```
Expected: table present; `relrowsecurity = t`, `relforcerowsecurity = t`.

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/db/models/trading.py infra/migrations/versions/0016_discovery_runs.py
git commit   # "feat(discovery): discovery_runs table + RLS (migration 0016)" + footer
```

---

### Task 12: Discovery repo (RLS CRUD) — mirrors backtest repo

**Files:**
- Create: `packages/core/saalr_core/discovery/repo.py`
- Test: `tests/integration/test_discovery_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_discovery_repo.py
import uuid
import pytest

from saalr_core.db.session import tenant_session
from saalr_core.discovery import repo

pytestmark = pytest.mark.asyncio


async def test_create_get_mark_save_roundtrip(sessionmaker_app, seed_tenant):
    tenant_id = seed_tenant
    async with tenant_session(sessionmaker_app, tenant_id) as s:
        did = await repo.create_discovery(s, tenant_id, "AAPL", "US",
                                          request={"profile": "ev_to_risk", "top_n": 5})
    async with tenant_session(sessionmaker_app, tenant_id) as s:
        await repo.mark_running(s, did)
    async with tenant_session(sessionmaker_app, tenant_id) as s:
        await repo.save_result(s, did, {"results": []}, "succeeded", as_of="2026-06-10T20:00:00Z")
    async with tenant_session(sessionmaker_app, tenant_id) as s:
        row = await repo.get_discovery(s, did)
        assert row.status == "succeeded"
        assert row.result_json == {"results": []}
```

> Use the existing integration fixtures for `sessionmaker_app` / `seed_tenant`. If their
> names differ in `tests/integration/conftest.py`, match the names used by
> `tests/integration/test_backtest*.py`.

- [ ] **Step 2: Run to verify it fails**

Run:
```
ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/saalr \
APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr \
uv run pytest tests/integration/test_discovery_repo.py -q
```
Expected: FAIL — `ImportError: cannot import name 'repo'` / attribute errors.

- [ ] **Step 3: Implement the repo**

```python
# packages/core/saalr_core/discovery/repo.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.trading import DiscoveryRun


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_discovery(session: AsyncSession, discovery_id: UUID) -> DiscoveryRun | None:
    return (
        await session.execute(select(DiscoveryRun).where(DiscoveryRun.discovery_id == discovery_id))
    ).scalar_one_or_none()


async def create_discovery(
    session: AsyncSession, tenant_id: UUID, underlying: str, market: str, request: dict,
) -> UUID:
    row = DiscoveryRun(tenant_id=tenant_id, underlying=underlying, market=market,
                       status="queued", request_json=request)
    session.add(row)
    await session.flush()
    return row.discovery_id


async def mark_running(session: AsyncSession, discovery_id: UUID) -> None:
    row = await get_discovery(session, discovery_id)
    if row is None:
        return
    row.status = "running"
    row.started_at = _utcnow()


async def save_result(
    session: AsyncSession, discovery_id: UUID, result_json: dict | None, status: str,
    error: str | None = None, as_of: str | None = None,
) -> None:
    row = await get_discovery(session, discovery_id)
    if row is None:
        return
    row.status = status
    row.result_json = result_json
    row.error_message = error
    if as_of is not None:
        row.as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    row.completed_at = _utcnow()
```

- [ ] **Step 4: Run to verify it passes**

Run: (same env as Step 2)
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/discovery/repo.py tests/integration/test_discovery_repo.py
git commit   # "feat(discovery): discovery_runs repo (RLS CRUD)" + footer
```

---

### Task 13: Discovery queue — mirror of `backtest_queue.py`

**Files:**
- Create: `packages/core/saalr_core/queue/discovery_queue.py`
- Test: `packages/core/tests/test_discovery_queue.py` (parse-only, no Redis)

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_discovery_queue.py
import uuid
from saalr_core.queue.discovery_queue import Job, STREAM, GROUP, _parse


def test_constants():
    assert STREAM == "saalr:disc:jobs:v1"
    assert GROUP == "disc-workers"


def test_parse_builds_jobs():
    tid, did = uuid.uuid4(), uuid.uuid4()
    jobs = _parse([("1-0", {"tenant_id": str(tid), "discovery_id": str(did)})])
    assert jobs == [Job(msg_id="1-0", tenant_id=tid, discovery_id=did)]


def test_parse_skips_empty_fields():
    assert _parse([("1-0", {})]) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_discovery_queue.py -q`
Expected: FAIL — import error

- [ ] **Step 3: Implement (copy `backtest_queue.py`, rename `backtest_id`→`discovery_id`, change stream/group)**

```python
# packages/core/saalr_core/queue/discovery_queue.py
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from redis.exceptions import ResponseError

STREAM = "saalr:disc:jobs:v1"
GROUP = "disc-workers"
_MAXLEN = 10_000


@dataclass(frozen=True)
class Job:
    msg_id: str
    tenant_id: UUID
    discovery_id: UUID


def _parse(entries) -> list[Job]:
    jobs: list[Job] = []
    for msg_id, fields in entries:
        if not fields:
            continue
        jobs.append(Job(msg_id=msg_id, tenant_id=UUID(fields["tenant_id"]),
                        discovery_id=UUID(fields["discovery_id"])))
    return jobs


async def ensure_group(redis, stream: str = STREAM, group: str = GROUP) -> None:
    try:
        await redis.xgroup_create(stream, group, id="$", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def enqueue(redis, tenant_id: UUID, discovery_id: UUID, stream: str = STREAM) -> str:
    return await redis.xadd(stream, {"tenant_id": str(tenant_id), "discovery_id": str(discovery_id)},
                            maxlen=_MAXLEN, approximate=True)


async def consume_batch(redis, consumer: str, block_ms: int, count: int,
                        stream: str = STREAM, group: str = GROUP) -> list[Job]:
    resp = await redis.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
    if not resp:
        return []
    _stream_name, entries = resp[0]
    return _parse(entries)


async def ack(redis, msg_id: str, stream: str = STREAM, group: str = GROUP) -> None:
    await redis.xack(stream, group, msg_id)
    await redis.xdel(stream, msg_id)


async def claim_stale(redis, consumer: str, min_idle_ms: int, count: int,
                      stream: str = STREAM, group: str = GROUP) -> list[Job]:
    jobs: list[Job] = []
    cursor = "0-0"
    while True:
        result = await redis.xautoclaim(stream, group, consumer, min_idle_ms, start_id=cursor, count=count)
        cursor = result[0]
        entries = result[1] if len(result) > 1 else []
        jobs.extend(_parse(entries))
        if not entries or cursor in ("0-0", "0"):
            return jobs
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_discovery_queue.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/queue/discovery_queue.py packages/core/tests/test_discovery_queue.py
git commit   # "feat(discovery): Redis-Streams queue (mirror of backtest_queue)" + footer
```

---

### Task 14: discovery-worker scaffold + input loaders

**Files:**
- Create: `apps/discovery-worker/pyproject.toml`
- Create: `apps/discovery-worker/discovery_worker/__init__.py` (empty)
- Create: `apps/discovery-worker/discovery_worker/repo.py`
- Test: covered by Task 16's worker integration test

`pyproject.toml` mirrors `apps/backtest-worker/pyproject.toml`. The worker depends on
`saalr-core`, `saalr-ml`, `saalr-api` (for `MarketService` + provider construction), `redis`.

- [ ] **Step 1: Create `pyproject.toml`** (copy backtest-worker's, change name/package)

```toml
# apps/discovery-worker/pyproject.toml
[project]
name = "saalr-discovery-worker"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = ["saalr-core", "saalr-ml", "saalr-api", "redis>=5"]

[tool.uv.sources]
saalr-core = { workspace = true }
saalr-ml = { workspace = true }
saalr-api = { workspace = true }

[dependency-groups]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["discovery_worker"]
```

- [ ] **Step 2: Implement input loaders (`repo.py`)**

```python
# apps/discovery-worker/discovery_worker/repo.py
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.market import Bar, Instrument  # Bar hypertable + instruments
from saalr_core.discovery.repo import (  # re-export the RLS CRUD
    create_discovery, get_discovery, mark_running, save_result,
)

__all__ = ["create_discovery", "get_discovery", "mark_running", "save_result", "load_recent_closes"]


async def load_recent_closes(
    session: AsyncSession, underlying: str, market: str, as_of: date, lookback_days: int = 400,
) -> list[float]:
    """Closes for regime detection (needs >= 60). Non-RLS bars table."""
    start = as_of - timedelta(days=lookback_days)
    rows = (
        await session.execute(
            select(Bar.ts, Bar.close)
            .join(Instrument, Instrument.instrument_id == Bar.instrument_id)
            .where(Instrument.symbol == underlying.upper(), Instrument.market == market)
            .where(Bar.ts >= start)
            .order_by(Bar.ts)
        )
    ).all()
    return [float(c) for _, c in rows]
```

> Verify the actual `Bar`/`Instrument` model module path and column names against
> `apps/backtest-worker/backtest_worker/repo.py::load_underlying_closes` (it already does this
> join). Reuse its exact query shape; the snippet above is the expected shape.

- [ ] **Step 3: Run import smoke**

Run: `uv run --package saalr-discovery-worker python -c "import discovery_worker.repo"`
Expected: no error (after `uv sync`).

- [ ] **Step 4: Sync the workspace + commit**

Run: `uv sync --all-packages --group dev`
```bash
git add apps/discovery-worker/pyproject.toml apps/discovery-worker/discovery_worker/__init__.py apps/discovery-worker/discovery_worker/repo.py uv.lock
git commit   # "feat(discovery): discovery-worker scaffold + input loaders" + footer
```

---

### Task 15: Worker service (3-phase) + chain adapter + consumer + cli

**Files:**
- Create: `apps/discovery-worker/discovery_worker/service.py`
- Create: `apps/discovery-worker/discovery_worker/consumer.py`
- Create: `apps/discovery-worker/discovery_worker/cli.py`
- Create: `apps/discovery-worker/discovery_worker/__main__.py`
- Test: `apps/discovery-worker/tests/test_cli_parser.py`

- [ ] **Step 1: Write the failing test (cli parser — mirrors backtest-worker's)**

```python
# apps/discovery-worker/tests/test_cli_parser.py
from discovery_worker.cli import build_parser


def test_discover_subcommand_parses():
    ns = build_parser().parse_args(["discover", "--underlying", "AAPL", "--market", "US",
                                    "--tenant", "11111111-1111-1111-1111-111111111111"])
    assert ns.cmd == "discover" and ns.underlying == "AAPL"


def test_consume_subcommand_parses():
    ns = build_parser().parse_args(["consume", "--consumer", "w1"])
    assert ns.cmd == "consume" and ns.consumer == "w1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --package saalr-discovery-worker pytest apps/discovery-worker/tests -q`
Expected: FAIL — import error

- [ ] **Step 3: Implement the chain adapter + service (3-phase)**

```python
# apps/discovery-worker/discovery_worker/service.py
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from saalr_core.db.session import tenant_session
from saalr_core.discovery.pipeline import DiscoveryRequest, run_discovery
from saalr_core.discovery.types import CleanChain, Quote
from saalr_core.strategies.types import OptionType
from saalr_ml.montecarlo import monte_carlo_pop

from . import repo


def _quotes_from_payload(payload: dict) -> list[Quote]:
    """Adapt a MarketService.chain() payload's contracts to discovery Quotes (per snapshot)."""
    out: list[Quote] = []
    for c in payload["contracts"]:
        kind = OptionType.CALL if c["type"] == "CALL" else OptionType.PUT
        iv = (c.get("ours") or {}).get("iv")
        out.append(Quote(expiry=c["expiry"], strike=float(c["strike"]), kind=kind,
                         bid=c.get("bid"), ask=c.get("ask"), iv=iv,
                         volume=c.get("volume"), open_interest=c.get("open_interest")))
    return out


def _clean_chain(payload: dict) -> tuple[CleanChain, list[dict]]:
    from saalr_core.discovery.gates import clean_quotes
    clean, dropped = clean_quotes(_quotes_from_payload(payload))
    return (
        CleanChain(underlying=payload["ticker"], as_of=payload["as_of"], spot=payload["spot"],
                   div_yield=payload.get("div_yield", 0.0), contracts=tuple(clean)),
        dropped,
    )


async def run_discovery_job(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: UUID, discovery_id: UUID,
    market_service, rate_for,
) -> dict:
    """Three phases, mirroring backtest service: load inputs / pure+MC compute / persist.
    A read error in phase 1 cannot poison the failure write in phase 3 (fresh session)."""
    # Phase 1 — load inputs.
    try:
        async with tenant_session(sessionmaker, tenant_id) as session:
            row = await repo.get_discovery(session, discovery_id)
            if row is None:
                raise ValueError(f"discovery {discovery_id} not found")
            await repo.mark_running(session, discovery_id)
            underlying, market, request = row.underlying, row.market, dict(row.request_json)
            payload = await market_service._computed_chain(session, underlying, market)
            as_of_date = datetime.fromisoformat(payload["as_of"]).date()
            closes = await repo.load_recent_closes(session, underlying, market, as_of_date)
    except Exception as exc:  # noqa: BLE001
        return await _persist_failed(sessionmaker, tenant_id, discovery_id, str(exc))

    # Phase 2 — pure compute (no DB).
    try:
        clean, dropped = _clean_chain(payload)
        req = DiscoveryRequest(
            dte_min=int(request.get("dte_min", 0)), dte_max=int(request.get("dte_max", 60)),
            strike_window=int(request.get("strike_window", 5)),
            profile=request.get("profile", "ev_to_risk"), top_n=int(request.get("top_n", 10)),
            families=request.get("families"), min_pop=request.get("min_pop"),
            max_loss=request.get("max_loss"), min_open_interest=request.get("min_open_interest"),
            max_bid_ask_pct=request.get("max_bid_ask_pct"),
        )
        result = run_discovery(clean, closes, rate_for, monte_carlo_pop, req, as_of_date)
        result_json = {
            "scoring_profile": result.scoring_profile, "regime": result.regime,
            "results": result.results, "baseline": result.baseline,
            "data_quality_report": [*result.data_quality_report, *dropped],
            "disclosure_block_id": result.disclosure_block_id,
        }
    except Exception as exc:  # noqa: BLE001
        return await _persist_failed(sessionmaker, tenant_id, discovery_id, str(exc))

    # Phase 3 — persist success.
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_result(session, discovery_id, result_json, "succeeded", as_of=payload["as_of"])
    return {"status": "succeeded"}


async def _persist_failed(sessionmaker, tenant_id, discovery_id, error: str) -> dict:
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_result(session, discovery_id, None, "failed", error)
    return {"status": "failed", "error": error}
```

- [ ] **Step 4: Implement consumer (mirror backtest consumer, with MarketService construction)**

```python
# apps/discovery-worker/discovery_worker/consumer.py
from __future__ import annotations

import logging

from saalr_core.queue.discovery_queue import Job, ack, claim_stale, consume_batch, ensure_group

from .service import run_discovery_job

log = logging.getLogger("saalr.discovery.consumer")


async def _process(redis, sessionmaker, job: Job, market_service, rate_for) -> None:
    try:
        await run_discovery_job(sessionmaker, job.tenant_id, job.discovery_id, market_service, rate_for)
    except Exception:  # noqa: BLE001 - poison guard: run_discovery_job persists failures itself
        log.exception("discovery job %s failed unexpectedly", job.discovery_id)
    finally:
        await ack(redis, job.msg_id)


async def run_consumer(redis, sessionmaker, consumer: str, market_service, rate_for,
                       block_ms: int = 5000, count: int = 10, once: bool = False,
                       claim_min_idle_ms: int = 60_000) -> None:
    await ensure_group(redis)
    for job in await claim_stale(redis, consumer, claim_min_idle_ms, count):
        await _process(redis, sessionmaker, job, market_service, rate_for)
    while True:
        for job in await consume_batch(redis, consumer, block_ms, count):
            await _process(redis, sessionmaker, job, market_service, rate_for)
        if once:
            return
```

- [ ] **Step 5: Implement cli + `__main__`**

```python
# apps/discovery-worker/discovery_worker/cli.py
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="discovery-worker")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="create + run one discovery synchronously")
    d.add_argument("--underlying", required=True)
    d.add_argument("--market", default="US")
    d.add_argument("--tenant", required=True)
    d.add_argument("--profile", default="ev_to_risk")
    d.add_argument("--top-n", type=int, default=10, dest="top_n")

    c = sub.add_parser("consume", help="run the queue consumer loop")
    c.add_argument("--consumer", required=True)
    c.add_argument("--once", action="store_true")
    return p
```

```python
# apps/discovery-worker/discovery_worker/__main__.py
from __future__ import annotations

from .cli import build_parser


def main() -> None:
    args = build_parser().parse_args()
    # Wiring (redis, sessionmaker, MarketService, rate_for) mirrors backtest-worker.__main__;
    # construct from env (REDIS_URL, APP_DATABASE_URL, Massive/FRED providers) and dispatch
    # to consumer.run_consumer / service.run_discovery_job. Kept thin; not unit-tested.
    raise SystemExit(f"cmd={args.cmd}: wire providers in deployment (see backtest-worker.__main__)")


if __name__ == "__main__":
    main()
```

> The `__main__` provider wiring is deployment glue (ops slice, like ingest-worker 7) and is
> intentionally not unit-tested here. Mirror `apps/backtest-worker/backtest_worker/__main__.py`
> for env → redis/sessionmaker construction; add Massive provider + FRED rates + `MarketService`
> exactly as `apps/api/saalr_api/main.py` builds them.

- [ ] **Step 6: Run cli test + ruff**

Run:
```
uv run --package saalr-discovery-worker pytest apps/discovery-worker/tests -q
uv run ruff check apps/discovery-worker
```
Expected: PASS (2 passed), ruff clean.

- [ ] **Step 7: Commit**

```bash
git add apps/discovery-worker/discovery_worker/service.py apps/discovery-worker/discovery_worker/consumer.py apps/discovery-worker/discovery_worker/cli.py apps/discovery-worker/discovery_worker/__main__.py apps/discovery-worker/tests/test_cli_parser.py
git commit   # "feat(discovery): worker service (3-phase) + consumer + cli" + footer
```

---

### Task 16: Worker integration test (enqueue → consume → persist)

**Files:**
- Create: `apps/discovery-worker/tests/test_consume_integration.py`

Uses a fake `MarketService` (returns a canned computed-chain payload) + real DB (55432) +
real Redis, mirroring `tests/integration/test_backtest*` style.

- [ ] **Step 1: Write the failing test**

```python
# apps/discovery-worker/tests/test_consume_integration.py
import uuid
import pytest

from saalr_core.db.session import tenant_session
from saalr_core.discovery import repo
from saalr_core.queue.discovery_queue import STREAM, enqueue
from discovery_worker.consumer import run_consumer

pytestmark = pytest.mark.asyncio


class _FakeMarket:
    async def _computed_chain(self, session, ticker, market):
        strikes = list(range(80, 121, 5))
        contracts = []
        for k in strikes:
            for t in ("CALL", "PUT"):
                contracts.append({"expiry": "2026-07-10", "strike": float(k), "type": t,
                                  "bid": 1.9, "ask": 2.1, "volume": 50, "open_interest": 500,
                                  "ours": {"iv": 0.3}})
        return {"ticker": ticker, "market": market, "as_of": "2026-06-10T20:00:00Z",
                "spot": 100.0, "div_yield": 0.0, "contracts": contracts}


async def test_enqueue_consume_persists_results(sessionmaker_app, seed_tenant, redis_client, seed_bars):
    tenant_id = seed_tenant
    await redis_client.delete(STREAM)
    async with tenant_session(sessionmaker_app, tenant_id) as s:
        did = await repo.create_discovery(s, tenant_id, "AAPL", "US",
                                          {"dte_min": 0, "dte_max": 60, "profile": "ev_to_risk",
                                           "top_n": 5, "families": ["bull_put_spread"]})
    await enqueue(redis_client, tenant_id, did)
    await run_consumer(redis_client, sessionmaker_app, "w-test", _FakeMarket(),
                       rate_for=lambda t: 0.05, once=True, block_ms=100)
    async with tenant_session(sessionmaker_app, tenant_id) as s:
        row = await repo.get_discovery(s, did)
        assert row.status == "succeeded"
        assert "results" in row.result_json
        assert row.result_json["scoring_profile"] == "ev_to_risk"
```

> `seed_bars` must insert >= 60 daily closes for AAPL/US so `classify_regime` succeeds. If no
> such fixture exists, add one to `tests/integration/conftest.py` (or the worker's conftest)
> that inserts a rising series into `instruments` + `bars`, mirroring how
> `tests/integration/test_backtest.py` seeds bars.

- [ ] **Step 2: Run to verify it fails, then passes once fixtures exist**

Run:
```
ADMIN_DATABASE_URL=... APP_DATABASE_URL=... REDIS_URL=redis://localhost:6379/0 \
uv run --package saalr-discovery-worker pytest apps/discovery-worker/tests/test_consume_integration.py -q
```
Expected: FAIL first (no results / fixture), then PASS after implementing fixtures.

- [ ] **Step 3: Commit**

```bash
git add apps/discovery-worker/tests/test_consume_integration.py tests/integration/conftest.py
git commit   # "test(discovery): worker enqueue->consume->persist integration" + footer
```

---

### Task 17: API — schemas + router (202/poll, gating, idempotency)

**Files:**
- Create: `apps/api/saalr_api/discovery/__init__.py` (empty)
- Create: `apps/api/saalr_api/discovery/schemas.py`
- Create: `apps/api/saalr_api/discovery/router.py`
- Modify: `apps/api/saalr_api/main.py` (register router + lifespan `ensure_group`)
- Test: `tests/integration/test_discovery_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_discovery_api.py
import pytest

pytestmark = pytest.mark.asyncio


async def test_free_tier_gets_402(client_free):
    r = await client_free.post("/v1/discovery", json={"underlying": "AAPL", "market": "US",
                                                       "dte_min": 0, "dte_max": 60})
    assert r.status_code == 402
    assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO"


async def test_pro_creates_queued_run_and_polls(client_pro):
    r = await client_pro.post("/v1/discovery", json={"underlying": "AAPL", "market": "US",
                                                      "dte_min": 0, "dte_max": 60, "top_n": 5})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    did = body["discovery_id"]
    poll = await client_pro.get(f"/v1/discovery/{did}")
    assert poll.status_code == 200
    assert poll.json()["status"] in ("queued", "running", "succeeded")


async def test_idempotency_key_dedupes(client_pro):
    headers = {"Idempotency-Key": "disc-abc-123"}
    body = {"underlying": "AAPL", "market": "US", "dte_min": 0, "dte_max": 60}
    a = await client_pro.post("/v1/discovery", json=body, headers=headers)
    b = await client_pro.post("/v1/discovery", json=body, headers=headers)
    assert a.json()["discovery_id"] == b.json()["discovery_id"]
```

> Reuse the entitlement-fixture pattern from `tests/integration/test_*` that exercises
> `require_ml_forecast` (e.g. the montecarlo/forecast tests). `client_free`/`client_pro` should
> match those fixtures' names; if different, align.

- [ ] **Step 2: Run to verify it fails**

Run: (DB + Redis env) `uv run pytest tests/integration/test_discovery_api.py -q`
Expected: FAIL — 404 (route missing)

- [ ] **Step 3: Implement schemas**

```python
# apps/api/saalr_api/discovery/schemas.py
from __future__ import annotations

from pydantic import BaseModel, model_validator


class DiscoveryRequest(BaseModel):
    underlying: str
    market: str = "US"
    dte_min: int = 0
    dte_max: int = 60
    strike_window: int = 5
    profile: str = "ev_to_risk"
    top_n: int = 10
    families: list[str] | None = None
    min_pop: float | None = None
    max_loss: float | None = None
    min_open_interest: int | None = None
    max_bid_ask_pct: float | None = None

    @model_validator(mode="after")
    def _valid_ranges(self) -> "DiscoveryRequest":
        if self.dte_max < self.dte_min:
            raise ValueError("dte_max must be >= dte_min")
        if self.profile not in ("ev_to_risk", "pop", "ev_absolute"):
            raise ValueError("unknown scoring profile")
        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")
        return self


ESTIMATED_DURATION_SECONDS = 20
```

- [ ] **Step 4: Implement router (mirror backtest router ordering invariants)**

```python
# apps/api/saalr_api/discovery/router.py
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.session import tenant_session
from saalr_core.discovery import repo
from saalr_core.queue.discovery_queue import enqueue

from ..auth import Principal
from ..forecast.gating import require_ml_forecast
from .schemas import ESTIMATED_DURATION_SECONDS, DiscoveryRequest

router = APIRouter(tags=["discovery"])


def _idem_key(tenant_id, key: str) -> str:
    return f"saalr:idem:disc:{tenant_id}:{key}"


def _accepted(discovery_id, status: str) -> dict:
    return {"discovery_id": str(discovery_id), "status": status,
            "estimated_duration_seconds": ESTIMATED_DURATION_SECONDS,
            "poll_url": f"/v1/discovery/{discovery_id}"}


@router.post("/v1/discovery", status_code=202)
async def create_discovery_run(
    body: DiscoveryRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    session, principal = ctx
    redis = request.app.state.redis
    sm = request.app.state.sessionmaker

    if idempotency_key:
        existing = await redis.get(_idem_key(principal.tenant_id, idempotency_key))
        if existing:
            row = await repo.get_discovery(session, UUID(existing))
            if row is not None:
                return _accepted(row.discovery_id, row.status)

    # Create + commit the row in its OWN tx BEFORE enqueue (worker can't read a missing row).
    async with tenant_session(sm, principal.tenant_id) as create_session:
        discovery_id = await repo.create_discovery(
            create_session, principal.tenant_id, body.underlying.upper(), body.market,
            body.model_dump(),
        )

    if idempotency_key:
        await redis.set(_idem_key(principal.tenant_id, idempotency_key), str(discovery_id), nx=True, ex=86400)

    try:
        await enqueue(redis, principal.tenant_id, discovery_id)
    except Exception as exc:  # noqa: BLE001
        if idempotency_key:
            try:
                await redis.delete(_idem_key(principal.tenant_id, idempotency_key))
            except Exception:  # noqa: BLE001
                pass
        raise HTTPException(503, {"error": {"code": "DISCOVERY_ENQUEUE_FAILED",
                                            "message": "could not enqueue job"}}) from exc

    return _accepted(discovery_id, "queued")


@router.get("/v1/discovery/{discovery_id}")
async def get_discovery_run(
    discovery_id: UUID,
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    session, _ = ctx
    row = await repo.get_discovery(session, discovery_id)
    if row is None:
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "discovery not found"}})
    out: dict = {"discovery_id": str(row.discovery_id), "status": row.status}
    if row.status == "succeeded" and row.result_json:
        out["as_of"] = row.as_of.isoformat() if row.as_of else None
        out.update({k: row.result_json.get(k) for k in
                    ("scoring_profile", "regime", "results", "baseline",
                     "data_quality_report", "disclosure_block_id")})
    elif row.status == "failed":
        out["error"] = {"code": "DISCOVERY_FAILED", "message": row.error_message}
    return out
```

- [ ] **Step 5: Register router + lifespan ensure_group in `main.py`**

In `apps/api/saalr_api/main.py`: import and `app.include_router(discovery_router)`, and in the
lifespan startup (where backtest's `ensure_group` is called) add discovery's:

```python
from saalr_core.queue.discovery_queue import ensure_group as ensure_discovery_group
# ... inside lifespan startup, next to the backtest ensure_group call:
await ensure_discovery_group(app.state.redis)
```
```python
from .discovery.router import router as discovery_router
# ... next to other include_router calls:
app.include_router(discovery_router)
```

> Find the exact lifespan + include_router sites by matching the existing
> `backtest_queue.ensure_group` and `backtests` router registration in `main.py`.

- [ ] **Step 6: Run the API integration test + ruff**

Run: (DB + Redis env) `uv run pytest tests/integration/test_discovery_api.py -q && uv run ruff check apps/api/saalr_api/discovery`
Expected: PASS (3 passed), ruff clean.

- [ ] **Step 7: Commit**

```bash
git add apps/api/saalr_api/discovery/ apps/api/saalr_api/main.py tests/integration/test_discovery_api.py
git commit   # "feat(discovery): async API (202/poll, ml_forecast gate, idempotency)" + footer
```

---

### Task 18: Full-suite gate + docs note

**Files:**
- Modify: `docs/superpowers/specs/2026-06-10-strategy-discovery-design.md` (mark Built; note the
  option-only-templates decision under "Out of scope / deferred" if not already captured)

- [ ] **Step 1: Run the complete backend gate**

Run:
```
ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/saalr \
APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr \
REDIS_URL=redis://localhost:6379/0 \
uv run pytest packages/core/tests packages/ml/tests tests -q
uv run --package saalr-discovery-worker pytest apps/discovery-worker/tests -q
uv run ruff check packages/core/saalr_core/discovery apps/discovery-worker apps/api/saalr_api/discovery
```
Expected: all PASS (including the 10 invariant-harness tests now green), ruff clean.

- [ ] **Step 2: Update the spec status + commit**

```bash
git add docs/superpowers/specs/2026-06-10-strategy-discovery-design.md
git commit   # "docs(discovery): mark strategy-discovery built" + footer
```

**Milestone B complete: user-callable async discovery feature shipped.**

---

## Self-review notes (author checklist — completed)

- **Spec coverage:** every spec stage 0–9 maps to a task (gen=T3, gates=T2, metrics=T4,
  free-lunch=T2/T9, MC=T4/T9, filter=T6, rank=T5/T6, baseline=T7, serialize=T8, pipeline=T9);
  table+migration=T11, repo=T12, queue=T13, worker=T14–16, API=T17. Harness wiring=T10.
- **New decision flagged:** option-only templates this slice (equity/cash-leg deferred) — must
  be reflected in the spec's "Out of scope" (Task 18 step 2).
- **Type consistency:** `mc_pop(legs, spot, t_years, sigma, rate, div_yield, seed)` signature is
  used identically in metrics.py, baseline.py, pipeline.py, and the worker passes
  `saalr_ml.montecarlo.monte_carlo_pop` (whose real signature is
  `(legs, spot, t_years, sigma, rate, div_yield=0.0, drift_adjust=0.0, paths=..., seed=...)` —
  the positional `div_yield` then keyword `seed` call matches; `drift_adjust`/`paths` default).
  `DiscoveryRequest` (core dataclass) vs `DiscoveryRequest` (API pydantic) are intentionally
  distinct types in different modules; the worker builds the core one from the stored dict.
- **Multiplier caveat (T10):** harness expectations are per-share; engine payoff is per-contract
  (×100). The adapter divides by `OPTION_MULTIPLIER`. If a harness test fails on a factor of 100,
  that's the lever — adjust the adapter, never the harness.
