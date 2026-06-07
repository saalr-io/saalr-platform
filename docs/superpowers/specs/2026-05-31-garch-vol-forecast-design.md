# GARCH volatility forecast (ML slice A) — design

**Date:** 2026-05-31
**Slice:** LLD §4.1 / §13 step 9 — GARCH inference + honest baseline reporting. First slice of the ML
band (A=GARCH, B=Monte-Carlo, C=FinBERT — see the band decomposition; B and C are separate later
slices).
**Status:** Approved design, pre-plan.
**Builds on:** the `bars` hypertable (ingestion), the `ml_forecast` tier entitlement, the existing
`model_validation_runs` table, and the API's Redis cache + `get_principal` pattern.

## Purpose

Forecast annualized volatility for a ticker over a short horizon using a hand-rolled GARCH(1,1),
**always reported alongside the HV21 baseline**, with a request-time walk-forward holdout deciding
which model is `primary`. The honesty rule is the point: if GARCH does not beat HV21 on held-out
data, HV21 is the primary number and GARCH is labelled `underperforming_baseline`.

## Decisions (locked during brainstorming)

1. **Hand-rolled GARCH(1,1)** via numpy + `scipy.optimize` (own-the-math, fully unit-testable). No
   `arch`, no pandas.
2. **Request-time walk-forward holdout** picks `primary` (no nightly performance-log dependency, no
   cold-start). Persisted to `model_validation_runs`.
3. **Isolated `saalr-ml` package** so numpy/scipy land only where ML is used (not in `saalr-core`).
4. **Synchronous + Redis-cached** in the API (a GARCH(1,1) fit is sub-second-ish); no async queue.
5. **Gated by `ml_forecast`** (Pro/Premium); 402 for free.

## Architecture

```
packages/ml/                         # NEW workspace package "saalr-ml" (numpy + scipy + saalr-core)
  pyproject.toml
  saalr_ml/
    __init__.py
    garch.py      # fit_garch11, forecast_var, simulate_ci
    baseline.py   # hv21
    evaluate.py   # walk_forward
    forecast.py   # vol_forecast (orchestrator) -> result dict
  tests/          # pure-numpy unit tests
apps/api/saalr_api/forecast/         # NEW API feature
  __init__.py  repo.py  router.py
apps/api/saalr_api/main.py           # register the forecast router
```

The root workspace already globs `packages/*`, so `saalr-ml` is auto-discovered. The API adds
`saalr-ml` to its dependencies — and because `saalr-api` is a root dependency, `saalr-ml` is then
installed (editable) in the root env, so both `packages/ml/tests` and the API integration tests run
under a plain `uv run pytest` (no `--package` flag needed).

### `saalr_ml/garch.py` (pure)
GARCH(1,1), constant mean, normal innovations. Returns are scaled ×100 for optimizer conditioning.
- `fit_garch11(returns: np.ndarray) -> GarchParams` — `GarchParams(omega, alpha, beta, mu)`.
  Negative-log-likelihood minimized with `scipy.optimize.minimize` (method `"L-BFGS-B"` with bounds
  `omega>0, 0<=alpha<1, 0<=beta<1`; reject/penalize `alpha+beta>=1` inside the objective to enforce
  stationarity). Init via variance targeting: `alpha0=0.05, beta0=0.90, omega0=var*(1-alpha0-beta0)`,
  `mu0=mean`. The conditional-variance recursion seeds `sigma2[0]` at the sample variance.
- `forecast_var(params, last_sigma2, last_resid2, horizon) -> np.ndarray` — daily conditional
  variance for each step `1..horizon`: `sigma2_{t+1} = omega + alpha*resid2_t + beta*sigma2_t`, then
  `E[sigma2_{t+k}] = omega + (alpha+beta)*E[sigma2_{t+k-1}]`. Converges to `omega/(1-alpha-beta)`.
- `simulate_ci(params, last_sigma2, last_resid2, horizon, n_paths, seed) -> (lo, hi)` — simulate
  `n_paths` GARCH paths (normal shocks; `seed` via `np.random.default_rng(seed)` for determinism),
  take the 2.5/97.5 percentiles of the **annualized** per-step vol. `n_paths` default 1000.

Helper `annualize_vol(daily_var) -> float = sqrt(daily_var * 252) / 100` (de-scales the ×100).

### `saalr_ml/baseline.py` (pure)
`hv21(returns: np.ndarray) -> float` — annualized stdev (×√252) of the **last 21** daily log returns
(de-scaled). Held flat across the horizon by the caller.

### `saalr_ml/evaluate.py` (pure)
`walk_forward(returns, holdout_days=40) -> WalkForward` where
`WalkForward(garch_mae, hv21_mae, lift, primary, holdout_days)`:
- Split `returns` into `train = returns[:-holdout_days]` and the holdout tail.
- Fit GARCH once on `train`; **forward-filter** the fitted recursion across the holdout to get each
  day's 1-step-ahead variance forecast. For each holdout day, HV21's 1-step forecast = rolling-21d
  variance from the data up to that day.
- Score both vs the realized-variance proxy `r_t^2` (the holdout return squared): `mae = mean(|forecast_var - r_t^2|)` for each model.
- `lift = (hv21_mae - garch_mae) / hv21_mae`; `primary = "garch" if garch_mae < hv21_mae else "hv21"`.

### `saalr_ml/forecast.py` (pure orchestrator)
`vol_forecast(closes: np.ndarray, horizon: int, holdout_days: int = 40, seed: int = 0) -> dict`:
- `returns = diff(log(closes)) * 100`.
- `wf = walk_forward(returns, holdout_days)`.
- Fit GARCH on the **full** returns; `garch_path = annualize(forecast_var(..., horizon))`;
  `garch_ci = simulate_ci(...)`.
- `hv21_val = hv21(returns)`; `hv21_path = [hv21_val] * horizon`.
- Assemble the result dict (see API response), tagging the `primary`/`alternative` from `wf.primary`.
  The alternative's `status` is honest about *why* it's secondary: `"baseline"` when the alternative
  is HV21 shown for reference (GARCH won), or `"underperforming_baseline"` when the alternative is
  GARCH because it lost to its baseline (HV21 won). Plus `delta_mae_vs_baseline`.
- Raise `ValueError("insufficient history")` if `len(closes) < 250` (need a real train + holdout).

## API (`apps/api/saalr_api/forecast/`)

### `repo.py`
- `load_closes(session, symbol, market, lookback_days) -> list[float]` — daily closes from `bars`
  (`interval='1d'`, non-RLS, last ~2 years) ordered by ts. Plain read, no tenant scope.
- `record_validation(session, model_name, market, cohort_label, baseline_name, status,
  metric_summary_json) -> None` — INSERT a `model_validation_runs` row via the **request session**
  (the table is non-RLS shared market data, so the tenant GUC is irrelevant; `validation_id` via
  `new_id()`, `started_at`/`completed_at` = now). `cohort_label = f"{ticker}:{as_of_date}"` so rows
  are naturally ~one per ticker per day. **Grant risk (plan must verify):** the `saalr_app` role got
  INSERT grants on RLS tables + `bars`/`instruments` in earlier slices, but `model_validation_runs`
  may have no grant yet — if `saalr_app` lacks INSERT/SELECT on it, add a tiny Alembic migration
  granting them (mirroring the `instruments` grant), and have the integration test prove the insert
  works as `saalr_app`.

### `GET /v1/market/vol-forecast`
Query: `ticker` (required), `market` (default `US`), `horizon` (default 10, 1–30).
1. `get_principal` → `(session, principal)`. If `not entitlements_for(principal.tier)["ml_forecast"]`
   → **402** `ENTITLEMENT_ML_FORECAST_REQUIRES_PRO`.
2. Redis cache key `mdq:volfc:v1:{market}:{ticker}:{horizon}` → return on hit.
3. `load_closes`; if `< 250` rows → **422** `INSUFFICIENT_HISTORY`.
4. `vol_forecast(np.array(closes), horizon)` (may also raise → 422).
5. `record_validation(...)` (status `passed`/`failed` = did GARCH beat HV21);
   `redis.set(key, json, ex=cache_ttl)`; return the result.

Response:
```json
{ "ticker": "AAPL", "market": "US", "horizon_days": 10, "as_of": "2026-05-31T…Z",
  "primary_model": "garch",
  "primary_forecast": [22.1, 22.4, 22.6, …],
  "primary_ci_95": [[18.0, 26.5], …],
  "alternative_models": [
    { "model": "hv21", "forecast": [20.3, 20.3, …],
      "status": "baseline", "delta_mae_vs_baseline": -0.0012 }
  ],
  "validation": { "holdout_days": 40, "garch_mae": …, "hv21_mae": …, "lift": 0.08 },
  "model": "garch(1,1)", "iv_source": "realized_returns", "approximate": true }
```
(`primary_forecast`/CI are annualized vol **percent**. When HV21 wins, the two models swap roles and
GARCH carries `status:"underperforming_baseline"`.)

### `main.py`
Add `from .forecast.router import router as forecast_router` and `app.include_router(forecast_router)`.
Add a `vol_forecast_cache_ttl_seconds` setting (default e.g. 21600 = 6h) on `app.state`, or reuse an
existing TTL setting.

## Error handling
- Free tier → 402; unknown ticker / `<250` bars → 422 `INSUFFICIENT_HISTORY`; GARCH optimizer
  non-convergence → fall back to `primary="hv21"` with GARCH `status:"fit_failed"` (still honest, never
  a fabricated GARCH number) and `status="failed"` in the validation row. `horizon` out of 1–30 → 422.

## Testing
- **ML unit** (`packages/ml/tests/`, pure numpy, deterministic via seeded RNG):
  - `fit_garch11` **recovers known params** on data simulated from known `(ω,α,β)` (within a tolerance
    band); rejects non-stationary fits (`α+β<1` always holds).
  - `forecast_var` **converges to the unconditional variance** `ω/(1−α−β)` at long horizon; is flat-ish
    for near-IID data.
  - `hv21` matches a hand-computed annualized stdev.
  - `simulate_ci` brackets the point forecast (lo ≤ point ≤ hi) and is deterministic under a fixed seed.
  - `walk_forward` picks **`garch`** on volatility-clustered simulated data and **`hv21`** (or a tie)
    on near-constant-vol data — directional, not magic numbers.
  - `vol_forecast` raises on `<250` closes; returns the right shape and a `primary` consistent with
    `walk_forward`.
- **API integration** (`tests/integration/test_vol_forecast.py`, 55432 + Redis): seed ≥260 daily
  `bars` (a deterministic series) for a ticker; Pro tenant `GET` → 200 with both models + `validation`
  + a `primary`, and `primary_forecast` length == horizon; **free tier → 402**; **<250 bars → 422**;
  a `model_validation_runs` row was written; a **second call hits the Redis cache** (assert no second
  validation row / same `as_of`).
- **Gate:** `saalr-ml` unit tests + the API integration (under the env that installs `saalr-ml`) +
  `uvx ruff check`.

## Out of scope (later)
- The nightly `ml_performance_log` accumulation + rolling-30-day "underperforming" badge (the
  request-time holdout covers v1). SageMaker/S3 trained-pickle pipeline (no AWS yet — fit on demand).
  LSTM/ARIMA price forecasting (§4.2 — separate slice). The forecast UI. Sentiment-adjusted vol
  (needs FinBERT, slice C). India/IN-market specifics beyond passing `market` through.
