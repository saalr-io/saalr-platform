# Strategy Discovery — Design

**Date:** 2026-06-10
**Slice:** Strategy discovery (LLD strategy-discovery module; the target of the installed
`docs/INVARIANTS.md` catalog and the `DiscoveryAdapter` invariant harness).
**Status:** Approved design, pre-plan.

## Summary

Strategy discovery is the async, Pro-gated module that takes a **point-in-time option
chain** for an underlying and **generates concrete candidate option strategies** (real
listed strikes/expiries), prices and scores each (payoff math, Monte-Carlo PoP/EV,
Greeks), applies quote-sanity and free-lunch gates, filters the full set, and returns a
**deterministically ranked, compliance-safe** list with an honest baseline and a disclosure
block.

It is distinct from the existing strategy **builder** (`saalr_core/strategies/`, where the
user constructs one strategy) and from `recommend.py` (which only ranks template
*families* by regime fit). Discovery is the missing layer that turns "which family fits the
regime" into "here are the concrete, ranked strikes, with metrics."

Every stage maps to an invariant ID in `docs/INVARIANTS.md`; the installed harness
(`tests/unit/test_strategy_invariants.py`) is wired to the new engine and goes green.

## Decisions (locked during brainstorming)

| Decision | Choice |
|---|---|
| Slice scope | Engine **+ async API** (user-callable feature) |
| Family selection | **Compose with regime**: `classify_regime` → `recommend` picks families; user can override via `families`. Default **top-3** families. |
| Execution | **Async**, Redis-Streams + 202/poll, mirroring backtest 8b. Monte-Carlo on **every** candidate. |
| Ranking | **Multi-profile from day one**: `ev_to_risk` (default), `pop`, `ev_absolute`; all dominance-guarded; profile echoed in output. |
| Tier gate | **Pro** via the existing `ml_forecast` entitlement (free → 402). |
| Topology | **Approach A**: pure engine in `saalr_core/discovery/`, MC stays in `saalr_ml`, new `discovery-worker` app mirroring `backtest-worker`. |
| Strike window | **±5 listed strikes around ATM** (11-strike window per expiry), tunable via `strike_window=5`. |

## Reuse map

| Need | Reused component |
|---|---|
| Regime → families | `saalr_ml.regime.classify_regime(closes)` → `saalr_core.strategies.recommend.recommend(regime, templates)` |
| Templates | `saalr_core.strategies.templates.list_templates()` |
| Chain snapshot | `RawChain{underlying, market, as_of, spot, div_yield, contracts:[RawContract{expiry,strike,kind,bid,ask,last,volume,open_interest,vendor_iv,vendor_delta/gamma/theta/vega}]}` via `MassiveProvider.get_option_chain` |
| Payoff/extremes | `strategies.payoff`: `expiration_curve`, `net_premium`, `breakevens`, `max_pl`, `risk_reward`, `profit_intervals` |
| PoP (closed-form) | `strategies.pop.probability_of_profit(spot, atm_iv, t_years, rate, div_yield, profit_intervals)` |
| PoP (MC) + EV | `saalr_ml.montecarlo.monte_carlo_pop(legs, spot, t_years, sigma, rate, div_yield, drift_adjust, paths, seed, hist_bins)` |
| Net Greeks | `strategies.aggregate` |
| Types | `strategies.types`: `OptionLeg`, `Side`, `OptionType`, `StrategyConfig`, `OPTION_MULTIPLIER` |
| Rate curve | `YieldCurve.rate_for(t_years)` (FRED) |
| Async job pattern | `saalr_core/queue/backtest_queue.py`, `apps/api/saalr_api/backtests/`, `apps/backtest-worker/` |
| Gating | `apps/api/saalr_api/forecast/gating.require_ml_forecast` |

## Module layout (Approach A)

```
packages/core/saalr_core/discovery/        # PURE engine (stdlib only, numpy-free)
  __init__.py
  generate.py    candidate enumeration from a clean chain, per template family
  gates.py       quote-sanity (DATA-3) + free-lunch quarantine (RANK-2)
  filters.py     liquidity / min-PoP / max-risk filtering (RANK-3 filter-before-truncate)
  score.py       scoring profiles (ev_to_risk | pop | ev_absolute), dominance-guarded
  rank.py        deterministic ordering (RANK-1/4/5) + top-N truncation
  baseline.py    naive ATM-short-put baseline (DATA-4)
  serialize.py   compliance-safe output strings + disclosure plumbing (COMPLY-*)
  pipeline.py    orchestrates the stages → a DiscoveryResult dataclass
  testing.py     HarnessAdapter → wires the installed DiscoveryAdapter protocol
  repo.py        discovery_runs CRUD (RLS), create/get/mark_running/save_result

packages/core/saalr_core/queue/discovery_queue.py   # mirror of backtest_queue.py

apps/discovery-worker/                      # thin shell, mirrors backtest-worker
  discovery_worker/{repo.py, service.py, consumer.py, cli.py}
  pyproject.toml, tests/

apps/api/saalr_api/discovery/               # 202/poll API
  {schemas.py, router.py}
```

MC PoP/EV stays in `saalr_ml.montecarlo` (numpy isolated). The worker and `testing.py`
compose `saalr_core.discovery` (pure) + `saalr_ml` (MC). The pure engine has **no numpy
import**, preserving the lean-core invariant.

## Pipeline (worker runs in order)

Input: live `RawChain` (point-in-time), `closes` (for regime), rate curve, request filters,
scoring profile, MC seed.

| # | Stage | Invariants | Reuses |
|---|---|---|---|
| 0 | **Regime → families.** `classify_regime(closes)` → `recommend(regime, templates)` → top-3 families. When the request supplies `families`, it **replaces** the `recommend()` selection, but `classify_regime` still runs to populate the output `regime` context. | COMPLY-3 | `saalr_ml.regime`, `strategies.recommend` |
| 1 | **Quote-sanity gate.** From `contracts`, drop/flag zero-bid, crossed (bid>ask), missing/stale; build clean quote table keyed by (expiry,strike,kind); entry price = mid = (bid+ask)/2. | DATA-3 | — |
| 2 | **Candidate generation.** Per family: per expiry in [dte_min,dte_max], find ATM strike (nearest listed to spot), take ±5 listed strikes (11-strike window), enumerate template-valid leg combos from those *real* strikes; enforce template constraints at construction; reject degenerate. | STRUCT-1/2/4 | `strategies.templates`, `types` |
| 3 | **Structural validation.** Defined-risk label ⇒ finite computable max loss (from `max_pl`); else reject (forbidden defined-risk label). Single sign convention imported, never re-derived. | STRUCT-0/3 | `strategies.payoff` |
| 4 | **Metrics.** net_premium, expiry curve, breakevens, max profit/loss, risk_reward, profit_intervals, net Greeks. | PAYOFF-1/2/3/4, GREEK-1/2 | `strategies.payoff`, `aggregate` |
| 5 | **Free-lunch quarantine.** net-credit + non-negative payoff everywhere ⇒ routed to `data_quality_report`, **never** to results (bad quote, not alpha). | RANK-2 (BLOCKER-class) | — |
| 6 | **MC scoring.** `monte_carlo_pop` per surviving candidate; σ = chain **ATM IV from the same snapshot** (PROB-5 provenance, single timestamp shared with pricing); also closed-form PoP for the PROB-1 cross-check. Seeded → deterministic. | PROB-1/2/5 | `saalr_ml.montecarlo`, `strategies.pop` |
| 7 | **Filter-before-truncate.** liquidity (min OI/volume, max bid-ask %), min-PoP, max-loss applied to the **full** candidate set, before any top-N. | RANK-3, RANK-5 | `filters.py` |
| 8 | **Rank + truncate.** selected profile, dominance-guarded; deterministic (seeded MC, stable sort with explicit tie-break); take top-N. | RANK-1/4/5 | `score.py`, `rank.py` |
| 9 | **Baseline + serialize.** attach naive ATM-short-put baseline; emit metrics-not-advice strings; echo scoring_profile; attach disclosure_block_id; run every user-facing string through the COMPLY-1 blocklist. | DATA-4, COMPLY-1/2/4 | `baseline.py`, `serialize.py` |

**Vol-input note (PROB-5):** the MC σ is the chain's ATM IV, so the PoP vol and the pricing
snapshot share one `as_of` timestamp. GARCH-σ as an alternative vol source is a noted
future enhancement, not in this slice.

**Combinatorics (bounded):** 11 strikes × ~4 expiries → verticals ≈ C(11,2)×2×4 ≈ 440;
condors add a few hundred more. Order ~10³ candidates per scan; `strike_window` caps it.
Massive's `atm_band` bounds the *fetch*; `strike_window=5` bounds the *enumeration* (the
invariant-relevant, deterministic one).

## Persistence — `discovery_runs` (new migration)

Tenant-scoped, FORCE-RLS, policy mirrors `backtests`. `saalr_app` gets SELECT/INSERT/UPDATE
(no truncate; tests truncate via admin).

| column | type | notes |
|---|---|---|
| `discovery_id` | UUID PK | |
| `tenant_id` | UUID | RLS key |
| `underlying` / `market` | text | |
| `status` | text | queued / running / succeeded / failed |
| `request_json` | JSONB | filters, profile, families-override, strike_window, top_n |
| `result_json` | JSONB | ranked candidates + baseline + data_quality_report + provenance |
| `error_message` | text | null unless failed |
| `as_of` | timestamptz | chain snapshot timestamp (PROB-5 / DATA-1 provenance) |
| `created_at` / `completed_at` | timestamptz | |

## Queue + worker

- `saalr_core/queue/discovery_queue.py` — mirror of `backtest_queue.py`:
  `STREAM="saalr:disc:jobs:v1"`, `GROUP="disc-workers"`, `Job(msg_id, tenant_id, discovery_id)`,
  same `ensure_group`/`enqueue`/`consume_batch`/`ack`/`claim_stale`.
- `apps/discovery-worker/` mirrors `backtest-worker`:
  - `consumer.py` — `run_consumer` → `ensure_group` → `claim_stale` reprocess → loop
    `consume_batch` → `_process` → **finally-ack poison guard**.
  - `service.py` — **3-phase transaction split**: (1) load-inputs tx, (2) pure + MC compute,
    (3) persist tx, so a failed run's `status='failed'` write happens in a fresh
    `tenant_session` (a read error can't poison the failure write).
  - `repo.py` re-exports the core `discovery.repo` CRUD + adds input loaders.
  - `cli.py` — `discover --underlying … --tenant …` (create+run) and `consume`.
- **Data loading (phase 1):** worker fetches a **live chain** via `MarketService` /
  `MassiveProvider.get_option_chain`, `closes` from `bars` (regime), rate curve from FRED;
  records `as_of`.
- **Test invocation:** worker pkg is not a root dep → `uv run --package saalr-discovery-worker
  pytest apps/discovery-worker/tests`.

## API (`apps/api/saalr_api/discovery/`)

```
POST /v1/discovery        → 202
  gated by require_ml_forecast (free → 402 upgrade nudge)
  body: { underlying, market, dte_min, dte_max, strike_window=5,
          max_loss?, min_pop?, min_open_interest?, max_bid_ask_pct?,
          profile="ev_to_risk", families?: [str], top_n=10 }
  → { discovery_id, status:"queued", poll_url, estimated_duration_seconds }
```

Ordering invariants (mirrored from the backtest handler):
1. Create + commit the `discovery_runs` row in its **own** `tenant_session` **before** enqueue
   (the worker cannot read a row that does not exist; `get_principal`'s session commits only
   after the handler returns).
2. `Idempotency-Key` header → `SET NX saalr:idem:disc:{tenant}:{key}` (24h) bound **before**
   enqueue, with compensating delete on enqueue failure.
3. `ensure_group` called at API lifespan startup **and** in `run_consumer` (a `$`-start group
   only sees messages XADDed after it exists).

```
GET /v1/discovery/{id}    → poll
  queued/running → { discovery_id, status }
  succeeded      → { status, as_of, scoring_profile, regime, results:[…],
                     baseline:{…}, data_quality_report:[…], disclosure_block_id }
  failed         → { status, error:{ code:"DISCOVERY_FAILED", message } }
```

## Output schema (compliance-safe)

Each entry in `results[]`:

```jsonc
{
  "rank": 1,
  "template": "put_credit_spread",
  "legs": [ { "option_type":"PUT","side":"SELL","strike":100,"expiry":"2026-07-17","qty":1 }, … ],
  "metrics": {
    "net_premium": -1.10, "net_credit": 1.10,        // STRUCT-0 sign convention, imported once
    "max_profit": 1.10, "max_loss": 3.90, "risk_reward": 0.28,
    "breakevens": [98.90],
    "pop": 0.74, "pop_method": "monte_carlo",
    "pop_closed_form": 0.7409,                         // echoed for transparency / PROB-1
    "ev": 0.31, "ev_to_risk": 0.079,
    "greeks": { "delta":0.12, "gamma":0.0, "theta":0.0, "vega":-0.05 }
  },
  "score": 0.079, "score_profile": "ev_to_risk",       // COMPLY-2: profile echoed
  "summary": "Ranked #1 by EV-to-max-loss under your filters."  // metrics phrasing, no imperatives
}
```

- `baseline`: `{ "naive": "atm_short_put", "pop": …, "ev": … }` (DATA-4 — no number ships
  without its baseline).
- `data_quality_report`: free-lunch quarantined candidates + dropped quotes
  (RANK-2 / DATA-3) — diagnostic, never in `results`.
- `disclosure_block_id`: non-null on every payload (COMPLY-4).

## Scoring profiles

All profiles are dominance-respecting (RANK-1): a candidate weakly better in every terminal
state and strictly better somewhere, at ≤ cost, must never rank below the dominated one.

- `ev_to_risk` (**default**): EV (from MC) ÷ max_loss. Reward per unit of defined risk.
- `pop`: probability of profit, **with a risk guard** (tie-break / floor on EV-to-risk) so a
  high-PoP / tiny-credit / huge-risk trade cannot outrank a balanced one — keeps RANK-1.
- `ev_absolute`: EV alone.

Ties broken deterministically (e.g. by EV then by a stable candidate key) so RANK-4 holds.

## Test plan

**Pure unit (`packages/core/tests/`)** — TDD'd with synthetic chains:
- `generate` → STRUCT-1/2/4 (real strikes only, 11-strike window, constraints at
  construction, degenerate rejection).
- `gates` → DATA-3 (zero-bid/crossed/stale dropped) + RANK-2 (free-lunch quarantined).
- `filters` → RANK-3 (filter applies to full set before truncate) + RANK-5 (irrelevant
  alternative doesn't reorder survivors).
- `score`/`rank` → RANK-1 (dominance) + RANK-4 (determinism).
- `serialize` → COMPLY-1/2/4 (blocklist, profile echoed, disclosure present).

**Invariant harness** — implement `HarnessAdapter` in `saalr_core/discovery/testing.py`,
point `make_adapter()` at it → the 10 currently-skipped tests in
`tests/unit/test_strategy_invariants.py` run **green**: PAYOFF-1/2, PROB-1/2/3, GREEK-1,
RANK-1/2/4, COMPLY-1.

**Golden regression** — a test loads `tests/fixtures/golden_strategies.json` and asserts the
engine reproduces `PCS-GOLDEN-001` (hand-verified) within stated tolerances.

**API + worker integration (`tests/integration/`, DB on 55432, Redis)** — 202/poll happy
path; 402 when un-entitled; idempotency dedupe; RLS isolation; enqueue→consume→persist;
failed-run persistence.

**Gate commands:**
- `… uv run pytest packages/core/tests packages/ml/tests` (pure + harness, torch-free)
- root integration suite (DB on 55432 + Redis)
- `uv run --package saalr-discovery-worker pytest apps/discovery-worker/tests`
- `ruff check` clean.

## Out of scope / deferred

- GARCH-σ (and skew-aware per-leg IV) as alternative MC vol sources.
- Discovery UI (a later front-end slice).
- Containerize/daemonize the discovery worker (an ops slice, like ingest-worker 7).
- Per-tier rate limits / quotas on scans; dead-letter stream.
- Multi-expiry exactness for calendars (MC values legs at the nearest expiry, same caveat as
  the existing montecarlo endpoint).
- Saving a discovered candidate straight into the strategy builder / OMS.
