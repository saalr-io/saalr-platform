# Monte-Carlo POP (ML slice B) — design

**Date:** 2026-06-01
**Slice:** LLD §4.4 / §13 step 10 — Monte-Carlo probability-of-profit. Second slice of the ML band
(A=GARCH done, B=Monte-Carlo here, C=FinBERT later).
**Status:** Approved design, pre-plan.
**Builds on:** slice A (`saalr_ml.forecast.vol_forecast` + its Redis cache), the strategy types +
`payoff._leg_pnl_at_expiry` (7a), the `bars` hypertable, the FRED rate provider, and the
`ml_forecast` entitlement.

## Purpose

Simulate a strategy's expiry P&L distribution by Monte-Carlo over GBM-simulated terminal prices, and
report **probability of profit (POP), expected value (EV), and a P&L histogram** — the things the
existing lognormal closed-form POP can't give. Volatility comes from the slice-A GARCH forecast
(honest primary), tying the ML band together. A sentiment-drift hook exists but stays neutral until
FinBERT (slice C).

## Decisions (locked during brainstorming)

1. **New dedicated endpoint** `POST /v1/strategies/montecarlo` (keeps `/analyze` fast).
2. **σ = the GARCH forecast** for the underlying by default (composes slice A); explicit `sigma`
   override allowed. **Gated by `ml_forecast`** (Pro/Premium; 402 free) — uniform with the GARCH
   endpoint.
3. **Vectorized numpy, no Numba** (10k paths is microseconds).
4. **Sentiment-drift hook included but neutral** in B (`sentiment=0` → `drift_adjust=0`); slice C
   supplies a real score.

## Architecture

```
packages/ml/saalr_ml/montecarlo.py     # PURE engine: GBM + vectorized payoff + histogram + drift hook
apps/api/saalr_api/forecast/service.py # NEW: get_or_compute_forecast (extracted, shared by both endpoints)
apps/api/saalr_api/forecast/router.py  # refactored to call the service (behaviour-neutral)
apps/api/saalr_api/montecarlo/         # NEW feature: schemas.py, router.py
apps/api/saalr_api/main.py             # register the montecarlo router
```

### `saalr_ml/montecarlo.py` (pure)
- `monte_carlo_pop(legs, spot, t_years, sigma, rate, div_yield=0.0, drift_adjust=0.0, paths=10000,
  seed=0, hist_bins=100) -> dict`:
  - GBM terminal prices: `drift = (rate - div_yield - 0.5*sigma**2)*t_years + drift_adjust`;
    `diffusion = sigma*sqrt(t_years)`; `Z = default_rng(seed).standard_normal(paths)`;
    `terminal = spot*exp(drift + diffusion*Z)`.
  - **Vectorized leg P&L** over the `terminal` array (mirrors `payoff._leg_pnl_at_expiry`):
    - OptionLeg: `intrinsic = maximum(terminal-strike,0)` (call) / `maximum(strike-terminal,0)` (put);
      `pnl += side.sign * (intrinsic - (entry_price or 0)) * OPTION_MULTIPLIER * qty`.
    - EquityLeg: `pnl += side.sign * (terminal - (entry_price or 0)) * qty`.
    - CashLeg: contributes 0.
  - `pop = float(mean(pnl > 0))`; `ev = float(mean(pnl))`; `counts, edges = histogram(pnl, bins)`.
  - Returns `{pop, ev, paths, histogram:{counts:[…], bin_edges:[…]}, percentiles:{p5,p50,p95},
    max_profit_observed, max_loss_observed, model:"gbm_mc", approximate:true, seed}`.
- `sentiment_adjusted_drift(sentiment, sigma, t_years) -> float` — `sentiment * 0.5 * sigma *
  sqrt(t_years)` (LLD §4.4). The MC's `drift_adjust` param receives this; slice B always passes 0.

> Consistency guard: the vectorized payoff duplicates the per-leg semantics of the core scalar
> `payoff._leg_pnl_at_expiry` because numpy can't live in stdlib-only `saalr-core`. A unit test
> cross-checks the vectorized result against the scalar function at sample prices so they can't drift.

### `forecast/service.py` (extracted, shared)
`get_or_compute_forecast(redis, sessionmaker, session, ticker, market, horizon, ttl) -> dict`:
read `mdq:volfc:v1:{market}:{ticker}:{horizon}`; on hit return it; else `load_closes` →
`vol_forecast(np.array(closes), horizon)` (raises `ValueError` on `<250` → caller maps 422) →
persist a `model_validation_runs` row (own committed session, as today) → cache → return the payload.
The forecast router calls this and returns it directly (behaviour-neutral; existing tests stay green).

### API `apps/api/saalr_api/montecarlo/`
- `schemas.py` — `MonteCarloRequest{config: StrategyConfigIn (reused from strategies.schemas),
  market: str = "US", sigma: float | None = None, paths: int = 10000, seed: int = 0}`.
- `POST /v1/strategies/montecarlo`, dependency `require_ml_forecast` (reused from `forecast.gating`):
  1. `config = body.config.to_domain()`; `legs = config.legs`; `underlying = config.underlying`.
  2. Nearest option-leg expiry → `days_to_expiry = (min option expiry − today).days`; if there are no
     option legs or `days_to_expiry < 1` → **422** `VALIDATION_NO_EXPIRY`. `t_years = days/365`.
  3. `closes = await forecast_repo.load_closes(session, underlying, market)`; `spot = closes[-1]`; if
     `closes` empty → **422** `INSUFFICIENT_HISTORY`.
  4. σ: if `body.sigma` is set (`>0`) → `sigma = body.sigma`, `sigma_source = "override"`. Else
     `payload = await get_or_compute_forecast(redis, sessionmaker, session, underlying, market,
     days_to_expiry, ttl)` (maps `ValueError` → 422 INSUFFICIENT_HISTORY); `sigma =
     mean(payload["primary_forecast"]) / 100.0`; `sigma_source = "garch"`.
  5. `rate = (await rate_provider.get_curve()).rate_for(t_years)` (FRED; provider already on
     `app.state`, with its built-in fallback).
  6. `result = monte_carlo_pop(legs, spot, t_years, sigma, rate, paths=body.paths, seed=body.seed)`.
  7. Return `{**result, "underlying": underlying, "market": market, "spot": spot, "sigma": sigma,
     "sigma_source": sigma_source, "horizon_days": days_to_expiry, "rate": rate}`.
- `main.py`: `from .montecarlo.router import router as montecarlo_router` +
  `app.include_router(montecarlo_router)`.

> POP is computed relative to the per-leg `entry_price` in the config (same convention as the payoff
> curve). Missing entry prices are treated as 0, so POP/EV are only as meaningful as the entries the
> caller supplies — stated honestly in the response (`approximate: true`).
>
> Multi-expiry note: the MC values **every leg at intrinsic at the binding (nearest) expiry**, exactly
> like the existing `payoff.expiration_curve`. This is exact for single-expiry structures (verticals,
> condors, straddles — the common case); for calendars/diagonals the longer-dated leg's residual time
> value at the near expiry is not modeled (the standard expiration-diagram simplification). Carried as
> a known limitation, consistent with the rest of the strategy analytics.

## Error handling
- Free tier → 402 `ENTITLEMENT_ML_FORECAST_REQUIRES_PRO`.
- No option legs / nearest expiry already passed → 422 `VALIDATION_NO_EXPIRY`.
- Underlying has no bars (no spot) → 422 `INSUFFICIENT_HISTORY`.
- σ from GARCH but `<250` bars → 422 `INSUFFICIENT_HISTORY` (the `vol_forecast` guard).
- `sigma <= 0` or `paths` outside `[1, 200000]` → 422 `VALIDATION_INVALID_PARAMETER`.

## Testing
- **ML unit** (`packages/ml/tests/test_montecarlo.py`, seeded → deterministic):
  - A **long call's MC POP ≈ the lognormal closed-form** `pop.probability_of_profit` within MC error
    (e.g. |Δ| < 0.02 at 50k paths, fixed seed) — cross-validates the GBM + payoff.
  - The **vectorized payoff equals the core scalar `payoff._leg_pnl_at_expiry`** summed over legs, at
    a handful of sample terminal prices, for a multi-leg config (consistency guard).
  - `histogram.counts.sum() == paths`; `len(bin_edges) == hist_bins + 1`.
  - **Determinism:** identical `pop`/`ev` for the same seed; different seeds differ slightly.
  - **`sentiment_adjusted_drift` monotonicity:** positive sentiment raises a long call's POP vs
    neutral; negative lowers it.
  - EV/POP finite and in `[0,1]` for a debit spread.
- **API integration** (`tests/integration/test_montecarlo.py`, 55432 + Redis): seed ≥260 bars; Pro
  tenant POSTs a ~30-day long-call config → 200 with `pop`/`ev`/`histogram` + `sigma_source:"garch"`;
  **free → 402**; **σ-override** request → 200 `sigma_source:"override"` (works with few bars since
  GARCH is skipped, but still needs ≥1 bar for spot); **no option legs → 422**; **unknown underlying
  (no bars) → 422**.
- **Forecast regression:** `tests/integration/test_vol_forecast.py` stays green after the
  `get_or_compute_forecast` extraction.
- **Gate:** `packages/ml/tests` + the API integration (plain `uv run pytest`, since `saalr-ml` is a
  root/`saalr-api` dep) + `uvx ruff check`.

## Out of scope (later)
- The real sentiment score (slice C wires FinBERT into `drift_adjust`). American/early-exercise or
  path-dependent payoffs (this is European expiry P&L). An MC-result cache (compute is ~ms once σ is
  known; the GARCH fit is already cached). A Greeks-at-horizon distribution. The Monte-Carlo UI.
  Numba JIT (vectorized numpy is already fast enough).
