# Backtest screen (`/app/backtests`) — design

**Status:** approved design, 2026-06-05.

## Goal

A dedicated `/app/backtests` page to run a historical, model-priced backtest on a **saved strategy**
and view the resulting **equity curve + metrics**. The backtest engine, async API, and Redis-Streams
worker already exist; this slice adds the missing UI plus a small backend change to expose the daily
equity series (computed today but discarded). Backtest is **auth-only — no entitlement gate**.

## Backend contract (current + the one change)

- **`POST /v1/strategies/{strategy_id}/backtest`** — body `BacktestRequest {start_date, end_date,
  initial_capital=100000, include_costs=true}` (validator: `end_date > start_date`) + optional
  `Idempotency-Key` header → **202** `{backtest_id, status:'queued', estimated_duration_seconds,
  poll_url}`. 404 `RESOURCE_NOT_FOUND` (no such strategy); 503 `BACKTEST_ENQUEUE_FAILED`.
- **`GET /v1/backtests/{backtest_id}`** → `{backtest_id, status}` where status ∈
  `queued|running|succeeded|failed`. `succeeded` → `+ {metrics, trade_log_url:null}`; `failed` →
  `+ {error:{code:'BACKTEST_FAILED', message}}`.
- `metrics` keys (from `run_backtest_engine`): `total_return, annualized_return, sharpe, sortino,
  max_drawdown, win_rate, trades, avg_trade_pnl`. The engine result also carries `model:'bsm',
  iv_source:'realized_vol', rate, vol_lookback, include_costs, approximate:true, equity_points,
  start, end, initial_capital, final_equity` — all persisted in `metrics_json`.

### The one backend change — expose the daily equity series

The engine (`packages/core/saalr_core/backtest/engine.py`) builds `equity_curve: list[float]` in the
`for d in sim_days` loop (line ~121) where the date `d` is in scope, but only returns
`equity_points` (count) + `final_equity`. Add a parallel series:

- Keep `equity_curve: list[float]` for the metrics math (untouched). Alongside the
  `equity_curve.append(...)`, append to a new `equity_series: list[dict]` →
  `{"date": d.isoformat(), "equity": value}`.
- Add `"equity_series": equity_series` to the returned result dict (so it lands in `metrics_json`).
- **`apps/api/saalr_api/backtests/router.py`** — in the `succeeded` branch of the GET, add
  `out["equity_series"] = (row.metrics_json or {}).get("equity_series", [])`.

(No new endpoint, no schema/migration change — `metrics_json` is a JSONB blob.)

## Frontend — the dedicated page

- **`src/lib/backtests.ts`** — client over a `request()` wrapper (same shape as `lib/market.ts`:
  401→logout, 402→`EntitlementError` [unused here], else `Error(code)`; reuses `BASE`/`authHeaders`):
  - `createBacktest(strategyId, body, idempotencyKey)` → `POST /v1/strategies/${id}/backtest`
    (Idempotency-Key header) → `BacktestRun = {backtest_id, status, estimated_duration_seconds, poll_url}`.
  - `getBacktest(id)` → `GET /v1/backtests/${id}` → `BacktestResult = {backtest_id, status,
    metrics?: BacktestMetrics, equity_series?: EquityPoint[], error?: {code,message}}`.
  - Types `BacktestMetrics` (the 8 keys above + accepts the extra honesty fields), `EquityPoint
    {date:string; equity:number}`, `BacktestRequestBody {start_date, end_date, initial_capital,
    include_costs}`.
- **`src/features/backtests/hooks.ts`** — `useCreateBacktest()` (mutation), `useBacktest(id)`
  (`useQuery`, `enabled:!!id`, `retry:false`, **`refetchInterval` returns `false` when
  `status==='succeeded'||'failed'`, else `2000`** — mirrors `features/research/hooks.useNote`).
  Reuses `useStrategies()` from `features/strategies/hooks` for the saved-strategy list.
- **Pure components** in `src/features/backtests/`:
  - `StrategyPicker` — props `{strategies, value, onChange}`; a `<select>` of saved strategies
    (`strategy_id` + name); empty → a prompt linking to `/app/strategies` to build/save one first.
  - `BacktestForm` — props `{disabled, pending, onSubmit}`; start/end date inputs (defaults ≈ today−2y
    → today), initial-capital input (default 100000), `include_costs` checkbox (default on); submit
    builds the body + a `crypto.randomUUID()` idempotency key; disabled until valid (end>start, a
    strategy picked) and **disabled-while-pending** (double-submit guard).
  - `EquityCurve` *(custom SVG)* — props `{series: EquityPoint[]; initialCapital: number}`; a polyline
    over `series` (x = index, y = equity), a dashed baseline at `initialCapital`, hex stroke literals
    (PayoffChart convention); `data-testid="equity-curve"`/`equity-line`.
  - `MetricsPanel` — props `{metrics, finalEquity, approximate, model, volLookback}`; tiles for total &
    annualized return (× 100 → %), Sharpe, Sortino, max-drawdown (% — it's a fraction), win-rate (%),
    trades, avg-trade-PnL ($), final equity ($); a `model bsm · approximate · vol N` honesty row.
  - `BacktestStatus` — props `{status, estSeconds, error}`; `queued`/`running` → a skeleton + "≈ Ns";
    `failed` → the `BACKTEST_FAILED` message (e.g. "no bars for SPY").
- **`src/pages/Backtests.tsx`** — owns hooks/state: `useStrategies` → `StrategyPicker`; `BacktestForm`
  → `useCreateBacktest.mutate` → stores `backtest_id`; `useBacktest(backtest_id)` polls; render
  `BacktestStatus` until terminal, then `<EquityCurve>` + `<MetricsPanel>` on `succeeded` (or the error
  on `failed`). A `// Backtest` kicker + `h2`.
- **`src/app/Router.tsx`** — add `<Route path="backtests" element={<Backtests />} />` + import.
- **`src/components/Sidebar.tsx`** — add a "Backtests" nav link (follow the existing link pattern).

## Data flow

Pick a saved strategy → set dates/capital/costs → submit → `202 {backtest_id}` → poll
`GET /v1/backtests/{id}` every 2 s until `succeeded`/`failed` → render the equity curve + metrics (or
the failure). The running backtest worker executes the job; with SPY data loaded, a SPY-based saved
strategy yields a real result. Numbers are **fractions on the wire** for returns/drawdown/win-rate
(× 100 for display); Sharpe/Sortino are ratios; avg-trade-PnL / final-equity are dollars.

## Error handling

No saved strategies → the picker's "create a strategy first" prompt (no run possible). `failed` →
the inline `BACKTEST_FAILED` message (commonly "no bars for SYMBOL" when the underlying isn't
ingested). 404 on a stale `backtest_id` → a "run not found" state. 503 enqueue-failed → "couldn't
start the backtest — try again". Backtest is ungated, so there is no 402 path. Money/metric fields are
JSON numbers (not Decimal strings) — no string coercion.

## Testing

- **Backend:** the engine test asserts the result now includes `equity_series` (length =
  `equity_points`, dates ISO + non-decreasing); the backtest API/poll test asserts the `succeeded`
  GET payload includes `equity_series` alongside `metrics`. Existing backtest tests stay green.
- **Frontend (vitest + RTL):** `backtests.test.ts` (URLs/methods, the Idempotency-Key header, the
  202 shape, the succeeded GET with `equity_series`); `EquityCurve.test.tsx` (N points, baseline);
  `MetricsPanel.test.tsx` (% formatting + the approximate chip); `BacktestStatus.test.tsx`
  (running vs failed); `Backtests.test.tsx` (mock `lib/strategies` + `lib/backtests`: pick a strategy
  → run → poll resolves succeeded → curve + metrics render; empty-strategies prompt).
- Gate: `npm run typecheck && npm run lint && npm run test:run` (web) + the Python suite (engine/API);
  `npm run build` still prerenders 47 SSG docs (`/app/backtests` is client-only). The local stack is
  running, so an end-to-end SPY backtest can be exercised after the build.

## Out of scope (later)

The trade-log table (`trade_log_url` is still null backend-side); a persisted run-history rail (each
visit runs fresh — no list-my-backtests endpoint exists); a benchmark overlay (SPY buy-and-hold);
multi-strategy comparison; CSV export; per-leg attribution.
