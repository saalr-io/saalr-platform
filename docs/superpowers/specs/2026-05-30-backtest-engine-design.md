# Backtest engine (8a) — rolling, model-priced — design

**Date:** 2026-05-30
**Slice:** LLD §13 step 8 — backtest engine + metrics. **Sub-slice 8a:** the compute engine + a
worker that runs a backtest by id and persists results (testable via CLI). **8b** (next) adds the
Redis queue + worker consume loop + the §5.3 POST(202)/GET-poll API.
**Status:** Approved design, pre-plan.
**Builds on:** the BSM `pricing` engine, the `strategies` leg types (7a), the `bars` hypertable
(ingestion), and the existing `Backtest` model.

## Purpose

Backtest a saved multi-leg strategy over a historical window and produce **honest, clearly
model-priced metrics**. We have underlying daily bars but no historical option prices, so option
legs are **BSM-modeled** from the bar path with IV from realized volatility. The result is a
defensible, caveated number — the validation-first point — not a fake-precise broker replay.

## Decisions (locked during brainstorming)

1. **Model-priced:** BSM per-leg pricing; **IV = trailing realized volatility** of the underlying
   (from bars). Flat risk-free rate; zero dividend yield (historical curves/divs unavailable).
2. **Rolling / recurring structure:** derive a relative template from the stored config and
   re-enter it each cycle, rolling at expiry across the window.
3. **Decomposed:** this is **8a** (engine + worker, run-by-id, persisted). **8b** = Redis queue +
   consume loop + async API.
4. **Honest labeling:** every result carries `model`, `iv_source`, model params, and
   `approximate: true`.

## Architecture

```
packages/core/saalr_core/backtest/      # PURE compute (stdlib + pricing + strategies.types)
  __init__.py
  metrics.py     # total/annualized return, sharpe, sortino, max_drawdown, win_rate, avg_trade_pnl
  vol.py         # realized_vol(closes, lookback) -> annualized stdev of log returns
  template.py    # RelativeTemplate: from_config(config, ref_spot, ref_date); instantiate(roll_date, spot)
  engine.py      # run_backtest_engine(closes, template, params) -> BacktestResult
apps/backtest-worker/
  pyproject.toml                         # dep: saalr-core
  backtest_worker/
    __init__.py  __main__.py
    repo.py      # get_strategy, load_underlying_closes, create_backtest, mark_running, save_result
    service.py   # run_backtest(sm, tenant_id, backtest_id); create_and_run(...) for CLI/tests
    cli.py       # backtest (create+run) / run (existing id)
packages/core/tests/  +  tests/integration/test_backtest.py
```

## Components

### `saalr_core/backtest/vol.py` (pure)
`realized_vol(closes: list[float], lookback: int) -> float` — annualized stdev (×√252) of the last
`lookback` daily log returns; returns a small floor (e.g. 0.01) if insufficient/degenerate data so
BSM never divides by zero.

### `saalr_core/backtest/metrics.py` (pure, no pandas)
From a daily equity series and a per-cycle P&L list:
- `total_return(equity)`, `annualized_return(equity, days)`, `sharpe(returns, rf, periods=252)`,
  `sortino(returns, rf, periods=252)`, `max_drawdown(equity)`, `win_rate(trade_pnls)`,
  `avg_trade_pnl(trade_pnls)`. All stdlib; guard empty/zero-variance series (return 0.0).

### `saalr_core/backtest/template.py` (pure)
- `RelativeLeg`: `{kind, option_type?, side, qty, moneyness?: float, dte?: int}` (option legs carry
  `moneyness = strike / ref_spot` and `dte = (expiry - ref_date).days`; equity legs carry `qty`;
  cash legs carry the collateral).
- `RelativeTemplate.from_config(config: StrategyConfig, ref_spot: float, ref_date: date)` →
  derives the relative legs, **preserving each leg's own `dte`** (no flattening). `cycle_dte` =
  **min** option-leg `dte` (the front expiry — see the engine's rolling logic). This supports
  calendars (same strike, different DTE) and diagonals (different strike *and* DTE); single-expiry
  structures fall out naturally (all DTEs equal → front == back).
- `instantiate(roll_date: date, spot: float, strike_increment: float = 1.0) -> list[Leg]` →
  concrete legs: option `strike = round(spot * moneyness / inc) * inc`, **`expiry = roll_date +
  leg.dte`** (per-leg); equity/cash unchanged. (Reuses `strategies.types` leg types.)

### `saalr_core/backtest/engine.py` (pure)
`run_backtest_engine(closes: dict[date, float], template: RelativeTemplate, params) -> BacktestResult`
where `params` = `{start, end, initial_capital, rate, vol_lookback, include_costs,
commission_per_contract, slippage_per_contract, strike_increment}`.

Algorithm:
1. Trading days = sorted `closes` keys within `[start, end]`.
2. Roll cycles from `start`: at each `roll_t`, `spot = closes[roll_t]`; `legs =
   template.instantiate(roll_t, spot)` (each option leg gets `expiry = roll_t + leg.dte`);
   `front_expiry = roll_t + cycle_dte` (the nearest leg expiry, clamped to ≤ end). Entry cost = Σ
   BSM(leg) at `roll_t` (σ = `realized_vol(closes up to roll_t, lookback)`, **per-leg**
   `t = leg.dte/365`, `rate`, `q=0`) ± costs.
3. For each trading day `d` in `(roll_t, front_expiry]`: position value = Σ BSM(leg, spot=closes[d],
   σ=realized_vol@d, **per-leg** `t = max(0, (leg.expiry − d).days)/365`) — a leg at or past its own
   expiry is valued at intrinsic; equity[d] = initial_capital + running_realized_pnl + (value −
   entry). Equity legs marked at the bar close; cash legs flat.
4. At `front_expiry`: realize the cycle P&L (settle − entry − costs) — front legs settle at
   intrinsic, longer-dated legs marked at BSM with their remaining time — append to `trade_pnls`,
   then **close and re-open the entire structure** into the next cycle at that day's spot. Stop at
   `end`.
5. Build the daily equity series and daily returns; compute metrics.

`BacktestResult` = `{metrics: {...§5.3 keys...}, trades: int, equity_points: int, model: "bsm",
iv_source: "realized_vol", rate, vol_lookback, approximate: True}`.

### `apps/backtest-worker/backtest_worker/`
- **`repo.py`**: `get_strategy(session, id)` (RLS-scoped); `load_underlying_closes(session, symbol,
  market, start, end, lookback)` → `dict[date, close]` from `bars` (loads from `start −
  lookback*~1.5 calendar days` to `end`; `bars` is non-RLS); `create_backtest(session, tenant_id,
  strategy_id, start, end, config_snapshot)` → `Backtest` row `status="queued"`, returns id;
  `mark_running(session, id)`; `save_result(session, id, metrics_json, status, error)`.
- **`service.py`**: `run_backtest(sessionmaker, tenant_id, backtest_id)` — open
  `tenant_session(sm, tenant_id)` (sets `app.current_tenant` for RLS), load the `Backtest` + its
  `Strategy`, parse `config_json` → `StrategyConfig`, pick the underlying = `config.underlying`,
  load closes, `ref_spot = closes[start]`, `template = RelativeTemplate.from_config(...)`, run the
  engine, `save_result(metrics_json=result, status="succeeded")`. On any error → `save_result(
  status="failed", error=str(exc))` and re-raise-or-log. `create_and_run(sm, tenant_id,
  strategy_id, params)` = create the row + `run_backtest`.
- **`cli.py`**: `backtest --strategy <id> --tenant <id> --start --end [--capital 100000 --rate 0.04
  --vol-lookback 20 --no-costs]` (create + run, print the metrics); `run --tenant <id>
  <backtest_id>`. Builds a core sessionmaker from `Settings` like ingest-worker.

### Persistence (existing `Backtest` model)
`status` queued→running→succeeded|failed; `metrics_json` = the result dict; `config_snapshot` =
`{config, params, engine_version}` (the §13.8 replay/seed/version metadata); `error_message` on
failure; `started_at`/`completed_at`. `trade_log_uri` stays null (trade count + avg P&L live in
`metrics_json`; a full trade-log file is a later concern).

## Model assumptions (honest, surfaced in every result)
- Option prices are **BSM-modeled**, not real marks. **IV = trailing realized vol** (`vol_lookback`,
  default 20). **Rate is flat** (default 0.04); **dividend yield 0**. Per-leg expiries are
  preserved (calendars/diagonals supported); each cycle holds to the **front** (nearest) leg expiry,
  then **closes and re-opens the whole structure** — continuous rolling of a short leg against a
  surviving long leg is not modeled. **Fixed size** (config leg qty/cycle), not capital-scaled.
  Strikes rounded to `strike_increment` (default $1). Each result carries
  `model/iv_source/rate/vol_lookback/approximate`.

## Error handling
- No bars for the underlying over the window, or `start`/`end` outside the bar range → the engine
  raises a clear error; `run_backtest` persists `status="failed"` + `error_message`.
- A structure with **no option legs** (pure equity) → clear error (no roll cycle to define);
  `status="failed"`. Structures that mix equity + option legs (e.g. covered calls) are fully
  supported — the equity leg is marked on bars while the option leg(s) drive the cycle.
- Degenerate vol (flat history) → `realized_vol` floors at a small value so BSM is finite.
- A cycle whose expiry exceeds `end` → truncated at `end` (settle at the last available mark).

## Testing
- **Pure** (`packages/core/tests/`): `metrics` (known equity/returns → expected sharpe/sortino/
  max_dd/total/annualized; win_rate/avg from a trade-pnl list; empty/zero-variance → 0.0);
  `vol` (known returns → expected annualized realized vol; insufficient data → floor); `template`
  (config → correct per-leg `moneyness`/`dte` + `cycle_dte` = min option DTE; `instantiate` →
  correct rounded strikes + **per-leg** `roll_date+leg.dte` expiries, incl. a calendar with two
  different DTEs); **`engine`** — deterministic synthetic `closes`: a long call on a **flat**
  underlying loses to theta (total_return < 0), on a **steadily rising** underlying profits
  (total_return > 0); a debit spread's loss is bounded; a **calendar** (short front / long back,
  same strike) on a flat underlying is net-positive (front decays faster than back) and cycles on
  the front expiry; metrics all finite; `trades` = number of completed cycles.
- **Integration** (`tests/integration/test_backtest.py`, 55432): seed a tenant + a `strategies`
  row + `bars` for its underlying (via admin/`tenant_session`), `create_and_run` →
  `Backtest.status == "succeeded"` with `metrics_json` populated (incl. `model/iv_source/
  approximate`); a strategy whose underlying has no bars → `status == "failed"` +
  `error_message`. RLS: the backtest is scoped to the seeding tenant.
- **CLI**: argparse parser smoke (no DB).
- **Gate**: `uv run pytest` (core + integration on the 55432 env) + `uvx ruff check`.

## Out of scope (→ 8b or later)
- Redis queue + the worker consume loop; the §5.3 POST(202)/GET-poll API + tier gating; a separate
  trade-log file/URI; capital-scaled position sizing; historical rate/dividend curves;
  transaction-cost calibration beyond a flat commission+slippage; continuous short-leg rolling
  against a surviving long leg (each front expiry closes and re-opens the full structure).
