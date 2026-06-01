# FinBERT sentiment — scoring engine + news adapter (ML slice C1) — design

**Date:** 2026-06-01
**Slice:** LLD §4.3 / §13 step 15 — FinBERT sentiment. Sub-slice **C1** (engine + news adapter);
**C2** (table + worker loop + API + Monte-Carlo drift wiring) is the next slice.
**Status:** Approved design, pre-plan.
**Builds on:** the marketdata adapter pattern (`aggregates.py`), `MASSIVE_API_KEY`, and the
strategy/MC Monte-Carlo `drift_adjust` hook (slice B) that C2 will feed.

## Purpose

Stand up the reusable sentiment-scoring core: fetch news headlines for a ticker (Massive), score each
with FinBERT, and aggregate them into a single **honest** per-ticker sentiment number that goes
**neutral when the signal is thin or stale**. No DB, worker loop, API, or MC wiring yet — those are C2.

## Decisions (locked during brainstorming)

1. **News source = Massive** `/v2/reference/news` (reuse `MASSIVE_API_KEY`; same adapter pattern as
   aggregates). The live test is env-gated, so unit tests pass on fixtures regardless of plan
   entitlement.
2. **Real FinBERT in C1**, in `apps/ml-worker` (torch + transformers), behind a `SentimentScorer`
   protocol. Fast tests use a stub; one **env-gated live test** runs the real ~440 MB model.
3. **torch stays isolated to `apps/ml-worker`** — not a root dependency, so normal `uv sync` / tests
   never pull it. The default gate (`packages/core/tests`) is torch-free.
4. **Honesty floor** from §4.3: aggregate confidence below threshold → neutral (0.0).

## Architecture

```
saalr_core/marketdata/news.py     # PURE httpx adapter (mirrors aggregates.py): RawHeadline + MassiveNewsProvider
saalr_core/sentiment/             # PURE core (no torch); importable by the worker + future API
  __init__.py
  types.py     # Label, ScoredHeadline, SentimentScorer protocol
  aggregate.py # aggregate_sentiment(...) — §4.3 time-decay / confidence / neutral-floor
apps/ml-worker/                   # torch lives here only
  pyproject.toml                  # + saalr-core, transformers, torch (CPU)
  ml_worker/__init__.py  ml_worker/finbert.py   # FinBertScorer (lazy model load)
  tests/test_finbert_live.py      # env-gated live model test
packages/core/tests/              # torch-free unit + pipeline tests
```

### `saalr_core/marketdata/news.py` (pure, mirrors `aggregates.py`)
- `RawHeadline{title: str, description: str, published_at: datetime, source: str, url: str,
  tickers: list[str]}` (frozen dataclass).
- `parse_news(results: list[dict]) -> list[RawHeadline]` — pure; maps Massive `/v2/reference/news`
  `results[]`: `title`, `description` (default ""), `published_utc` (ISO → `datetime`, UTC),
  `publisher.name` → `source`, `article_url` → `url`, `tickers` (default []). Rows missing a title or
  timestamp are skipped (defensive).
- `MassiveNewsProvider(api_key, *, base_url=_BASE)` with the same retry/`_get`/pagination machinery as
  `MassiveAggregatesProvider`:
  - `get_news(ticker, limit=50, published_after: datetime|None=None) -> list[RawHeadline]` →
    `GET {base}/v2/reference/news` with params `{ticker, limit, order:"desc", sort:"published_utc",
    apiKey}` plus `published_utc.gte = published_after.isoformat()` when given; follows `next_url`
    (seen-set bounded). Raises `ProviderError` (no key / HTTP errors), like the aggregates provider.

### `saalr_core/sentiment/types.py` (pure)
- `class Label(str, Enum)`: `BEARISH="bearish"`, `NEUTRAL="neutral"`, `BULLISH="bullish"`.
- `@dataclass(frozen=True) ScoredHeadline{published_at: datetime, score: float, confidence: float,
  label: Label, title: str}` (`score ∈ [-1,1]`, `confidence ∈ [0,1]`).
- `class SentimentScorer(Protocol)`: `def score_headlines(self, headlines: list[RawHeadline]) ->
  list[ScoredHeadline]: ...`. Implemented by the real FinBERT (worker) and by test stubs.

### `saalr_core/sentiment/aggregate.py` (pure — §4.3, returns a richer honest dict)
`aggregate_sentiment(scored: list[ScoredHeadline], as_of: datetime, half_life_hours: float = 72.0,
min_weight: float = 0.1) -> dict`:
- For each headline: `age_hours = (as_of - published_at).total_seconds()/3600`;
  `time_weight = 0.5 ** (age_hours / half_life_hours)`; `weight = time_weight * confidence`;
  accumulate `total_score += score*weight`, `total_weight += weight`.
- **Honesty floor:** if `total_weight < min_weight` (thin/stale/low-confidence) →
  `{"score": 0.0, "label": "neutral", "confident": False, "n_headlines": len(scored),
    "total_weight": total_weight, "as_of": as_of.isoformat()}`.
- Else `score = total_score/total_weight` (clamped to [-1,1]); `label` from thresholds
  (`> 0.15 → bullish`, `< -0.15 → bearish`, else `neutral`); `confident: True`. Same return keys.
- Empty input → the neutral-floor branch.

### `apps/ml-worker/ml_worker/finbert.py` (torch, isolated)
- `FinBertScorer(model_name: str = "ProsusAI/finbert")` implementing `SentimentScorer`:
  - **Lazy load:** `transformers`/`torch` imported inside `_pipeline()` (module import stays cheap);
    `pipeline("text-classification", model=model_name, top_k=None)` built once and cached on the
    instance; CPU device. The ~440 MB model downloads to the HF cache on first call only.
  - `score_headlines(headlines)`: for each, `text = f"{h.title}. {h.description}".strip()` (pipeline
    truncates to the model's 512-token max); run batched; map the three class probs
    `{positive, negative, neutral}` → `score = P(positive) - P(negative)`,
    `confidence = max(prob)`, `label` = argmax (`positive→BULLISH`, `negative→BEARISH`,
    `neutral→NEUTRAL`); emit `ScoredHeadline(published_at=h.published_at, score, confidence, label,
    title=h.title)`.
- `apps/ml-worker/pyproject.toml`: `dependencies = ["saalr-core", "transformers>=4.40", "torch>=2.2"]`
  + `[tool.uv.sources] saalr-core = { workspace = true }` + the hatch wheel target `ml_worker`.

## Error handling
- `MassiveNewsProvider`: no key / HTTP error → `ProviderError` (caller's concern; C2 handles per-ticker
  isolation). `parse_news` skips malformed rows rather than raising.
- `aggregate_sentiment`: never raises on thin data — returns the neutral floor (the honesty contract).
- `FinBertScorer`: an empty `headlines` list → `[]` (no model load). Model-load failure surfaces as the
  underlying transformers exception (the env-gated live test is where that would show).

## Testing
- **`packages/core/tests` (pure, torch-free, plain `uv run pytest`):**
  - `test_news_parse` — a fixture Massive `/v2/reference/news` JSON → `parse_news` → correct
    `RawHeadline` fields (`published_at` parsed from `published_utc`, `source` from `publisher.name`,
    `tickers`); a malformed row (no title) is skipped.
  - `test_sentiment_aggregate` — a fresh bullish headline outweighs a stale one (time decay); higher
    `confidence` weights more; the **neutral floor** (`total_weight < 0.1` → `score 0.0,
    confident False`); empty list → neutral; a strongly-bullish set → `score > 0, label "bullish"`.
  - `test_sentiment_pipeline` — an **inline deterministic stub scorer** (keyword-based; implements
    `SentimentScorer`) over fixture `RawHeadline`s → `aggregate_sentiment` → the honest dict
    end-to-end (no network, no torch).
- **`apps/ml-worker/tests/test_finbert_live.py` (env-gated, opt-in):**
  - `@pytest.mark.skipif(not os.environ.get("SAALR_LIVE_FINBERT"), reason="opt-in: downloads FinBERT")`
    — `FinBertScorer().score_headlines([...])` on a clearly-bullish and a clearly-bearish headline →
    first `Label.BULLISH` and `score > 0`, second `Label.BEARISH` and `score < 0`. Run with
    `uv run --package saalr-ml-worker pytest apps/ml-worker/tests -v` + `SAALR_LIVE_FINBERT=1`.
  - An env-gated **live news smoke** (real `MASSIVE_API_KEY`): `MassiveNewsProvider.get_news("AAPL")`
    returns ≥1 `RawHeadline` (skipped without the key, mirroring the existing market live smokes).
- **Gate:** `uv run pytest packages/core/tests` (torch-free) + `uvx ruff check`. A short runbook note
  documents how to run the opt-in live tests (and that the first FinBERT run downloads the model).

## Out of scope (→ C2)
- The `news_sentiment` table + migration; the ml-worker fetch→score→aggregate→**persist** loop; the
  `GET /v1/market/sentiment` endpoint; wiring the score into the Monte-Carlo `drift_adjust`
  (Premium); news dedup / incremental cursors / multi-ticker batching; a shared reusable
  `StubScorer` (C1 uses an inline test stub); per-source credibility weighting; non-US news.
