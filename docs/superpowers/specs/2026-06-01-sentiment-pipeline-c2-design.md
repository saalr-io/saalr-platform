# Sentiment pipeline + API + Monte-Carlo wiring (ML slice C2) — design

**Date:** 2026-06-01
**Slice:** LLD §4.3 / §13 step 15 — sub-slice **C2** (finishes the FinBERT band: persistence + worker
loop + read API + Monte-Carlo drift wiring). Builds directly on **C1** (`MassiveNewsProvider`,
`FinBertScorer`, `aggregate_sentiment`, the `SentimentScorer` protocol).
**Status:** Approved design, pre-plan.

## Purpose

Make sentiment real and usable: persist a per-ticker aggregate, refresh it on demand via the
ml-worker, expose it at `GET /v1/market/sentiment`, and feed it into the Monte-Carlo `drift_adjust`
— honestly (a thin, stale, or absent signal contributes **zero** drift and says so). This lights up
the hook slice B left neutral and completes the ML band (A+B+C).

## Decisions (locked during brainstorming)

1. **Persist the aggregate per ticker, append history** (`news_sentiment` table, non-RLS shared);
   reads take the most recent row.
2. **Gating = `ml_forecast` (Pro+), uniform** for both the read endpoint and the MC sentiment-drift
   (no premium-only split; ml_forecast is the platform's quant gate).
3. **Pipeline + persistence live in `saalr-core`** (torch-free, injected `SentimentScorer`); the
   ml-worker is a thin CLI that wires the real `FinBertScorer`. Scheduling/containerizing deferred.
4. **Honesty:** sentiment-drift applies only when present + confident + fresh; otherwise 0 with a
   reason. "No news" reads as neutral, not an error.

## Architecture

```
infra/migrations/versions/0004_news_sentiment.py    # news_sentiment table (non-RLS) + saalr_app grant
saalr_core/db/models/market_data.py                 # + NewsSentiment model (columns MUST match 0004 exactly)
saalr_core/sentiment/repo.py                         # save_sentiment, latest_sentiment, list_active_instruments
saalr_core/sentiment/pipeline.py                     # refresh_symbol(...) — torch-free, injected scorer+provider
apps/ml-worker/ml_worker/cli.py + __main__.py        # thin CLI: `sentiment` command, lazy FinBertScorer
apps/api/saalr_api/sentiment/router.py               # GET /v1/market/sentiment (ml_forecast-gated)
apps/api/saalr_api/main.py                           # register the sentiment router
apps/api/saalr_api/montecarlo/{schemas,router}.py    # + use_sentiment flag + drift wiring
```

### `news_sentiment` table (migration `0004`, non-RLS shared)
Columns (the `NewsSentiment` model in `market_data.py` must mirror these **exactly** — the
schema-vs-models test asserts column equality):
- `sentiment_id UUID PRIMARY KEY` (default generated app-side via `new_id`)
- `symbol TEXT NOT NULL`, `market CHAR(2) NOT NULL`
- `score DOUBLE PRECISION NOT NULL` (∈ [−1,1]), `label TEXT NOT NULL`, `confident BOOLEAN NOT NULL`
- `n_headlines INTEGER NOT NULL`, `total_weight DOUBLE PRECISION NOT NULL`
- `as_of TIMESTAMPTZ NOT NULL`, `computed_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `INDEX idx_news_sentiment_symbol ON news_sentiment(symbol, market, computed_at DESC)`
- `GRANT SELECT, INSERT ON news_sentiment TO saalr_app;` (belt-and-suspenders over 0001's default
  privileges; not added to the RLS `TENANT_SCOPED` set). `down_revision = "0003"`.

### `saalr_core/sentiment/repo.py`
- `save_sentiment(session, symbol, market, agg: dict) -> None` — INSERT a row from an
  `aggregate_sentiment` result (`score`, `label`, `confident`, `n_headlines`, `total_weight`,
  `as_of` parsed from the dict's ISO string). `sentiment_id = new_id()`.
- `latest_sentiment(session, symbol, market) -> dict | None` — most recent row
  (`ORDER BY computed_at DESC LIMIT 1`) → `{symbol, market, score, label, confident, n_headlines,
  as_of, computed_at}` (datetimes as aware `datetime`).
- `list_active_instruments(session, market: str | None = None) -> list[tuple[str, str]]` —
  `(symbol, market)` for active instruments (the refresh universe).

### `saalr_core/sentiment/pipeline.py` (pure orchestration, no torch)
`refresh_symbol(session, provider, scorer, symbol, market, as_of, lookback_hours=168) -> dict`:
`headlines = await provider.get_news(symbol, published_after=as_of - timedelta(hours=lookback_hours))`
→ `scored = scorer.score_headlines(headlines)` → `agg = aggregate_sentiment(scored, as_of)` →
`await repo.save_sentiment(session, symbol, market, agg)` → return `agg`. `provider` and `scorer`
are injected (protocols), so this is fully testable with stubs under the normal (torch-free) gate.

### ml-worker CLI (`apps/ml-worker/ml_worker/cli.py`, mirrors `ingest_worker/cli.py`)
`sentiment` subcommand: builds the core sessionmaker + `MassiveNewsProvider(settings.massive_api_key)`
+ **lazily** constructs `FinBertScorer` (imported inside the command so the parser test is torch-free)
→ `list_active_instruments` → `refresh_symbol` per symbol **in its own transaction** (crash
isolation, like ingest); prints per-symbol `{label, score}`. `__main__.py` calls `cli.main`.

### Read API `apps/api/saalr_api/sentiment/router.py`
`GET /v1/market/sentiment?ticker=&market=US`, `Depends(require_ml_forecast)` (402 free):
- `latest_sentiment(session, ticker.upper(), market)`. **No row → 200 neutral**
  `{ticker, market, score:0.0, label:"neutral", confident:false, n_headlines:0, has_data:false,
  computed_at:null, as_of:null}`. A row → 200 with its fields + `has_data:true` + `computed_at`/`as_of`.
- Register in `main.py` (`app.include_router(sentiment_router)`).

### Monte-Carlo wiring (`apps/api/saalr_api/montecarlo/`)
- `schemas.py`: `MonteCarloRequest` gains `use_sentiment: bool = False`.
- `router.py`: after σ is computed, before `monte_carlo_pop`:
  - `drift_adjust = 0.0`; `sentiment = {"applied": False, "reason": "not_requested"}`.
  - If `body.use_sentiment`: `sent = await sentiment_repo.latest_sentiment(session, underlying, market)`
    - `None` → `reason="no_data"`; not `sent["confident"]` → `reason="low_confidence"`;
      `now − computed_at > SENTIMENT_MAX_AGE_HOURS (168)` → `reason="stale"`;
    - else → `drift_adjust = sentiment_adjusted_drift(sent["score"], sigma, t_years)`;
      `sentiment = {"applied": True, "score": sent["score"], "label": sent["label"],
      "computed_at": sent["computed_at"].isoformat()}`.
  - `result = monte_carlo_pop(legs, spot, t_years, sigma, rate, drift_adjust=drift_adjust,
    paths=body.paths, seed=body.seed)`; response adds `"sentiment": sentiment`.
  - `sentiment_adjusted_drift` is imported from `saalr_ml.montecarlo`; `latest_sentiment` from
    `saalr_core.sentiment.repo`. Gating is unchanged (the endpoint is already `require_ml_forecast`).

## Error handling
- Read endpoint: free → 402; unsupported market → 400; unknown ticker → 200 neutral (`has_data:false`).
- MC: `use_sentiment` with no/low-confidence/stale signal → `drift_adjust=0` + an explicit `reason`
  (never a fabricated drift). Worker: per-symbol `ProviderError`/scoring failure is isolated to that
  symbol's transaction (logged, others continue) — like ingest.

## Testing
- **Pipeline** (`tests/integration/test_sentiment_pipeline.py`, 55432, **torch-free** via a stub
  scorer + stub provider): seed an instrument; `refresh_symbol` over bullish fixture headlines →
  persists a `news_sentiment` row (proves the `saalr_app` grant) and `latest_sentiment` returns a
  positive, `confident` score; `latest_sentiment` with no rows → `None`. A stale/low-confidence set →
  the honest aggregate.
- **Read API** (`tests/integration/test_sentiment_api.py`): seed a row → Pro `GET` → 200
  `has_data:true` + score; **free → 402**; unknown ticker → 200 neutral `has_data:false`.
- **MC wiring** (append to `tests/integration/test_montecarlo.py`): seed bars + a **bullish**
  sentiment row for the underlying; same-seed long-call `POST /montecarlo` with `use_sentiment:true`
  → `sentiment.applied:true` and **POP strictly greater** than the `use_sentiment:false` run (bullish
  drift raises a call's POP); `use_sentiment:true` with no row → `applied:false, reason:"no_data"`.
- **CLI** (`apps/ml-worker/tests/`, `--package saalr-ml-worker`): the `sentiment` subcommand parses
  (torch-free — `FinBertScorer` is lazy-imported in the command body).
- **Schema/migration:** `NewsSentiment` columns == `0004` columns (the existing
  `test_schema_matches_models` enforces this once the model + migration land); the migration applies
  cleanly on top of `0003`.
- **Gate:** `uv run pytest packages/core/tests` + `uv run pytest tests/integration/test_sentiment_*.py
  tests/integration/test_montecarlo.py` (torch-free) + `uv run --package saalr-ml-worker pytest
  apps/ml-worker/tests` (CLI parser) + `uvx ruff check`.

## Out of scope (later)
- Scheduling/containerizing the sentiment worker (an ops pass, like ingest's slice 7). Per-headline
  storage + source display; the sentiment UI; news dedup / incremental cursors; non-US news; a
  configurable max-age setting (constant 168h for v1); a sentiment time-series/trend endpoint (the
  history rows enable it later).
