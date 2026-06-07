# Market Regime Engine + Trade Ideas — Design Spec

**Date:** 2026-06-05
**Slice:** Regime analysis + recommendations (Slice B of the two-slice "regime drives templates" effort)
**Status:** Approved design, ready for implementation plan
**Depends on:** Slice A (template metadata schema — `market_view`/`vol_view`/`net`/`risk`/`reward`/`legs`/`complexity`)

## Context

Slice A shipped 21 templates with a recommender-ready metadata schema. Slice B builds the engine that makes "regime drives templates" real: a transparent, rule-based market-regime classifier that reads a ticker's recent price action (and, for entitled users, GARCH vol-forecast + FinBERT sentiment), then scores the 21 templates against the detected regime and surfaces a ranked "what should I trade now?" list on a new `/app/ideas` screen.

### Decisions locked during brainstorming
- **Rule-based, not trained** — every signal traces to an explainable threshold (the platform's honesty/validation-first ethos). No new model, no training data.
- **Taxonomy:** two axes — Direction (5 levels) × Volatility (3 levels) — plus a Momentum badge and a synthesized headline.
- **Tiering:** the endpoint is **ungated**; the free base (trend + vol-percentile + momentum, all from free `bars`) computes for everyone, and the premium layer (GARCH vol-trend + sentiment) enriches the response only when the principal has `ml_forecast` (Pro/Premium). Degrades gracefully when premium signals are absent or thin.
- **Recommender:** pure, **scored** (not a static map) — `market_view` + `vol_view` tag-match **plus a retail-safety bias** (demote undefined-risk and advanced structures; still shown, just lower).
- **UI:** dedicated `/app/ideas` screen; each recommendation's **Apply** deep-links into the existing strategy builder.
- **Momentum metric:** Kaufman Efficiency Ratio (close-only) as the ADX-equivalent, since `load_closes` is close-only (no new bars loader).

## Goal

Ship `GET /v1/market/regime?ticker=&market=US` and an `/app/ideas` screen that classify a ticker's regime from daily closes (+premium signals when entitled) and return a ranked, rationale-bearing list of recommended templates.

## Architecture

```
saalr_ml/regime.py            pure numpy — trend_score, realized_vol_percentile,
                              efficiency_ratio, vol_trend_label, classify_regime → dict   [free base]
saalr_core/strategies/recommend.py   pure — recommend(regime, templates) → ranked list   [no numpy]
        │
apps/api/saalr_api/regime/    router (ungated) + service (compose + cache)
   GET /v1/market/regime
        │ load_closes (free) → classify_regime
        │ if entitlements_for(tier)["ml_forecast"]:  + GARCH vol-trend  + latest_sentiment
        │ recommend(regime, list_templates())  → Redis cache (1h)
        ▼
apps/web /app/ideas           Ideas page → RegimePanel (badges) + premium card + RecoCards → Apply
                              → navigate('/strategies', { state: { config } })
```

**No circular dependency:** the numpy classifier lives in `saalr-ml` (which already depends on `saalr-core`); the recommender takes plain dicts (regime + template metadata) so it stays in `saalr-core`; the API layer composes both.

## Engine internals (`saalr_ml/regime.py`)

All functions are pure (numpy in, plain values out). `MIN_CLOSES = 60`; `classify_regime` raises `ValueError("insufficient history")` below that (the router maps it to 422).

### Direction (5 levels)
```
sma20 = mean(closes[-20:]);  sma50 = mean(closes[-50:]);  price = closes[-1]
blend = (sign(price - sma20) + sign(price - sma50) + sign(sma20 - sma50)) / 3      # [-1, 1]
slope = (sma20 - mean(closes[-40:-20])) / mean(closes[-40:-20])                    # 20d % change of SMA20
slope_c = clamp(slope / 0.10, -1, 1)                                               # ±10%/20d saturates
T = 0.4 * blend + 0.6 * slope_c
```
Buckets: `strong_bullish` T≥0.6 · `bullish` 0.2≤T<0.6 · `neutral` −0.2<T<0.2 · `bearish` −0.6<T≤−0.2 · `strong_bearish` T≤−0.6.

### Volatility (3 levels)
`realized_vol(window=20)` = `std(log-returns of last 20 closes) · sqrt(252) · 100` (annualized %). Build the rolling 20d realized-vol series over the available closes; `percentile` = rank of the latest value among the trailing `min(252, len)` values. Buckets: `low` <0.33 · `normal` 0.33–0.66 · `high` >0.66.

### Momentum (2 levels)
Kaufman Efficiency Ratio over 20d: `ER = abs(closes[-1] - closes[-21]) / sum(abs(diff(closes[-21:])))` ∈ [0,1]. `trending` ER≥0.30 · `range_bound` <0.30.

### Premium layer (computed in the API service, only when entitled)
- **Vol trend** — `vol_trend_label(garch_mean, realized_vol)` (pure, in regime.py): `garch_mean = mean(vol_forecast.primary_forecast)`; `rising` if `garch_mean > realized_vol·1.10`, `falling` if `< ·0.90`, else `stable`. Unavailable (flagged `available:false`) if `vol_forecast` raises `ValueError` (<250 closes).
- **Sentiment** — `sentiment_repo.latest_sentiment(session, ticker, market)` → `bullish/neutral/bearish` + score. `available:false` (and label `neutral`, score 0) when the row is absent.

### `classify_regime(closes) -> dict`
Returns (every signal carries a plain-English `detail`):
```python
{
  "direction":  {"label": "bullish", "score": 0.42, "detail": "price above the 20- and 50-day average, rising"},
  "volatility": {"label": "normal", "percentile": 0.42, "realized_vol": 18.3, "detail": "20-day realized vol 18.3%, 42nd percentile of the past year"},
  "momentum":   {"label": "trending", "efficiency_ratio": 0.34, "detail": "directional efficiency 0.34 — trending"},
  "headline":   "Bullish · Normal vol · Trending",
  "last_close": 585.21,
  "n_closes": 858,
}
```

## Recommender (`saalr_core/strategies/recommend.py`)

`recommend(regime: dict, templates: list[dict]) -> list[dict]` — pure; `templates` is `templates.list_templates()` output. Scoring per template:

```
direction_points:  by detected direction label →
  strong_bullish | bullish  : market_view bullish +3, neutral +1, volatile +1, bearish -2
  strong_bearish | bearish  : market_view bearish +3, neutral +1, volatile +1, bullish -2
  neutral                   : market_view neutral +3, bullish +1, bearish +1, volatile +1
vol_points:  by detected volatility label →
  high   : vol_view short_vol +3, neutral +1, long_vol -1
  low    : vol_view long_vol  +3, neutral +1, short_vol -1
  normal : vol_view neutral   +2, short_vol +1, long_vol +1
momentum_bonus:
  momentum trending  AND market_view volatile  → +1   (breakout plays)
  momentum range_bound AND market_view neutral → +1
safety_penalty (a non-negative amount subtracted):
  risk == "undefined"        → +2
  complexity == "advanced"   → +1   (penalties stack: an advanced undefined-risk template loses 3)
score = direction_points + vol_points + momentum_bonus - safety_penalty
```
Each result: `{template_key, name, score, market_view, vol_view, net, risk, complexity, rationale}`. `rationale` is a human string assembled from which clauses fired (e.g. "Fits a bullish view in normal vol; defined risk."). Sort by score desc, then `key` asc (stable, deterministic). Returns **all 21 ranked**; the UI highlights the top ~5. The premium signals (vol_trend/sentiment) do **not** change scoring in this slice — they are shown as context badges only (keeps the recommender pure of tier state; sentiment-into-scoring is a deferred follow-up).

## API (`apps/api/saalr_api/regime/`)

- `router.py` — `GET /v1/market/regime` under prefix `/v1/market`, tag `regime`. **Ungated** (`Depends(get_principal)`). Reuses the `_validate(ticker, market)` pattern (alpha ticker → 404, market≠US → 400). `has_premium = entitlements_for(principal.tier)["ml_forecast"]`. Calls the service; maps `ValueError` → `422 INSUFFICIENT_HISTORY`.
- `service.py` — `get_or_compute_regime(redis, session, ticker, market, has_premium, ttl) -> dict`:
  1. Cache read `mdq:regime:v1:{market}:{ticker}:{"premium" if has_premium else "base"}`.
  2. `closes = await load_closes(session, ticker, market)` (free bars).
  3. `regime = classify_regime(closes)` (raises ValueError <60 → caller 422).
  4. If `has_premium`: compute `vol_trend` (try `vol_forecast`, on ValueError → `available:false`) and `sentiment` (`latest_sentiment` → `available:false` if None); attach as `regime["premium"]`. Else `regime["premium"] = None`. Set `regime["premium_available"] = has_premium`.
  5. `recommendations = recommend(regime, list_templates())`.
  6. `payload = {ticker, market, as_of, regime, recommendations, approximate: true}`; cache `ex=ttl`; return.
- No new gating file; no new DB table (cache-only — regime is recomputable from bars).

**Response shape:**
```json
{
  "ticker": "SPY", "market": "US", "as_of": "2026-06-05T...Z", "approximate": true,
  "regime": {
    "direction": {...}, "volatility": {...}, "momentum": {...},
    "headline": "Bullish · Normal vol · Trending", "last_close": 585.21, "n_closes": 858,
    "premium_available": true,
    "premium": {
      "vol_trend": {"label": "rising", "available": true, "detail": "GARCH 10-day forecast above current realized vol"},
      "sentiment": {"label": "bullish", "score": 0.31, "available": true, "n_headlines": 12, "detail": "..."}
    }
  },
  "recommendations": [
    {"template_key": "bull_put_spread", "name": "Bull Put Spread", "score": 7, "market_view": "bullish",
     "vol_view": "short_vol", "net": "credit", "risk": "defined", "complexity": "beginner",
     "rationale": "Fits a bullish view in normal vol; defined risk."},
    ...
  ]
}
```
For a free user, `premium` is `null` and `premium_available` is `false`.

**Wiring:** register the router in `main.py`; add `app.state.regime_ttl` from a new config field `regime_cache_ttl_seconds` (default 3600).

## Frontend (`apps/web`)

- `src/lib/regime.ts` — typed client `getRegime(ticker, market='US'): Promise<RegimeResponse>` + types (`RegimeResponse`, `Signal`, `Recommendation`, `PremiumSignals`). Reuses the shared `request()` wrapper (401→logout; the endpoint is ungated so no 402 path needed, but `request` already handles it harmlessly).
- `src/features/ideas/hooks.ts` — `useRegime(ticker: string | null)` query (`enabled: !!ticker`, `retry: false`).
- `src/features/ideas/RegimePanel.tsx` — renders the 5 signal badges (direction/vol/momentum + premium vol-trend/sentiment), the headline, and each signal's `detail`. Premium sub-section: if `premium_available`, show the live premium badges; else a compact upgrade nudge (link to `/app/billing`), mirroring the existing `PremiumGate`/`MarketsGate` pattern. Theme tokens only.
- `src/features/ideas/RecoCard.tsx` — one recommendation: name, score, `rationale`, and Slice-A-style net/legs/risk badges (`risk:undefined` → warn tone). **Apply** button → builds the template (`buildTemplate(key, {underlying: ticker, expiry: defaultExpiry(), atm_strike: last_close})`, where `defaultExpiry()` returns the ISO date ~35 calendar days ahead — the builder lets the user adjust) then `navigate('/strategies', { state: { config } })`.
- `src/pages/Ideas.tsx` — ticker input (default empty; submit enables the query) → `RegimePanel` → ranked `RecoCard`s (top 5 emphasized, rest in a "more" list). Loading/empty/error states. Owns the `useRegime` hook + the Apply handler.
- `src/pages/Ideas.test.tsx` — regime renders badges + recommendations; free user sees the premium nudge; Apply navigates with a config.
- `src/app/Router.tsx` — add `<Route path="ideas" element={<Ideas />} />` + import.
- `src/components/Sidebar.tsx` — add `['/ideas', 'Trade Ideas']` to the `'Learn & Research'` section.
- `src/pages/Strategies.tsx` — on mount, read `location.state?.config` (react-router `useLocation`); if present, `setConfig(state.config)` + `setTab('build')`. This is the Apply landing — a small additive change; the existing builder takes over.

## Data flow

`/app/ideas` ticker submit → `useRegime` → `GET /v1/market/regime` → service composes base (+premium) → `recommend()` → JSON → `RegimePanel` + `RecoCard`s. **Apply** → `buildTemplate` (existing endpoint) → `navigate('/strategies', {state:{config}})` → `Strategies` loads it into the builder → existing analyze/save flow.

## Error handling
- `<60` closes → `422 INSUFFICIENT_HISTORY` (thin/new ticker).
- Non-alpha ticker → 404; market≠US → 400 (existing pattern).
- Premium signal failures never fail the request — they degrade to `available:false` (GARCH <250 closes; no sentiment row).
- The endpoint never calls a market-data provider (closes come from the local `bars` table), so there is no 503 provider path.

## Testing
- **`saalr_ml/regime.py` (pure):** synthetic close series — a steady uptrend → `strong_bullish`/`bullish`; a flat/noisy series → `neutral` + `range_bound`; a low-vol vs high-vol series → correct percentile bucket; ER ≈1 for a monotonic ramp, ≈0 for an oscillation; `vol_trend_label` thresholds; `classify_regime` raises below `MIN_CLOSES`.
- **`recommend.py` (pure):** a high-vol-neutral regime ranks iron condor + credit spreads above directional debits, and ranks a defined-risk structure above an equally-fitting undefined-risk one (safety bias); a strong-bullish low-vol regime puts bullish long-vol/debit structures on top; output is deterministically ordered.
- **API:** ungated base works for a free principal (`premium` null); premium fields populate with an `ml_forecast` tier; `422` on a thin ticker; cache hit returns the same payload. (DB-backed test uses the 55432 override; gated by the existing integration-test harness.)
- **Web:** `RegimePanel` renders direction/vol/momentum badges + headline; free user sees the upgrade nudge (no premium badges); `RecoCard` Apply triggers `buildTemplate` + navigation; `Ideas` empty/loading/error states.

## Out of scope (deferred)
- **Sentiment/GARCH into the recommendation *score*** — this slice shows them as context only; folding them into scoring (e.g. sentiment confirms/vetoes a directional reco) is a follow-up.
- **Regime history / persistence** — cache-only; no `regime_runs` table. A backtest of regime-recommendation performance is a later, larger effort.
- **Intraday/true-ADX momentum** — would need an OHLC bars loader; the close-only Efficiency Ratio is the deliberate v1.
- **Multi-market** (India) — US-only, consistent with every other market endpoint.
- **Auto-refresh / streaming** — daily-bar cadence; a manual ticker submit + 1h cache is sufficient.

## Build sequence (for the plan)
1. `saalr_ml/regime.py` + tests (pure classifier).
2. `saalr_core/strategies/recommend.py` + tests (pure recommender).
3. API `regime/` router+service + config wiring + tests.
4. Web client + hooks + `RegimePanel`/`RecoCard`/`Ideas` + route/sidebar + `Strategies.tsx` Apply-landing + tests.
5. Final gate (core+ml pytest; web typecheck/lint/test/build) + optional live SPY smoke.
