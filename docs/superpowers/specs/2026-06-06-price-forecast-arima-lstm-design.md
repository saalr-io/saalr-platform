# Price Forecast (ARIMA + LSTM) — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorming)
**Slice:** Models → "Forecasts & simulation" — add a price/return forecast alongside the existing volatility forecast.

## Goal

Add a new **Price forecast** panel to the Models → Insights tab that trains **ARIMA** and
**LSTM** models (plus a naive baseline) on a ticker's price history and overlays their projected
close paths over a horizon, with walk-forward validation marking which model actually won on
backtest. Premium-gated (`ml_forecast`), Redis-cached, and framed honestly as educational.

## Context (existing design this builds on)

- `packages/ml/saalr_ml/` is deliberately **pure numpy + scipy** — GARCH(1,1) is hand-rolled
  (`garch.py`), no `statsmodels`/`torch`. The existing `vol_forecast` (`forecast.py`) predicts
  **annualized volatility %**, GARCH vs an HV21 baseline, picks a `primary` by walk-forward
  holdout, and reports honest validation metrics (lift, MAE) with an `approximate` chip.
- API: `apps/api/saalr_api/forecast/` — `router.py` exposes `GET /v1/market/vol-forecast`
  gated by `require_ml_forecast`; `service.py` caches in Redis and records
  `model_validation_runs` rows; `repo.load_closes` loads the daily close series.
- Frontend: `features/models/ForecastPanel.tsx` renders the vol forecast; `hooks.ts` has
  `useVolForecast`; `pages/Models.tsx` Insights tab loads it on "Load".

**Decisions locked during brainstorming:**
1. ARIMA + LSTM forecast **price/return direction** (a NEW panel), not volatility.
2. Implement with **real libraries**: `statsmodels` (ARIMA) + `torch` (LSTM). Heavy deps and
   per-request training are accepted; mitigated by caching, bounded LSTM size, thread-offload,
   and seeding for determinism.
3. The panel shows **all three models together** (ARIMA, LSTM, naive) with a `primary` marked by
   walk-forward holdout — mirroring the GARCH/HV21 vol panel.

## Architecture

```
saalr_ml (pure fns)                 forecast API                      web
─────────────────                   ────────────                      ───
arima.py   ─┐                       price_service.py ──> /v1/market/   lib/models.ts (types+fetch)
lstm.py    ─┼─> price_forecast.py ──> get_or_compute     price-       hooks.ts (usePriceForecast)
            │   (orchestrator +        (+Redis cache,     forecast     PriceForecastPanel.tsx
naive (in   │    walk-forward)         model_validation,  (gated)      Models.tsx (wire under
price_fc)  ─┘                          to_thread)                       ForecastPanel)
```

### Modeling conventions

- **Target:** model log-returns / log-price; reconstruct a **price (close) path** of length
  `horizon` for display. `last_close` anchors all paths.
- **ARIMA:** fit on `log(close)`; auto-select order by AIC over a small grid p,d,q ∈
  {0,1,2}×{0,1}×{0,1}. Forecast mean + analytic 95% prediction interval via
  `get_forecast(horizon)`; exponentiate back to price. Returns `(path, ci95, order)`.
- **LSTM:** train on standardized log-returns with a sliding window (lookback ≈ 20), 1 layer,
  hidden ≈ 16, bounded epochs (≤ 150), fixed lr, `torch.manual_seed(seed)` +
  `torch.set_num_threads` small. Predict returns iteratively for `horizon` steps; compound from
  `last_close` to a price path. 95% band from bootstrapped training residuals (quantiles),
  reconstructed to price. Returns `(path, ci95)`.
- **Naive baseline:** random-walk-with-drift — `drift = mean(log returns)`,
  `path[i] = last_close * exp(drift * (i+1))`. `ci_95 = null`. The honesty yardstick.
- **History minimum:** reuse 250 closes; `< 250` raises `ValueError` (→ 422), consistent with
  `vol_forecast`.

### Walk-forward validation (multi-origin)

Rolling multi-origin holdout over the last `holdout_days` (≈ 60). Choose `n_origins` (≈ 5)
evenly-spaced origins inside the holdout window; at each origin, train each model on data up to
that origin and forecast `horizon` (or to the window end, whichever is shorter) ahead, scoring
against realized closes. Per model, aggregate across origins into a mean **MAE on price** and mean
**directional accuracy** (sign of cumulative move vs realized). `primary` = lowest mean MAE.

Cost note: ARIMA/naive refit cheaply, so the LSTM dominates — `n_origins + 1` LSTM fits per
cache-miss (one per origin + the final full fit for the live forecast). `n_origins` is bounded
(≈ 5) and epochs stay capped; combined with the 6h cache and `asyncio.to_thread` offload this
keeps a cold request to a few seconds. `n_origins`/`holdout_days` are parameters on
`price_forecast(...)` so tests can shrink them.

## Components / files

### Backend — `saalr_ml`
- **Create** `packages/ml/saalr_ml/arima.py` — `arima_forecast(log_closes, horizon) -> (list[float] path, list[[lo,hi]] ci95, tuple order)`.
- **Create** `packages/ml/saalr_ml/lstm.py` — `lstm_forecast(returns, horizon, last_close, seed=0, epochs=150) -> (list[float] path, list[[lo,hi]] ci95)`.
- **Create** `packages/ml/saalr_ml/price_forecast.py` — `price_forecast(closes, horizon, holdout_days=60, n_origins=5, seed=0) -> dict` (orchestrator + naive + multi-origin walk-forward + primary selection).
- **Modify** `packages/ml/pyproject.toml` — add `statsmodels>=0.14`, `torch>=2.2`.

### Backend — API (`apps/api/saalr_api/forecast/`)
- **Create** `price_service.py` — `get_or_compute_price_forecast(redis, sessionmaker, session, ticker, market, horizon, ttl, *, closes=None) -> dict`. Redis key `mdq:pricefc:v1:{market}:{ticker}:{horizon}`; the CPU-bound `price_forecast(...)` runs via `asyncio.to_thread`; persists `model_validation_runs` rows (`model_name` ∈ {arima, lstm}, baseline `naive`); caches with `ttl`.
- **Modify** `router.py` — add `GET /v1/market/price-forecast` (`ticker`, `market=US`, `horizon: int = Query(10, ge=1, le=30)`), `Depends(require_ml_forecast)`, reuse `_validate`, map `ValueError` → 422 `INSUFFICIENT_HISTORY`. Reuse `request.app.state.vol_forecast_ttl`.

### Frontend (`apps/web/src`)
- **Modify** `lib/models.ts` — `PriceForecast` + `PriceModel` types; `fetchPriceForecast(ticker, horizon)` (reuse `EntitlementError` mapping).
- **Modify** `features/models/hooks.ts` — `usePriceForecast(ticker, horizon, enabled)`.
- **Create** `features/models/PriceForecastPanel.tsx` — multi-line SVG overlay **with axes**
  (step/day × price), legend (arima/lstm/naive), band on the `primary`, a one-line directional
  read (e.g. "ARIMA leans +2.3% / 10d · naive wins backtest"), `approximate` + disclaimer chips,
  per-model holdout MAE + directional accuracy. `data-testid="price-forecast-panel"`.
- **Create** `features/models/PriceForecastPanel.test.tsx`.
- **Modify** `pages/Models.tsx` — Insights tab renders `<PriceForecastPanel>` under
  `<ForecastPanel>`, driven by the same `ticker`/`horizon`; loads on "Load" when entitled.

## Payload shape

```json
{
  "ticker": "AAPL", "market": "US", "as_of": "2026-06-06T…Z",
  "horizon_days": 10, "last_close": 187.42, "primary_model": "naive",
  "models": [
    { "model": "arima", "path": [187.6, …], "ci_95": [[185.1, 190.2], …],
      "expected_return_pct": 2.31, "direction": "up",
      "holdout_mae": 3.12, "directional_accuracy": 0.55 },
    { "model": "lstm",  "path": […], "ci_95": [[…]], "expected_return_pct": -0.4,
      "direction": "down", "holdout_mae": 3.88, "directional_accuracy": 0.50 },
    { "model": "naive", "path": […], "ci_95": null, "expected_return_pct": 0.6,
      "direction": "up", "holdout_mae": 2.97, "directional_accuracy": 0.52 }
  ],
  "validation": { "holdout_days": 60, "n_origins": 5, "best_model": "naive" },
  "approximate": true,
  "disclaimer": "Educational. Daily price direction is near-random; the naive baseline often wins."
}
```

## Error handling

| Condition | Status | Code |
|---|---|---|
| ticker non-alpha / empty | 404 | `RESOURCE_NOT_FOUND` |
| market ≠ US | 400 | `VALIDATION_INVALID_PARAMETER` |
| `< 250` closes | 422 | `INSUFFICIENT_HISTORY` |
| not premium | 402 | entitlement error (via `require_ml_forecast`) |

Frontend reuses `forecastError(err)` mapping (insufficient history, unknown ticker, generic) and
the `EntitlementError → ModelsGate` path already in `Models.tsx`.

## Performance / honesty guardrails

- **Cache** results 6h (`vol_forecast_cache_ttl_seconds`); the LSTM only trains on cache-miss.
- **Bound** the LSTM (hidden ≈ 16, 1 layer, epochs ≤ 150, lookback ≈ 20, few threads) and the
  multi-origin validation (`n_origins` ≈ 5 ⇒ `n_origins + 1` LSTM fits per cache-miss).
- **Offload** `price_forecast(...)` via `asyncio.to_thread` so torch training never blocks the
  event loop.
- **Determinism:** seed torch + numpy ⇒ reproducible paths and reproducible tests.
- **Honesty:** naive overlay + walk-forward + directional accuracy + `approximate`/disclaimer
  chips, consistent with the platform's existing posture.

## Testing

- `packages/ml/tests/test_price_forecast.py` — path length == horizon; all finite; determinism
  (same seed ⇒ identical LSTM path); `< 250` raises `ValueError`; naive drift correctness;
  `primary` == lowest mean holdout MAE across origins on a synthetic trend+noise series; the
  multi-origin scorer produces one mean MAE + directional accuracy per model. LSTM uses tiny
  epochs and tests shrink `n_origins`/`holdout_days` for speed.
- `tests/integration/test_price_forecast.py` — 402 for free; 200 for premium with arima+lstm+naive
  all present and `len(path)==horizon`; 422 on short history; second call served from cache.
- `apps/web/src/features/models/PriceForecastPanel.test.tsx` — renders three model paths + legend
  + axes; shows the primary band and the directional read.

## Out of scope (YAGNI)

- Exogenous regressors, multivariate models, GPU training.
- Persisting trained model artifacts (retrain on cache-miss).
- Intraday / non-US markets.
