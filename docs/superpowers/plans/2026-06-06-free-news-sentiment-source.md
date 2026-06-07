# Free News Source for Sentiment (RSS + Finnhub) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add free news providers (Finnhub free-tier + no-key Yahoo→Google RSS) behind the existing `get_news` interface, selected by a composite factory, wired into the ml-worker.

**Architecture:** Pure parsers + thin httpx providers in `packages/core/saalr_core/marketdata/`, all implementing `async get_news(ticker, limit=50, published_after=None) -> list[RawHeadline]` and raising `ProviderError`. A `CompositeNewsProvider` + `build_news_provider(settings)` chooses sources. Stdlib `xml.etree` — no new dependency. Providers take an optional `transport=` so fallback logic is unit-testable without network.

**Tech Stack:** Python 3.12, httpx (already a dep), stdlib `xml.etree`/`email.utils`, pytest (async auto mode — write `async def test_...` with NO decorator, matching the repo's existing async tests).

**Spec:** `docs/superpowers/specs/2026-06-06-free-news-sentiment-source-design.md`

**Run core tests:** `python -m pytest packages/core/tests/test_news_rss.py packages/core/tests/test_news_finnhub.py packages/core/tests/test_news_factory.py -q` (no DB/Redis needed for these). Lint: `ruff check <files>`. Commit footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Don't touch `.env`, `.gitignore`, `tools/equity-screener`, `.omc`.

**Existing contract (do not change):** `RawHeadline(title, description, published_at: datetime, source, url, tickers: list[str])` and `ProviderError` live in `saalr_core.marketdata.news` / `.provider`.

---

### Task 1: Config — finnhub key + provider selector

**Files:** Modify `packages/core/saalr_core/config.py`

- [ ] **Step 1:** After the `massive_api_key` / market-data settings, add:
```python
    finnhub_api_key: str | None = None
    news_provider: str = "auto"  # auto | massive | finnhub | rss
```
- [ ] **Step 2:** Verify it loads: `python -c "from saalr_core.config import Settings; s=Settings(); print(s.news_provider, s.finnhub_api_key)"` → prints `auto None`.
- [ ] **Step 3:** Commit:
```bash
git add packages/core/saalr_core/config.py
git commit -m "feat(config): finnhub_api_key + news_provider selector"
```

---

### Task 2: RSS provider (Yahoo → Google) + test

**Files:**
- Create: `packages/core/saalr_core/marketdata/news_rss.py`
- Test: `packages/core/tests/test_news_rss.py`

- [ ] **Step 1: Write the failing test** `packages/core/tests/test_news_rss.py`:
```python
from datetime import datetime, timezone

import httpx

from saalr_core.marketdata.news_rss import RssNewsProvider, parse_rss

YAHOO = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Apple hits record high</title>
<description>&lt;p&gt;Shares &lt;b&gt;jump&lt;/b&gt; today&lt;/p&gt;</description>
<pubDate>Wed, 04 Jun 2026 14:30:00 GMT</pubDate><link>https://ex/1</link></item>
<item><title>No date here</title><link>https://ex/2</link></item>
</channel></rss>"""

GOOGLE = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Apple news from Google</title><description>summary</description>
<pubDate>Thu, 05 Jun 2026 09:00:00 GMT</pubDate><link>https://ex/3</link></item>
</channel></rss>"""


def test_parse_rss_maps_items_and_strips_html():
    out = parse_rss(YAHOO, source="yahoo", ticker="aapl")
    assert len(out) == 1  # the dateless item is skipped
    h = out[0]
    assert h.title == "Apple hits record high"
    assert "jump" in h.description and "<" not in h.description
    assert h.source == "yahoo" and h.tickers == ["AAPL"]
    assert h.published_at == datetime(2026, 6, 4, 14, 30, tzinfo=timezone.utc)


def test_parse_rss_bad_xml_returns_empty():
    assert parse_rss(b"not xml at all", source="yahoo", ticker="x") == []


async def test_provider_falls_back_to_google_when_yahoo_empty():
    def handler(req: httpx.Request) -> httpx.Response:
        body = GOOGLE if "news.google.com" in str(req.url) else b"<rss><channel></channel></rss>"
        return httpx.Response(200, content=body)

    p = RssNewsProvider(transport=httpx.MockTransport(handler))
    out = await p.get_news("AAPL")
    assert len(out) == 1 and out[0].source == "google"
```

- [ ] **Step 2: Run → FAIL** `python -m pytest packages/core/tests/test_news_rss.py -q` (module missing).

- [ ] **Step 3: Implement `packages/core/saalr_core/marketdata/news_rss.py`:**
```python
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

from .news import RawHeadline
from .provider import ProviderError

_YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
_GOOGLE = "https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
_UA = "Mozilla/5.0 (compatible; SaalrBot/1.0; +https://saalr.com)"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})
_TAG = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG.sub("", s or "").strip()


def _parse_pubdate(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_rss(xml_bytes: bytes, *, source: str, ticker: str) -> list[RawHeadline]:
    """Pure: map RSS 2.0 <item>s into RawHeadline. Skips items missing a title or parseable date."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    out: list[RawHeadline] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        published = _parse_pubdate(item.findtext("pubDate"))
        if not title or published is None:
            continue
        out.append(
            RawHeadline(
                title=title,
                description=_strip_html(item.findtext("description") or ""),
                published_at=published,
                source=source,
                url=(item.findtext("link") or "").strip(),
                tickers=[ticker.upper()],
            )
        )
    return out


class RssNewsProvider:
    """No-key news via public RSS: Yahoo Finance primary, Google News fallback."""

    def __init__(self, *, timeout: float = 15.0, transport: httpx.BaseTransport | None = None) -> None:
        self._timeout = timeout
        self._transport = transport

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> bytes:
        for attempt in range(3):
            try:
                r = await client.get(url, headers={"User-Agent": _UA})
                if r.status_code in _RETRYABLE:
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    raise ProviderError(f"rss returned {r.status_code} after retries")
                r.raise_for_status()
                return r.content
            except httpx.HTTPStatusError as exc:
                raise ProviderError(str(exc)) from exc
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ProviderError(str(exc)) from exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ProviderError("exhausted retries")

    async def get_news(
        self, ticker: str, limit: int = 50, published_after: datetime | None = None
    ) -> list[RawHeadline]:
        feeds = [("yahoo", _YAHOO.format(ticker=ticker)), ("google", _GOOGLE.format(ticker=ticker))]
        last_err: ProviderError | None = None
        reachable = False
        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport, follow_redirects=True
        ) as client:
            for source, url in feeds:
                try:
                    raw = await self._fetch(client, url)
                except ProviderError as exc:
                    last_err = exc
                    continue
                reachable = True
                items = parse_rss(raw, source=source, ticker=ticker)
                if published_after is not None:
                    items = [h for h in items if h.published_at >= published_after]
                if items:
                    return items[:limit]
        if not reachable and last_err is not None:
            raise last_err
        return []
```

- [ ] **Step 4: Run → PASS** `python -m pytest packages/core/tests/test_news_rss.py -q` (3 passed). If the async test errors with "async def functions are not natively supported", the repo's pytest is configured for asyncio auto mode — confirm `packages/core` is covered; if not, add the same marker the existing async core tests use. `ruff check` both files.

- [ ] **Step 5: Commit:**
```bash
git add packages/core/saalr_core/marketdata/news_rss.py packages/core/tests/test_news_rss.py
git commit -m "feat(marketdata): no-key RSS news provider (Yahoo -> Google)"
```

---

### Task 3: Finnhub provider + test

**Files:**
- Create: `packages/core/saalr_core/marketdata/news_finnhub.py`
- Test: `packages/core/tests/test_news_finnhub.py`

- [ ] **Step 1: Failing test** `packages/core/tests/test_news_finnhub.py`:
```python
from datetime import datetime, timezone

import httpx
import pytest

from saalr_core.marketdata.news_finnhub import FinnhubNewsProvider, parse_finnhub
from saalr_core.marketdata.provider import ProviderError

ROWS = [
    {"headline": "Apple beats earnings", "summary": "Strong quarter", "datetime": 1749045000,
     "url": "https://ex/1", "source": "Reuters"},
    {"headline": "", "datetime": 1749045000},  # skipped: no title
    {"headline": "No timestamp"},               # skipped: no datetime
]


def test_parse_finnhub_maps_rows():
    out = parse_finnhub(ROWS, ticker="aapl")
    assert len(out) == 1
    h = out[0]
    assert h.title == "Apple beats earnings" and h.source == "Reuters"
    assert h.tickers == ["AAPL"]
    assert h.published_at == datetime.fromtimestamp(1749045000, tz=timezone.utc)


async def test_provider_requires_key():
    with pytest.raises(ProviderError):
        await FinnhubNewsProvider(None).get_news("AAPL")


async def test_provider_fetches_and_parses():
    def handler(req: httpx.Request) -> httpx.Response:
        assert "company-news" in str(req.url)
        return httpx.Response(200, json=ROWS)

    p = FinnhubNewsProvider("k", transport=httpx.MockTransport(handler))
    out = await p.get_news("AAPL")
    assert len(out) == 1 and out[0].title == "Apple beats earnings"
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `packages/core/saalr_core/marketdata/news_finnhub.py`:**
```python
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from .news import RawHeadline
from .provider import ProviderError

_BASE = "https://finnhub.io/api/v1/company-news"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


def parse_finnhub(rows: list[dict], *, ticker: str) -> list[RawHeadline]:
    """Pure: map Finnhub /company-news rows into RawHeadline; skip rows missing title or datetime."""
    out: list[RawHeadline] = []
    for r in rows:
        title = (r.get("headline") or "").strip()
        ts = r.get("datetime")
        if not title or not ts:
            continue
        try:
            published = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, OSError, TypeError):
            continue
        out.append(
            RawHeadline(
                title=title,
                description=(r.get("summary") or "").strip(),
                published_at=published,
                source=(r.get("source") or "finnhub").strip(),
                url=(r.get("url") or "").strip(),
                tickers=[ticker.upper()],
            )
        )
    return out


class FinnhubNewsProvider:
    def __init__(
        self, api_key: str | None, *, base_url: str = _BASE, timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base = base_url
        self._timeout = timeout
        self._transport = transport

    async def get_news(
        self, ticker: str, limit: int = 50, published_after: datetime | None = None
    ) -> list[RawHeadline]:
        if not self._api_key:
            raise ProviderError("no finnhub api key configured")
        end = datetime.now(timezone.utc)
        start = published_after or (end - timedelta(days=7))
        params = {
            "symbol": ticker.upper(),
            "from": start.date().isoformat(),
            "to": end.date().isoformat(),
            "token": self._api_key,
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            rows: object = []
            for attempt in range(3):
                try:
                    r = await client.get(self._base, params=params)
                    if r.status_code in _RETRYABLE:
                        if attempt < 2:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        raise ProviderError(f"finnhub returned {r.status_code} after retries")
                    r.raise_for_status()
                    rows = r.json()
                    break
                except httpx.HTTPStatusError as exc:
                    raise ProviderError(str(exc)) from exc
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        raise ProviderError(str(exc)) from exc
                    await asyncio.sleep(0.5 * (attempt + 1))
            else:
                raise ProviderError("exhausted retries")
        if not isinstance(rows, list):
            return []
        items = parse_finnhub(rows, ticker=ticker)
        if published_after is not None:
            items = [h for h in items if h.published_at >= published_after]
        return items[:limit]
```

- [ ] **Step 4: Run → PASS** (3 passed). `ruff check` both files.

- [ ] **Step 5: Commit:**
```bash
git add packages/core/saalr_core/marketdata/news_finnhub.py packages/core/tests/test_news_finnhub.py
git commit -m "feat(marketdata): Finnhub company-news provider (free tier)"
```

---

### Task 4: Composite + factory + test

**Files:**
- Create: `packages/core/saalr_core/marketdata/news_factory.py`
- Test: `packages/core/tests/test_news_factory.py`

- [ ] **Step 1: Failing test** `packages/core/tests/test_news_factory.py`:
```python
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from saalr_core.marketdata.news import RawHeadline
from saalr_core.marketdata.news_factory import CompositeNewsProvider, build_news_provider
from saalr_core.marketdata.news_finnhub import FinnhubNewsProvider
from saalr_core.marketdata.news_rss import RssNewsProvider
from saalr_core.marketdata.provider import ProviderError


def _hl(title: str) -> RawHeadline:
    return RawHeadline(title, "", datetime(2026, 6, 4, tzinfo=timezone.utc), "stub", "http://x", ["AAPL"])


class _Stub:
    def __init__(self, *, items=None, error=False):
        self._items, self._error = items or [], error
    async def get_news(self, ticker, limit=50, published_after=None):
        if self._error:
            raise ProviderError("boom")
        return self._items


@dataclass
class _Settings:
    news_provider: str = "auto"
    finnhub_api_key: str | None = None
    massive_api_key: str | None = None


async def test_composite_returns_first_non_empty():
    c = CompositeNewsProvider([_Stub(items=[]), _Stub(items=[_hl("a")]), _Stub(items=[_hl("b")])])
    out = await c.get_news("AAPL")
    assert [h.title for h in out] == ["a"]


async def test_composite_swallows_error_then_uses_next():
    c = CompositeNewsProvider([_Stub(error=True), _Stub(items=[_hl("ok")])])
    out = await c.get_news("AAPL")
    assert [h.title for h in out] == ["ok"]


async def test_composite_reraises_when_all_error():
    c = CompositeNewsProvider([_Stub(error=True), _Stub(error=True)])
    with pytest.raises(ProviderError):
        await c.get_news("AAPL")


def test_build_auto_uses_finnhub_first_then_rss_when_keyed():
    p = build_news_provider(_Settings(finnhub_api_key="k"))
    assert isinstance(p, CompositeNewsProvider)
    assert isinstance(p._providers[0], FinnhubNewsProvider)
    assert isinstance(p._providers[-1], RssNewsProvider)


def test_build_auto_is_rss_only_without_key():
    p = build_news_provider(_Settings())
    assert isinstance(p, CompositeNewsProvider)
    assert len(p._providers) == 1 and isinstance(p._providers[0], RssNewsProvider)


def test_build_respects_explicit_override():
    assert isinstance(build_news_provider(_Settings(news_provider="rss")), RssNewsProvider)
    assert isinstance(build_news_provider(_Settings(news_provider="finnhub", finnhub_api_key="k")), FinnhubNewsProvider)
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `packages/core/saalr_core/marketdata/news_factory.py`:**
```python
from __future__ import annotations

from datetime import datetime

from .news import MassiveNewsProvider, RawHeadline
from .news_finnhub import FinnhubNewsProvider
from .news_rss import RssNewsProvider
from .provider import ProviderError


class CompositeNewsProvider:
    """Try providers in order; return the first non-empty result. Swallow ProviderError until the
    last; re-raise only if EVERY provider errored (none returned anything)."""

    def __init__(self, providers: list) -> None:
        self._providers = providers

    async def get_news(
        self, ticker: str, limit: int = 50, published_after: datetime | None = None
    ) -> list[RawHeadline]:
        last_err: ProviderError | None = None
        returned = False
        for p in self._providers:
            try:
                items = await p.get_news(ticker, limit=limit, published_after=published_after)
            except ProviderError as exc:
                last_err = exc
                continue
            returned = True
            if items:
                return items
        if not returned and last_err is not None:
            raise last_err
        return []


def build_news_provider(settings):
    """Select the news provider from settings. 'auto' = Finnhub (if keyed) then RSS fallback."""
    mode = getattr(settings, "news_provider", "auto") or "auto"
    if mode == "massive":
        return MassiveNewsProvider(settings.massive_api_key)
    if mode == "finnhub":
        return FinnhubNewsProvider(settings.finnhub_api_key)
    if mode == "rss":
        return RssNewsProvider()
    providers: list = []
    if getattr(settings, "finnhub_api_key", None):
        providers.append(FinnhubNewsProvider(settings.finnhub_api_key))
    providers.append(RssNewsProvider())
    return CompositeNewsProvider(providers)
```

- [ ] **Step 4: Run → PASS** (6 passed). `ruff check` both files.

- [ ] **Step 5: Commit:**
```bash
git add packages/core/saalr_core/marketdata/news_factory.py packages/core/tests/test_news_factory.py
git commit -m "feat(marketdata): composite news provider + build_news_provider factory"
```

---

### Task 5: Wire the ml-worker + verify

**Files:** Modify `apps/ml-worker/ml_worker/cli.py`

- [ ] **Step 1:** Change the import line `from saalr_core.marketdata.news import MassiveNewsProvider` to:
```python
from saalr_core.marketdata.news_factory import build_news_provider
```
- [ ] **Step 2:** In `_cmd_sentiment`, replace `provider = MassiveNewsProvider(settings.massive_api_key)` with:
```python
    provider = build_news_provider(settings)
```
(Leave the rest — `ProviderError` handling, scorer, loop — unchanged.)

- [ ] **Step 3:** Verify the module imports and the parser is wired:
`python -c "import ml_worker.cli as c; from saalr_core.config import Settings; print(type(c.build_news_provider(Settings())).__name__)"`
Expected: prints `CompositeNewsProvider` (no Finnhub key in default settings → RSS-only composite... actually with no key it's `CompositeNewsProvider` wrapping one RssNewsProvider). If `ml_worker` isn't importable as a top-level module, run from the worker dir or use its package path; just confirm `build_news_provider(Settings())` returns a provider with a `get_news` coroutine.

- [ ] **Step 4:** `ruff check apps/ml-worker/ml_worker/cli.py`.

- [ ] **Step 5: Commit:**
```bash
git add apps/ml-worker/ml_worker/cli.py
git commit -m "feat(ml-worker): use build_news_provider (free RSS/Finnhub) for sentiment"
```

---

## Final verification (after all tasks)
- [ ] `python -m pytest packages/core/tests/test_news_rss.py packages/core/tests/test_news_finnhub.py packages/core/tests/test_news_factory.py -q` — all pass.
- [ ] `python -m pytest packages/core/tests/test_sentiment.py -q` — existing sentiment tests still pass (no contract change).
- [ ] `ruff check packages/core/saalr_core/marketdata apps/ml-worker/ml_worker/cli.py` — clean.
- [ ] Dispatch a final code-reviewer over the diff.
- [ ] Note to user: set `FINNHUB_API_KEY` in `.env` to enable the (better) Finnhub source; otherwise the worker uses no-key Yahoo→Google RSS automatically. Restart the ml-worker run to pick up config.

## Self-review notes
- **Spec coverage:** config → T1; RSS → T2; Finnhub → T3; composite+factory → T4; wiring → T5. ✅
- **Type consistency:** every provider returns `list[RawHeadline]` and raises `ProviderError`; `build_news_provider` returns either a single provider or `CompositeNewsProvider`; `get_news` signature `(ticker, limit=50, published_after=None)` matches the pipeline call and the Massive provider. ✅
- **Testability seam:** `transport=` added to RSS + Finnhub providers so fallback/fetch logic is tested via `httpx.MockTransport` without network. ✅
- **No new dependency** (stdlib xml/email.utils; httpx already present). ✅
