# Free News Source for Sentiment (RSS + Finnhub) — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorming — key decisions made via Q&A)
**Slice:** Add free news providers behind the existing `get_news` interface so the sentiment pipeline
works without the paid Massive key: **Finnhub** (free tier, when a key is present) with a no-key
**RSS** fallback (Yahoo Finance primary, Google News secondary).

## Goal

Let `ml_worker sentiment` produce news sentiment with **no paid key required**. A composite news
provider tries, in order, Finnhub (if a key is configured) then RSS (Yahoo → Google), returning the
first source that yields headlines. Existing Massive support stays available via config.

## Context (existing pieces this builds on)

- The news-provider contract is **duck-typed**: `async get_news(ticker, limit=50, published_after=None)
  -> list[RawHeadline]`, raising `ProviderError` (`saalr_core.marketdata.provider`).
  `RawHeadline(title, description, published_at: datetime, source, url, tickers: list[str])`
  (`saalr_core.marketdata.news`). `MassiveNewsProvider` is the only implementation today.
- `saalr_core.sentiment.pipeline.refresh_symbol(session, provider, scorer, symbol, market, as_of,
  lookback_hours)` calls `provider.get_news(symbol, published_after=as_of - lookback)`, scores, and
  persists. Provider is injected — no pipeline change needed.
- The **only construction site** is `apps/ml-worker/ml_worker/cli.py` `_cmd_sentiment`:
  `provider = MassiveNewsProvider(settings.massive_api_key)`. It already catches `ProviderError`
  per symbol.

**Decisions locked (via Q&A):** composite = **Finnhub when key present, else RSS**; RSS = **Yahoo
primary + Google News fallback**, parsed with **stdlib `xml.etree`** (no new dependency); honest about
free-feed noise/reliability.

## Components / files

### New providers (`packages/core/saalr_core/marketdata/`)
- **Create `news_rss.py`**
  - `parse_rss(xml_bytes: bytes, *, source: str, ticker: str) -> list[RawHeadline]` — pure; parses
    RSS 2.0 `<item>`s with `xml.etree.ElementTree`: `title`, `description` (strip HTML tags crudely),
    `pubDate` (RFC-822 → aware `datetime`; skip items with no parseable date or title), `link` → url,
    `source` = the feed source label; `tickers=[ticker]` (RSS isn't ticker-tagged). Skips malformed
    items rather than raising.
  - `RssNewsProvider` with feeds:
    - Yahoo: `https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US`
    - Google: `https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en`
    - `get_news(...)`: GET Yahoo first (httpx, 15s timeout, a real `User-Agent` header, the same
      3-try retry-on-5xx/429 pattern as Massive). If Yahoo returns 0 parsed headlines OR raises,
      try Google. Filter to `published_after` when given; truncate to `limit`. Returns `[]` if both
      feeds are reachable but empty; raises `ProviderError` only if BOTH transport-fail.
- **Create `news_finnhub.py`**
  - `parse_finnhub(rows: list[dict], *, ticker: str) -> list[RawHeadline]` — pure; maps Finnhub
    `/company-news` rows (`headline`, `summary`, `datetime` unix→aware datetime, `url`, `source`).
  - `FinnhubNewsProvider(api_key)` — `get_news(...)`: requires a key (else `ProviderError`); GETs
    `https://finnhub.io/api/v1/company-news?symbol={ticker}&from={d}&to={d}&token=…` where the date
    window is derived from `published_after` (default last 7 days) → today; same retry pattern.

### Composite + factory (`packages/core/saalr_core/marketdata/news_factory.py`)
- `CompositeNewsProvider(providers: list)` — `get_news(...)`: iterate providers in order; on a
  non-empty result, return it; on `ProviderError`, remember it and continue. After all: if any
  provider returned (even empty), return `[]`; if EVERY provider raised, re-raise the last
  `ProviderError`.
- `build_news_provider(settings) -> provider`:
  - `settings.news_provider` (`"auto"` default | `"massive"` | `"finnhub"` | `"rss"`).
  - `"auto"`: `Composite([Finnhub(key)] if finnhub_api_key else []) + [Rss()])` — Finnhub first
    when keyed, RSS fallback always present.
  - `"massive"` → `MassiveNewsProvider(massive_api_key)`; `"finnhub"` → `FinnhubNewsProvider(key)`;
    `"rss"` → `RssNewsProvider()`.

### Config (`packages/core/saalr_core/config.py`)
- Add `finnhub_api_key: str | None = None` and `news_provider: str = "auto"`.

### Wiring (`apps/ml-worker/ml_worker/cli.py`)
- Replace `provider = MassiveNewsProvider(settings.massive_api_key)` with
  `provider = build_news_provider(settings)` (import from `news_factory`). No other change — the
  per-symbol `ProviderError` handling already covers a total-failure provider.

## Error handling

- Per-provider `ProviderError` is swallowed by the composite until the last; total failure re-raises,
  so the worker logs `FAILED` for that symbol (existing behaviour).
- Empty-but-reachable feeds → `[]` → `has_data:false` sentiment (existing empty state), not an error.
- `parse_rss` / `parse_finnhub` skip malformed items; never raise on a single bad row.

## Testing (pure, no network)

- `packages/core/tests/test_news_rss.py` — `parse_rss` over a small Yahoo RSS XML fixture and a
  Google News RSS fixture → expected `RawHeadline`s (title/url/source/aware date); skips an item
  missing title/date; HTML stripped from description; `published_after` filtering (via the provider
  with an injected fake transport, OR by testing the parse + filter helper directly).
- `packages/core/tests/test_news_finnhub.py` — `parse_finnhub` over sample rows; unix→datetime;
  `FinnhubNewsProvider` with no key raises `ProviderError`.
- `packages/core/tests/test_news_factory.py` — `CompositeNewsProvider` returns the first non-empty;
  swallows a `ProviderError` from the first provider and uses the second; re-raises when all error;
  `build_news_provider` picks Finnhub-first when keyed, RSS-only when not, and honours an explicit
  `news_provider` override (inject stub providers / a settings object).
- Network GETs are NOT unit-tested; the existing `test_market_smoke.py` (live, key-gated) pattern is
  the place for any optional live check — out of scope here.

## Out of scope (YAGNI)

- No new Python dependency (stdlib `xml.etree` only; `httpx` already used).
- No live-network unit tests; no caching layer (the worker already runs as a batch job).
- No change to scoring (`FinBertScorer`), aggregation, persistence, or the sentiment API/UI.
- Per-article ticker tagging from RSS (RSS feeds aren't ticker-tagged — we attribute to the queried
  ticker).
