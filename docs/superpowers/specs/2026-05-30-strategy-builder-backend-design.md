# Strategy builder — backend (7a) — design

**Date:** 2026-05-30
**Slice:** LLD §13 step 7 — "Strategy CRUD + multi-leg builder UI. No execution yet." This is the **backend half (7a)**; the React builder UI is a follow-up slice (7b).
**Status:** Approved design, pre-plan.
**Builds on:** the Greeks/vol-surface slice (`saalr_core/pricing`, `saalr_core/marketdata`, `saalr_api/market`).

## Purpose

A headless, fully-tested backend for creating, persisting, and analyzing multi-leg
options strategies. It consumes the BSM engine to produce the analytics a
Sensibull-style builder needs — payoff diagrams (expiration **and** target-date),
breakevens, max P/L, net premium, net Greeks, and an approximate probability of profit —
plus a catalog of ready-made strategy templates.

## Decisions (locked during brainstorming)

1. **Backend-first (7a)** — CRUD + analytics now; React multi-leg builder UI is slice 7b.
2. **Leg types:** option + equity + cash. Cash = collateral accounting for payoff
   (capital-at-risk); full broker margin (Reg-T/SPAN) is deferred to the OMS/risk slice.
3. **Analytics:** pure expiration payoff + **live** net Greeks (via the Massive chain).
   Plus (Sensibull-inspired): **target-date theoretical payoff curve**, a **strategy-templates
   catalog**, and a **simple lognormal POP**. Margin/funds deferred.
4. **State machine:** the full §7 FSM (enum + `VALID_TRANSITIONS`), pure, illegal transitions
   raise. Only `DRAFT↔BACKTESTED↔ARCHIVED` are reachable now; `PAPER`/`LIVE` states exist but
   their transitions + promotion gates are deferred to the OMS/live-trading slices.
5. **Tier gating:** CRUD + pure payoff available to all tiers; the **live** analysis
   (net Greeks, target-date curve, POP, auto-filled prices) requires the `vol_surface`
   entitlement (Pro+), reusing the existing gate.

### Roadmap context (not in this slice)
- **Paper + live trading are built together** at the OMS/broker slices (§13 steps 11–13), on
  one account-mode-agnostic order path (`broker_accounts.is_paper`), live guarded by the §7
  promotion gates. 7a only builds the FSM states, not execution.

### Structure (Approach A)
Pure domain logic in `saalr_core/strategies/`; thin API in `saalr_api/strategies/`. The
payoff/POP/aggregation math stays pure so the backtest slice (step 8) can reuse it.

## Architecture

```
packages/core/saalr_core/strategies/   # PURE — stdlib + pricing engine, no I/O
  types.py        # OptionLeg / EquityLeg / CashLeg, StrategyConfig, OptionType, Side, LegKind
  state.py        # §7 StrategyState enum + VALID_TRANSITIONS + transition(); IllegalTransition
  payoff.py       # expiration_curve, target_date_curve, breakevens, max_pl, net_premium
  pop.py          # probability_of_profit (lognormal, ATM IV)
  aggregate.py    # net_greeks
  templates.py    # ready-made strategy registry + build()

apps/api/saalr_api/strategies/         # web layer (auth, gating, persistence, HTTP shapes)
  schemas.py      # pydantic request/response (leg discriminated union, validation)
  repo.py         # RLS-scoped strategies table access (insert/get/list/update/set_state)
  service.py      # CRUD orchestration + analyze (composes MarketService for live data)
  gating.py       # reuse require_vol_surface; helper for the analyze live-vs-pure split
  router.py       # APIRouter(prefix="/v1/strategies")
apps/api/saalr_api/main.py             # MODIFY: include strategies router
```

## Components

### `saalr_core/strategies/types.py` (pure)

`OptionType` (CALL/PUT), `Side` (BUY=+1, SELL=−1), `LegKind` (option/equity/cash).

- `OptionLeg(kind="option", option_type, side, strike: float, expiry: str "YYYY-MM-DD", qty: int>0, entry_price: float|None)`
- `EquityLeg(kind="equity", side, qty: int>0, entry_price: float|None)`  — shares
- `CashLeg(kind="cash", amount: float>0)`  — collateral; 0 to P&L shape, feeds capital-at-risk
- `StrategyConfig(underlying: str, legs: list[Leg])`

Conventions: `side` sets sign; `qty` always positive. Option qty is **contracts** (×100
multiplier in payoff/Greeks); equity qty is **shares** (×1). `entry_price` is the seam between
pure and live: present → pure P&L from inputs; absent → the analyze endpoint fills it from the
live Massive mid.

### `state.py` (pure)
The §7 FSM verbatim — `StrategyState` enum and `VALID_TRANSITIONS`. `transition(current,
target) -> StrategyState` returns target if the edge is valid, else raises `IllegalTransition`.
`archived` is terminal. Promotion gates are NOT implemented here (deferred).

### `payoff.py` (pure) — legs must carry `entry_price`
- `expiration_curve(legs, spot_grid) -> list[tuple[float, float]]`: per spot S, sum leg P&L —
  option `side·(intrinsic(S) − entry)·100·qty` (intrinsic = `max(S−K,0)` call / `max(K−S,0)` put);
  equity `side·(S − entry)·qty`; cash 0.
- `target_date_curve(legs, spot_grid, eval_date, rate, div_yield, iv_by_leg) -> list[tuple[float,float]]`:
  re-prices each option leg with BSM at remaining time `(expiry − eval_date)/365` and the leg's
  IV; same equity/cash treatment. At `eval_date == expiry` this equals `expiration_curve`.
- `breakevens(curve) -> list[float]`: linear-interpolated zero crossings.
- `max_pl(curve) -> {max_profit, max_loss, unbounded_profit: bool, unbounded_loss: bool}`:
  extrema over the grid plus tail-slope detection — a non-zero outward slope at a grid end →
  that side is unbounded (value `None` + flag), never a clipped number.
- `net_premium(legs) -> float`: `Σ side·entry·mult·qty` (positive = net debit, negative = credit).
- `risk_reward(max_profit, max_loss) -> float | None` (None when either side unbounded).
- Spot grid: anchored on the leg strikes and `spot`, spanning ≈ [0.5×, 1.5×] spot, plus exact
  strike points so breakevens/extrema land on kinks.

### `pop.py` (pure)
`probability_of_profit(spot, atm_iv, t_years, rate, div_yield, profit_intervals) -> {pop, method, approximate}`:
terminal price `S_T` lognormal with drift `(rate − div_yield − 0.5·iv²)·t` and vol `iv·√t`;
POP = Σ lognormal-CDF mass over the profit intervals (derived from breakevens + curve sign).
Always returns `method="lognormal_atm_iv"`, `approximate=true` — honest, and explicitly weaker
than the Monte-Carlo POP of step 10.

### `aggregate.py` (pure)
`net_greeks(priced_legs) -> {delta, gamma, theta, vega, rho}`: `Σ option_greek·100·qty·side`;
equity adds `delta += qty·side`; cash 0.

### `templates.py` (pure)
Registry of ready-made strategies. Each entry: descriptor `{key, name, category:
bullish|bearish|neutral, description}` + `build(underlying, expiry, atm_strike, width?) ->
StrategyConfig`. Initial set (~9): `bull_call_spread`, `bear_put_spread`, `long_straddle`,
`long_strangle`, `iron_condor`, `iron_butterfly`, `covered_call`, `cash_secured_put`,
`long_calendar`.

### `saalr_api/strategies/` (web)
- **`schemas.py`** — pydantic models with a discriminated leg union; validates non-empty legs,
  option legs require strike/expiry/type, `qty>0`, `amount>0`, ISO expiry, non-empty alpha
  underlying. Invalid → 400 `VALIDATION_INVALID_PARAMETER`.
- **`repo.py`** — RLS-scoped access to `strategies` (insert, get-by-id, keyset list, update,
  set_state) using the `get_principal` session (tenant GUC already set). IDs exposed as raw
  UUID strings (matches existing app; LLD `str_` prefix is a separate cross-cutting concern).
- **`service.py`** — CRUD orchestration; `analyze` computes the pure payoff from supplied
  entry prices and, when live is requested + entitled, composes `MarketService` to fetch the
  Massive chain, fill missing prices + per-leg IV, and add net Greeks + target-date curve + POP.
- **`router.py`** — endpoints below.

## API

IDs are raw UUID strings. RLS scopes everything to the principal's tenant. Standard
`{"error":{"code","message"}}` envelope.

| Method & path | Tier | Notes |
|---|---|---|
| `POST /v1/strategies` | all | validate config → persist `state="draft"` → `StrategyOut` |
| `GET /v1/strategies?cursor=&limit=` | all | keyset pagination on `(created_at, strategy_id)` desc; `next_cursor` |
| `GET /v1/strategies/{id}` | all | 404 `RESOURCE_NOT_FOUND` if absent/other-tenant |
| `PATCH /v1/strategies/{id}` | all | name/description/config; **only in `draft`** else 409 `STRATEGY_NOT_EDITABLE` |
| `POST /v1/strategies/{id}/transition` | all | `{target_state}`; §7 FSM; illegal → 409 `STRATEGY_ILLEGAL_TRANSITION` |
| `DELETE /v1/strategies/{id}` | all | archive (FSM → `archived`); not a hard delete |
| `GET /v1/strategies/templates` | all | list `{key, name, category, description}` |
| `POST /v1/strategies/templates/{key}/build` | all | `{underlying, expiry, atm_strike, width?}` → `StrategyConfig` |
| `POST /v1/strategies/analyze` | all / Pro | see below |

**`POST /v1/strategies/analyze`** `{config, target_date?, live?: bool}`:
- **Pure part (all tiers):** expiration payoff curve, breakevens, max P/L (with `unbounded`
  flags), net premium, risk/reward — from caller-supplied `entry_price`s. POP omitted unless
  live (needs IV).
- **Live part (`live:true` ⇒ requires `vol_surface`, else 402
  `ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO`):** pulls the Massive chain via `MarketService`,
  fills missing entry prices + per-leg IV, adds net Greeks, the target-date theoretical curve,
  and lognormal POP. Carries `data_provider:"massive"`, `model:"bsm"`, POP `approximate:true`.

### Error codes (align to §10 conventions)
| Condition | HTTP | Code |
|---|---|---|
| Invalid config / params | 400 | `VALIDATION_INVALID_PARAMETER` |
| Strategy absent / other tenant | 404 | `RESOURCE_NOT_FOUND` |
| Edit when not in draft | 409 | `STRATEGY_NOT_EDITABLE` (new) |
| Illegal FSM transition | 409 | `STRATEGY_ILLEGAL_TRANSITION` (new) |
| Free tier requests live analysis | 402 | `ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO` (existing) |

## Testing

**Pure unit tests** (`packages/core/tests/`):
- `state.py`: valid edges pass; illegal raise `IllegalTransition`; `archived` terminal.
- `payoff.py`: long call (max loss = premium, `unbounded_profit`), bull call spread (bounded;
  breakeven = long strike + net debit), iron condor (two breakevens, bounded), short put
  (`unbounded_loss`), covered call — all asserted against closed-form values. Target-date
  invariant: `eval_date==expiry` ⇒ equals expiration curve.
- `pop.py`: long-call POP == `P(S_T > breakeven)` (lognormal CDF); POP ∈ [0,1]; condor
  multi-interval sums.
- `aggregate.py`: straddle ≈ delta 0, positive gamma+vega; spreads net; equity → delta only.
- `templates.py`: each template emits the right legs; descriptors well-formed.

**API integration tests** (`tests/integration/`, Postgres+Redis, reusing the market slice's
stub `MarketService`/provider + `_make_pro` helper):
- CRUD: create→draft, get, list+cursor, PATCH (draft-only; 409 otherwise), transition (valid +
  illegal→409), archive. RLS: tenant B's strategy → 404 for tenant A.
- Templates: list + build returns legs.
- Analyze: free + supplied entry prices → 200 pure payoff (no live block); `live:true` free →
  402; `live:true` pro (stub provider) → 200 with net Greeks + target-date curve + POP.
- Validation: empty legs / missing strike → 400.

**Gates:** `uv run pytest` (core + integration, integration on the 55432 DB env) + `uvx ruff
check`, all green offline. Implemented via subagent-driven TDD.

## Out of scope
- React multi-leg builder UI (slice 7b).
- Execution: paper/live order placement, the OMS, broker adapters, promotion gates (§13 11–13).
- Monte-Carlo POP (step 10) and full margin/funds (OMS/risk slice).
- `str_`-prefixed external IDs (app-wide convention change, tracked separately).
- India (`market="IN"`) chains for live analysis — US/Massive only; `market` carried through.
