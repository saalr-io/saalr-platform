# Models frontend (AN-2) — design

**Status:** approved design, 2026-06-04. Slice **AN-2** of the analytics-frontends band
(AN-1 Markets & Vol + AN-3 Portfolio shipped; AN-4 Dashboard remains).

## Goal

Replace the `Models` placeholder at `/app/models` with the ML surface over the three
`ml_forecast`-gated endpoints: a ticker-driven **Insights** view (GARCH vol-forecast +
sentiment) and a **Monte-Carlo** tab (ready-made template → strategy config → POP / EV /
P&L histogram). Brand-defining honesty: surface the walk-forward holdout that picks the
primary forecast, the GARCH-vs-baseline lift, and the `approximate` flags.

## Backends consumed (bearer-authed; base `import.meta.env.VITE_API_BASE_URL ?? '/api'`; all `ml_forecast`-gated → 402)

- `GET /v1/market/vol-forecast?ticker=&market=US&horizon=` (horizon 1–30, default 10) →
  ```
  {
    horizon_days, primary_model: 'garch'|'hv21',
    primary_forecast: number[],            // annualized vol %, length = horizon_days
    primary_ci_95: [number, number][] | null,   // [lo, hi] per day; null for hv21
    alternative_models: [{ model, forecast: number[], status: 'baseline'|'underperforming_baseline', delta_mae_vs_baseline }],
    validation: { holdout_days, garch_mae, hv21_mae, lift },
    model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true,
    params: { omega, alpha, beta }
  }
  ```
  422 `INSUFFICIENT_HISTORY` (<250 bars); 404 `RESOURCE_NOT_FOUND` (non-alpha ticker);
  400 `VALIDATION_INVALID_PARAMETER` (market ≠ US).
- `GET /v1/market/sentiment?ticker=&market=US` →
  `{ ticker, market, score: -1..1, label: 'bearish'|'neutral'|'bullish', confident: bool,
  n_headlines: int, has_data: bool, computed_at: string|null, as_of: string|null }`.
  When the worker has no rows for the ticker: `has_data:false, score:0, label:'neutral',
  confident:false, n_headlines:0, computed_at:null, as_of:null` (200, **not** an error).
  Same 404/400 guards as forecast.
- `POST /v1/strategies/montecarlo` body
  `{ config: StrategyConfig, market:'US', sigma?:number>0, paths:int (1–200000, default 10000),
  seed:int, use_sentiment:bool }` →
  ```
  {
    pop, ev, paths,
    histogram: { counts: int[], bin_edges: number[] },   // len(bin_edges) = len(counts)+1
    percentiles: { p5, p50, p95 },
    max_profit_observed, max_loss_observed,
    model:'gbm_mc', approximate:true, seed,
    underlying, market, spot, sigma,
    sigma_source: 'override'|'garch', horizon_days, rate,
    sentiment: { applied:bool, reason?:string, score?, label?, computed_at? }
  }
  ```
  422 `VALIDATION_NO_EXPIRY` (no future option leg), 422 `INSUFFICIENT_HISTORY`
  (σ from GARCH needs ≥250 bars), 400 `VALIDATION_INVALID_PARAMETER`.

Reused from `lib/strategies.ts` (already shipped with the builder): `listTemplates()` →
`TemplateDescriptor[]`, `buildTemplate(key, { underlying, expiry, atm_strike, width? })` →
`StrategyConfig`, and the `StrategyConfig`/`Leg` types. The `<TemplatePicker>` component
(`features/strategies/TemplatePicker.tsx`, props `{ underlying, expiry, atmStrike, onApply }`)
is reused directly for the MC config — no new template UI.

## Decisions (locked)

- **Monte-Carlo strategy input = ready-made templates.** Reuse `<TemplatePicker>`: the user
  enters underlying + expiry + ATM strike, picks a template, and `onApply` yields a
  `StrategyConfig` that MC runs on. Saved-strategy input is deferred.
- **Layout = ticker Insights view + a separate Monte-Carlo tab.** Two tabs: **Insights**
  (one ticker input + horizon selector driving both the forecast curve and the sentiment
  gauge) and **Monte-Carlo**. Fewer ticker inputs, tighter story than three independent tabs.
- **Honesty is foregrounded.** The forecast panel shows which model won the walk-forward
  (`primary_model`), the `lift`, both MAEs, the GARCH params, and the `approximate` tag; the
  alternative model's `status` distinguishes "baseline" from "underperforming_baseline".
- **Entitlement pre-check** (no wasted 402): `me.entitlements.ml_forecast === true` →
  `ModelsGate`; hooks are still called unconditionally before the early return (Rules of
  Hooks), with `enabled` gated so a free user fetches nothing. An `EntitlementError` from any
  query also routes to the gate.
- **Custom SVG charts** (no charting lib; AN-1 Payoff/IvCurves convention — SVG stroke/fill
  HEX literals allowed, only Tailwind *class* colors must be theme tokens).

## Components / files

- **`src/lib/models.ts`** — client over a local `request()` wrapper (same shape as
  `lib/market.ts`: 401→`setToken(null)`+throw, 402→`EntitlementError(code)`, else
  `Error(code)`; reuses `BASE`/`authHeaders` from `lib/api.ts` and re-exports
  `EntitlementError` from `lib/strategies.ts` to keep one class):
  - `getVolForecast(ticker: string, horizon: number): Promise<VolForecast>`
    → `GET /v1/market/vol-forecast?ticker=&market=US&horizon=`
  - `getSentiment(ticker: string): Promise<Sentiment>` → `GET /v1/market/sentiment?ticker=&market=US`
  - `runMonteCarlo(body: MonteCarloRequest): Promise<MonteCarloResult>` → `POST /v1/strategies/montecarlo`
  - Types `VolForecast`, `Sentiment`, `MonteCarloRequest` (`{ config: StrategyConfig; market?: string;
    sigma?: number; paths?: number; seed?: number; use_sentiment?: boolean }`), `MonteCarloResult`.
- **`src/features/models/hooks.ts`** — `useVolForecast(ticker, horizon, enabled)`
  (key `['vol-forecast', ticker, horizon]`, `enabled: enabled && !!ticker`, `retry:false`),
  `useSentiment(ticker, enabled)` (key `['sentiment', ticker]`, same enable, `retry:false`),
  `useMonteCarlo()` (mutation `runMonteCarlo`, no invalidation — pure compute).
- **`src/features/models/ForecastPanel.tsx`** — props `{ forecast: VolForecast }`. Custom
  SVG: x = day index 1…horizon, y = annualized vol %; a primary polyline
  (`data-testid="forecast-line"`, points length = horizon) and, when `primary_ci_95` is
  non-null, a shaded band polygon (`data-testid="forecast-ci"`) from the lo/hi pairs. An
  honesty row: `primary_model` badge, `lift` (×), `garch_mae` vs `hv21_mae`, params
  ω/α/β, the alternative model's `status`, and an `approximate` tag.
- **`src/features/models/SentimentGauge.tsx`** — props `{ sentiment: Sentiment }`. If
  `!has_data` → `data-testid="sentiment-empty"` "No sentiment coverage yet." Otherwise a
  horizontal −1…+1 meter with a marker (`data-testid="sentiment-marker"`) positioned at
  `(score + 1) / 2`, the `label` (colored bearish→neg / neutral→warn / bullish→pos),
  `confident` flag, `n_headlines`, and `as_of` freshness.
- **`src/features/models/MonteCarloPanel.tsx`** — props `{ result: MonteCarloResult }`. SVG
  histogram: one bar per `counts[i]` spanning `bin_edges[i]..bin_edges[i+1]`, colored
  `fill` pos/neg by whether the bin's midpoint ≥ 0, with a zero reference line
  (`data-testid="mc-histogram"`, bar count = `counts.length`). A stats block: POP %, EV,
  p5/p50/p95, max profit/loss, a `sigma_source` badge (override|garch), a sentiment note
  (applied → score/label; else the `reason`), and spot/horizon_days/rate meta.
- **`src/features/models/ModelsGate.tsx`** — `ml_forecast` upgrade nudge with a
  `<Link to="/billing?plan=pro">` CTA (mirrors `MarketsGate`).
- **`src/pages/Models.tsx`** — owns hooks/state. A `// Models` kicker + `h2`. Pre-checks
  entitlement → `ModelsGate`. Tabs **Insights | Monte-Carlo**:
  - **Insights:** a ticker input (uppercased, Enter or Load) + a horizon `<select>`
    (10/20/30, default 10). On load sets `ticker`; `useVolForecast`/`useSentiment` fire.
    Renders a loading skeleton, an inline error (INSUFFICIENT_HISTORY / RESOURCE_NOT_FOUND /
    generic), then `<ForecastPanel>` + `<SentimentGauge>` side by side.
  - **Monte-Carlo:** underlying / expiry / ATM-strike inputs feed `<TemplatePicker>`; its
    `onApply(config)` stores the config (show a one-line summary of legs). Controls: paths
    (default 10000) and a `use_sentiment` checkbox. A Run button (disabled until a config
    exists, disabled-while-pending) calls `useMonteCarlo.mutate`. Renders the MC error or
    `<MonteCarloPanel>`.
- **`src/app/Router.tsx`** — replace `<Route path="models" element={<PlaceholderPage title="Models" />} />`
  with `<Route path="models" element={<Models />} />` + import (PlaceholderPage stays — still
  used by the dashboard route until AN-4).

## Data flow

Insights: ticker + horizon → `useVolForecast` + `useSentiment` (both `enabled` only when
entitled and a ticker is set). The two render independently — a sentiment `has_data:false`
empty card coexists with a real forecast. Monte-Carlo: underlying/expiry/ATM → `buildTemplate`
(via `TemplatePicker`) → `StrategyConfig` held in page state → on Run, `runMonteCarlo({ config,
paths, use_sentiment })` → `<MonteCarloPanel>`. σ defaults to GARCH server-side (no client σ
override in v1); `use_sentiment` lets Premium-grade sentiment shift the drift (server decides
applicability and reports it in `sentiment`).

## Error handling

- Not entitled (pre-check or `EntitlementError`) → `ModelsGate`.
- Forecast/MC 422 `INSUFFICIENT_HISTORY` → "Not enough price history for {ticker} (need 250+
  trading days)."
- 404 `RESOURCE_NOT_FOUND` → "Unknown ticker."
- MC 422 `VALIDATION_NO_EXPIRY` → "Pick a template with an option expiry in the future."
- Sentiment `has_data:false` → the empty card (handled in the component, not an error).
- Provider/unknown (`MARKET_DATA_PROVIDER_UNAVAILABLE`, 503/502) → plain `Error(code)` →
  "Something went wrong — try again."

## Testing (vitest + @testing-library/react; mock the `models` module or `fetch`; `MemoryRouter` where a Link is used)

- `src/lib/models.test.ts` — each method's URL/method/query; `runMonteCarlo` POSTs the body;
  a 402 throws `EntitlementError`; a 422 throws `Error('INSUFFICIENT_HISTORY')`.
- `ForecastPanel.test.tsx` — `forecast-line` has `horizon_days` points; `forecast-ci` present
  when `primary_ci_95` given and absent when null (hv21 primary); shows `primary_model` + the
  `lift`; renders the `approximate` tag.
- `SentimentGauge.test.tsx` — bullish score → marker past mid + `bullish` label; bearish →
  before mid + `bearish`; `has_data:false` → `sentiment-empty`.
- `MonteCarloPanel.test.tsx` — renders POP/EV/percentiles; `mc-histogram` bar count =
  `counts.length`; `sigma_source` badge; sentiment-applied note vs reason.
- `Models.test.tsx` — no `ml_forecast` → `ModelsGate` (no fetch); with entitlement, load a
  ticker → forecast + sentiment render (mock both); switch to Monte-Carlo, apply a template
  (mock `buildTemplate`), Run (mock `runMonteCarlo`) → `<MonteCarloPanel>` shows.
- Gate: `npm run typecheck && npm run lint && npm run test:run` (all green); `npm run build`
  still prerenders 17 docs (client-only `/app` route).

## Out of scope (later)

Saved-strategy MC input (templates only for v1); client-side σ override input; a
forecast-vs-realized backtest overlay; news-headline drill-in beneath the sentiment gauge;
multi-ticker compare; AN-4 Dashboard aggregation of these panels.
