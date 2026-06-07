# Forecasts & Simulation: Price Forecast (ARIMA + LSTM) + HAR-RV — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorming)
**Slice:** Models → "Forecasts & simulation" — two cohesive feature areas, both shipping today:
- **Feature A** — a NEW **Price forecast** panel (ARIMA + LSTM + naive baseline) for the underlying.
- **Feature B** — add a **HAR-RV** model to the EXISTING volatility forecast (beside GARCH/HV21).

Plus a documented **Future work (parked)** section for the heavier options-ML wins.

## Goal

1. **Feature A:** Add a new **Price forecast** panel to the Models → Insights tab that trains
   **ARIMA** and **LSTM** models (plus a naive baseline) on a ticker's price history and overlays
   their projected close paths over a horizon, with multi-origin walk-forward validation marking
   which model actually won on backtest.
2. **Feature B:** Add **HAR-RV** (Corsi's Heterogeneous AutoRegressive realized-variance model) as
   a third model in the existing volatility forecast, joining the GARCH-vs-HV21 walk-forward so the
   `primary` can be any of the three.

Both premium-gated (`ml_forecast`), Redis-cached, and framed honestly as educational/approximate.

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

---

# Feature A — Price forecast panel (ARIMA + LSTM)

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

---

# Feature B — HAR-RV volatility model (extends the existing vol forecast)

## What it adds

HAR-RV (Corsi 2009) regresses next-day realized variance on its own **daily / weekly (5d) /
monthly (22d)** averages — a 4-coefficient OLS (intercept + 3 lags), pure-numpy
(`np.linalg.lstsq`), **no new deps**. It joins GARCH and HV21 as a third candidate in the existing
`vol_forecast`; the walk-forward holdout scores all three and `primary` becomes the best of them.

**Honesty caveat:** canonical HAR uses *intraday* realized variance; we only store daily closes,
so daily realized variance is proxied by squared scaled log-returns (`rv_t = r_t²`, the SAME proxy
`walk_forward` already uses as its realized target), smoothed by the d/w/m averaging. A legitimate,
common daily-data variant — noisier than true HAR — and it inherits the panel's existing
`approximate` chip.

## Modeling conventions (consistent with the existing vol forecast)

- **Realized-variance proxy:** `rv = returns²` where `returns` are the existing scaled log-returns
  (`_SCALE = 100`). Same units as GARCH/HV21 internals.
- **Features at day t:** `rv_d = rv[t-1]`, `rv_w = mean(rv[t-5:t])`, `rv_m = mean(rv[t-22:t])`;
  target `rv[t]`. Fit `β` by OLS over all valid rows (needs ≥ 22 trailing days).
- **Forecast path:** iterate the HAR recursion forward `horizon` steps (feed each predicted `rv`
  back into the daily lag and roll the 5d/22d means), then annualize each step to **vol percent**:
  `sqrt(rv_fc * 252)` — matching `garch_path`/`hv_path` units so it overlays cleanly.
- **No CI band** for HAR (point path only), like HV21.

## Components / files

### Backend — `saalr_ml`
- **Create** `packages/ml/saalr_ml/har.py` —
  - `fit_har(rv: np.ndarray) -> np.ndarray` (returns the 4 OLS coefficients).
  - `har_one_step(rv_history: np.ndarray, beta) -> float` (next-day variance; used by walk-forward).
  - `har_rv_forecast(returns: np.ndarray, horizon: int) -> list[float]` (annualized vol-percent path).
- **Modify** `packages/ml/saalr_ml/evaluate.py` — extend `WalkForward` with `har_mae: float`; in
  `walk_forward`, score HAR one-step-ahead variance across the holdout (same `realized = resid²`
  target as GARCH/HV21); set `primary = argmin` over `{garch, hv21, har}`. Bump the minimum-history
  guard to `holdout_days + 22` (monthly lag). Leave `lift` unchanged
  (`(hv21_mae − garch_mae) / hv21_mae`) so existing tests/semantics hold; HAR is judged purely by
  `har_mae` and the `primary` selection.
- **Modify** `packages/ml/saalr_ml/forecast.py` — add `"har"` to the `forecasts` dict
  (`(har_path, None)`), include it in `alternative_models` when not primary, and add
  `validation.har_mae`. `alternative_models` may now hold up to **two** entries.

### Backend — API
- **Modify** `apps/api/saalr_api/forecast/service.py` — `record_validation` already keys on
  `result["primary_model"]`; no signature change. (HAR rides the existing `/v1/market/vol-forecast`
  endpoint and Redis cache; payload simply gains a model.)

### Frontend (`apps/web/src`)
- **Modify** `lib/models.ts` — `VolForecast.validation` gains optional `har_mae?: number`;
  `alternative_models` already typed as an array (now 0–2 entries).
- **Modify** `features/models/ForecastPanel.tsx` — render the `har MAE` validation row when present
  and map over **all** `alternative_models` (today it shows only `[0]`); `primary` badge already
  data-driven so "har" displays without further change.
- **Modify** `features/models/ForecastPanel.test.tsx` — cover a `primary: "har"` payload with two
  alternatives and the `har_mae` row.

## Payload delta (vol forecast)

```jsonc
// existing /v1/market/vol-forecast response, additively:
{
  "primary_model": "har",                       // now one of garch | hv21 | har
  "primary_forecast": [22.1, 22.3, …],
  "alternative_models": [                        // 0–2 entries
    { "model": "garch", "forecast": […], "status": "underperforming_baseline", "delta_mae_vs_baseline": … },
    { "model": "hv21",  "forecast": […], "status": "baseline" }
  ],
  "validation": { "holdout_days": 40, "garch_mae": …, "hv21_mae": …, "har_mae": …, "lift": … }
}
```

## Testing (Feature B)

- `packages/ml/tests/test_har.py` — `fit_har` recovers known coefficients on a synthetic
  AR-in-variance series; `har_rv_forecast` returns a horizon-length, all-finite, positive vol path;
  raises/handles too-short input.
- Extend `packages/ml/tests/test_forecast.py` / `test_evaluate.py` — `vol_forecast` output contains
  a HAR forecast; `walk_forward` returns `har_mae` and can pick `primary == "har"` on a series HAR
  fits best.
- Extend `tests/integration/test_vol_forecast.py` — response includes a HAR entry (primary or
  alternative) and `validation.har_mae`.
- Extend `ForecastPanel.test.tsx` — primary "har" + two alternatives render; `har MAE` row shows.

---

# Future work (parked — NOT built today)

Documented so we can scope them as their own slices later. Both are higher-leverage for an options
platform but carry real cost:

- **Deep hedging** (Buehler et al.) — a NN/RL policy that learns to hedge an option (or a strategy)
  under transaction costs and market frictions, typically beating static delta-hedging. Heavy:
  needs a training pipeline, a market simulator, and `torch`; best as an offline-trained model
  served at inference, not per-request. Natural home: the Models/Strategy area, tied to the OMS
  paper-trading loop.
- **IV-surface ML** — arbitrage-free smoothing/forecasting of the implied-vol surface across
  strike × maturity (Gaussian-process or "deep smoothing" nets; SSVI/SABR as the parametric
  baselines). Directly augments the existing vol-surface view; main risk is enforcing no-arbitrage
  constraints. Could start as a parametric SSVI fit before any NN.

These remain **out of scope for this slice**; no files are created for them now.

## Out of scope (YAGNI)

- Exogenous regressors, multivariate models, GPU training.
- Persisting trained model artifacts (retrain on cache-miss).
- Intraday / non-US markets.
- Deep hedging and IV-surface ML (parked above — future slices).
