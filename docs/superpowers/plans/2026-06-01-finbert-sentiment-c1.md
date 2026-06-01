# FinBERT sentiment C1 (engine + news adapter) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reusable sentiment-scoring core — a Massive news adapter, the pure §4.3 time-decay/confidence aggregation with a neutral honesty floor, the core types + a `SentimentScorer` protocol, and a real FinBERT scorer (torch, isolated in `apps/ml-worker`) behind that protocol.

**Architecture:** Pure pieces in `saalr-core` (news adapter + `sentiment/`), torch-only piece in `apps/ml-worker`. The default test suite is torch-free (an inline stub stands in for the model); the real model is exercised only by an env-gated opt-in test.

**Tech Stack:** Python 3.12, httpx, transformers + torch (ml-worker only), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-06-01-finbert-sentiment-c1-design.md`

**Conventions / facts (verified):**
- `from __future__ import annotations` at the top of every module.
- News adapter mirrors `saalr_core/marketdata/aggregates.py` exactly: a pure `parse_*` function + a provider class with the SAME `_get` retry helper (`_RETRYABLE = {429,500,502,503,504}`, 3 attempts, 0.5·(n+1)s backoff) and `next_url` pagination (seen-set bounded). `ProviderError` is in `saalr_core/marketdata/provider.py`. The existing `_get` is duplicated per provider (massive.py, aggregates.py) — follow that pattern, don't refactor a shared base.
- `_BASE = "https://api.massive.com"`. Massive news endpoint: `GET /v2/reference/news?ticker=&limit=&order=desc&sort=published_utc&apiKey=` → `{"results":[{title, description, published_utc, publisher:{name}, article_url, tickers:[...]}], "next_url": ...}`.
- Live-smoke gate pattern (`tests/integration/test_market_smoke.py`): module-level `pytestmark = pytest.mark.skipif(not os.environ.get("RUN_LIVE_SMOKE"), ...)` + per-test `@pytest.mark.skipif(not _settings.massive_api_key, ...)`.
- `apps/ml-worker` is a stub (`saalr-ml-worker`, deps `[]`, README placeholder). It is NOT a root dependency, so `uv sync` / `uv run pytest` at the root never install torch; only `uv sync --package saalr-ml-worker` does. Pure core tests run under plain `uv run pytest packages/core/tests`.
- ProsusAI/finbert via `transformers.pipeline("text-classification", model=..., top_k=None)` returns, per input text, a list of `{"label","score"}` for the 3 classes `positive/negative/neutral`.

---

## Task 1: Massive news adapter (`saalr_core/marketdata/news.py`)

**Files:**
- Create: `packages/core/saalr_core/marketdata/news.py`
- Test: `packages/core/tests/test_news_parse.py`
- Modify: `tests/integration/test_market_smoke.py` (append an env-gated live news smoke)

- [ ] **Step 1: Write the failing parse test**

```python
# packages/core/tests/test_news_parse.py
from saalr_core.marketdata.news import parse_news

_RESULTS = [
    {"title": "Acme beats earnings", "description": "Strong quarter.",
     "published_utc": "2024-03-01T13:30:00Z", "publisher": {"name": "Reuters"},
     "article_url": "http://x/1", "tickers": ["ACME"]},
    {"description": "no title", "published_utc": "2024-03-01T14:00:00Z"},   # skipped: no title
    {"title": "No timestamp", "publisher": {"name": "AP"}},                  # skipped: no published_utc
]


def test_parse_news_maps_fields_and_skips_malformed():
    rows = parse_news(_RESULTS)
    assert len(rows) == 1
    h = rows[0]
    assert h.title == "Acme beats earnings"
    assert h.description == "Strong quarter."
    assert h.source == "Reuters" and h.url == "http://x/1"
    assert h.tickers == ["ACME"]
    assert h.published_at.tzinfo is not None
    assert h.published_at.year == 2024 and h.published_at.month == 3 and h.published_at.hour == 13


def test_parse_news_handles_missing_optionals():
    rows = parse_news([{"title": "t", "published_utc": "2024-03-01T00:00:00Z"}])
    assert len(rows) == 1
    assert rows[0].description == "" and rows[0].source == "" and rows[0].tickers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_news_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.marketdata.news'`.

- [ ] **Step 3: Write the adapter**

```python
# packages/core/saalr_core/marketdata/news.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from .provider import ProviderError

_BASE = "https://api.massive.com"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RawHeadline:
    title: str
    description: str
    published_at: datetime
    source: str
    url: str
    tickers: list[str] = field(default_factory=list)


def _parse_dt(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def parse_news(results: list[dict]) -> list[RawHeadline]:
    """Pure: map Massive /v2/reference/news rows into RawHeadline; skip malformed rows."""
    out: list[RawHeadline] = []
    for r in results:
        title = r.get("title")
        published = _parse_dt(r.get("published_utc", ""))
        if not title or published is None:
            continue
        publisher = r.get("publisher") or {}
        source = publisher.get("name", "") if isinstance(publisher, dict) else ""
        out.append(
            RawHeadline(
                title=title,
                description=r.get("description") or "",
                published_at=published,
                source=source,
                url=r.get("article_url", "") or "",
                tickers=list(r.get("tickers") or []),
            )
        )
    return out


class MassiveNewsProvider:
    def __init__(self, api_key: str | None, *, base_url: str = _BASE) -> None:
        self._api_key = api_key
        self._base = base_url

    async def _get(self, client: httpx.AsyncClient, url: str, params: dict) -> dict:
        for attempt in range(3):
            try:
                r = await client.get(url, params=params)
                if r.status_code in _RETRYABLE:
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    raise ProviderError(f"massive returned {r.status_code} after retries")
                r.raise_for_status()
                return r.json()
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
        if not self._api_key:
            raise ProviderError("no massive api key configured")
        out: list[RawHeadline] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self._base}/v2/reference/news"
            params: dict = {
                "ticker": ticker,
                "limit": limit,
                "order": "desc",
                "sort": "published_utc",
                "apiKey": self._api_key,
            }
            if published_after is not None:
                params["published_utc.gte"] = published_after.isoformat()
            seen: set[str] = set()
            while url and url not in seen:
                seen.add(url)
                data = await self._get(client, url, params)
                out.extend(parse_news(data.get("results", []) or []))
                url = data.get("next_url")
                params = {"apiKey": self._api_key}
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_news_parse.py -v`
Expected: PASS (2).

- [ ] **Step 5: Append the env-gated live news smoke**

In `tests/integration/test_market_smoke.py`, add the import `from saalr_core.marketdata.news import MassiveNewsProvider` (with the others) and append:

```python
@pytest.mark.skipif(not _settings.massive_api_key, reason="no MASSIVE_API_KEY")
async def test_massive_news_live():
    rows = await MassiveNewsProvider(_settings.massive_api_key).get_news("AAPL", limit=5)
    assert len(rows) >= 1 and rows[0].title
```

(The module-level `RUN_LIVE_SMOKE` skip already guards the whole file.)

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/marketdata/news.py packages/core/tests/test_news_parse.py tests/integration/test_market_smoke.py
git add packages/core/saalr_core/marketdata/news.py packages/core/tests/test_news_parse.py tests/integration/test_market_smoke.py
git commit -m "feat(marketdata): Massive news adapter (parse_news + MassiveNewsProvider)"
```

---

## Task 2: Sentiment core — types, protocol, aggregation

**Files:**
- Create: `packages/core/saalr_core/sentiment/__init__.py` (empty)
- Create: `packages/core/saalr_core/sentiment/types.py`
- Create: `packages/core/saalr_core/sentiment/aggregate.py`
- Test: `packages/core/tests/test_sentiment.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_sentiment.py
from datetime import datetime, timedelta, timezone

from saalr_core.marketdata.news import RawHeadline
from saalr_core.sentiment.aggregate import aggregate_sentiment
from saalr_core.sentiment.types import Label, ScoredHeadline, SentimentScorer

_NOW = datetime(2024, 3, 10, tzinfo=timezone.utc)


def _sh(score, conf, age_hours, title="x"):
    lab = Label.BULLISH if score > 0 else Label.BEARISH if score < 0 else Label.NEUTRAL
    return ScoredHeadline(_NOW - timedelta(hours=age_hours), score, conf, lab, title)


def test_empty_is_neutral_floor():
    out = aggregate_sentiment([], _NOW)
    assert out["score"] == 0.0 and out["confident"] is False and out["label"] == "neutral"


def test_low_confidence_hits_neutral_floor():
    out = aggregate_sentiment([_sh(0.9, 0.02, 1)], _NOW)  # weight ~0.02 < 0.1
    assert out["score"] == 0.0 and out["confident"] is False


def test_recent_bull_outweighs_stale_bear():
    out = aggregate_sentiment([_sh(0.8, 1.0, 1), _sh(-0.8, 1.0, 240)], _NOW)  # 10-day-old bear decays
    assert out["score"] > 0 and out["confident"] is True


def test_strong_bullish_set_is_labeled_bullish():
    out = aggregate_sentiment([_sh(0.7, 0.9, 2), _sh(0.8, 0.9, 5)], _NOW)
    assert out["confident"] is True and out["score"] > 0 and out["label"] == "bullish"


class _StubScorer:
    """Deterministic keyword scorer implementing SentimentScorer (no torch)."""

    _BULL = ("beats", "surges", "raises", "upgrade")
    _BEAR = ("plunges", "bankruptcy", "downgrade", "misses", "fraud")

    def score_headlines(self, headlines):
        out = []
        for h in headlines:
            t = h.title.lower()
            if any(w in t for w in self._BEAR):
                out.append(ScoredHeadline(h.published_at, -0.8, 0.9, Label.BEARISH, h.title))
            elif any(w in t for w in self._BULL):
                out.append(ScoredHeadline(h.published_at, 0.8, 0.9, Label.BULLISH, h.title))
            else:
                out.append(ScoredHeadline(h.published_at, 0.0, 0.3, Label.NEUTRAL, h.title))
        return out


def test_pipeline_stub_to_aggregate():
    scorer: SentimentScorer = _StubScorer()
    heads = [
        RawHeadline("Acme beats earnings", "", _NOW - timedelta(hours=2), "R", "u", ["ACME"]),
        RawHeadline("Acme raises guidance", "", _NOW - timedelta(hours=5), "R", "u", ["ACME"]),
    ]
    out = aggregate_sentiment(scorer.score_headlines(heads), _NOW)
    assert out["label"] == "bullish" and out["confident"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_sentiment.py -v`
Expected: FAIL — `ModuleNotFoundError` for `saalr_core.sentiment.*`.

- [ ] **Step 3: Write the modules**

```python
# packages/core/saalr_core/sentiment/types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from saalr_core.marketdata.news import RawHeadline


class Label(str, Enum):
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"


@dataclass(frozen=True)
class ScoredHeadline:
    published_at: datetime
    score: float        # [-1, 1]
    confidence: float   # [0, 1]
    label: Label
    title: str


class SentimentScorer(Protocol):
    def score_headlines(self, headlines: list[RawHeadline]) -> list[ScoredHeadline]: ...
```

```python
# packages/core/saalr_core/sentiment/aggregate.py
from __future__ import annotations

from datetime import datetime

from .types import ScoredHeadline

_BULL_THRESHOLD = 0.15
_BEAR_THRESHOLD = -0.15


def aggregate_sentiment(
    scored: list[ScoredHeadline],
    as_of: datetime,
    half_life_hours: float = 72.0,
    min_weight: float = 0.1,
) -> dict:
    """Time-decayed, confidence-weighted mean sentiment (LLD §4.3). Returns the neutral
    floor (score 0.0, confident False) when the accumulated weight is below min_weight —
    never forcing a directional signal from thin or stale data."""
    total_score = 0.0
    total_weight = 0.0
    for h in scored:
        age_hours = (as_of - h.published_at).total_seconds() / 3600.0
        time_weight = 0.5 ** (age_hours / half_life_hours)
        weight = time_weight * h.confidence
        total_score += h.score * weight
        total_weight += weight

    n = len(scored)
    if total_weight < min_weight:
        return {
            "score": 0.0,
            "label": "neutral",
            "confident": False,
            "n_headlines": n,
            "total_weight": total_weight,
            "as_of": as_of.isoformat(),
        }

    score = max(-1.0, min(1.0, total_score / total_weight))
    label = "bullish" if score > _BULL_THRESHOLD else "bearish" if score < _BEAR_THRESHOLD else "neutral"
    return {
        "score": score,
        "label": label,
        "confident": True,
        "n_headlines": n,
        "total_weight": total_weight,
        "as_of": as_of.isoformat(),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_sentiment.py -v`
Expected: PASS (5).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/sentiment packages/core/tests/test_sentiment.py
git add packages/core/saalr_core/sentiment packages/core/tests/test_sentiment.py
git commit -m "feat(sentiment): pure types + SentimentScorer protocol + §4.3 aggregation"
```

---

## Task 3: FinBERT scorer (`apps/ml-worker`, torch-isolated)

**Files:**
- Modify: `apps/ml-worker/pyproject.toml` (deps + sources + wheel target)
- Create: `apps/ml-worker/ml_worker/__init__.py` (empty)
- Create: `apps/ml-worker/ml_worker/finbert.py`
- Create: `apps/ml-worker/tests/test_finbert_live.py`
- Create: `docs/runbooks/finbert-sentiment.md`

- [ ] **Step 1: Update the package manifest**

```toml
# apps/ml-worker/pyproject.toml
[project]
name = "saalr-ml-worker"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "saalr-core",
  "transformers>=4.40",
  "torch>=2.2",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["ml_worker"]

[tool.uv.sources]
saalr-core = { workspace = true }
```

- [ ] **Step 2: Write the FinBERT scorer**

```python
# apps/ml-worker/ml_worker/finbert.py
from __future__ import annotations

from saalr_core.marketdata.news import RawHeadline
from saalr_core.sentiment.types import Label, ScoredHeadline

_LABEL_MAP = {
    "positive": Label.BULLISH,
    "negative": Label.BEARISH,
    "neutral": Label.NEUTRAL,
}


class FinBertScorer:
    """SentimentScorer backed by ProsusAI/finbert. torch + transformers are imported
    lazily inside _pipeline(), so importing this module is cheap and torch only loads
    when the scorer is actually used (e.g. the env-gated live test or the C2 worker)."""

    def __init__(self, model_name: str = "ProsusAI/finbert") -> None:
        self._model_name = model_name
        self._pipe = None

    def _pipeline(self):
        if self._pipe is None:
            from transformers import pipeline  # lazy: torch/transformers loaded on first use

            self._pipe = pipeline("text-classification", model=self._model_name, top_k=None)
        return self._pipe

    def score_headlines(self, headlines: list[RawHeadline]) -> list[ScoredHeadline]:
        if not headlines:
            return []
        pipe = self._pipeline()
        texts = [f"{h.title}. {h.description}".strip() for h in headlines]
        results = pipe(texts, truncation=True, max_length=512)
        out: list[ScoredHeadline] = []
        for h, res in zip(headlines, results):
            probs = {r["label"].lower(): float(r["score"]) for r in res}
            score = probs.get("positive", 0.0) - probs.get("negative", 0.0)
            top = max(res, key=lambda r: r["score"])
            label = _LABEL_MAP.get(top["label"].lower(), Label.NEUTRAL)
            out.append(
                ScoredHeadline(
                    published_at=h.published_at,
                    score=score,
                    confidence=float(top["score"]),
                    label=label,
                    title=h.title,
                )
            )
        return out
```

- [ ] **Step 3: Write the env-gated live test**

```python
# apps/ml-worker/tests/test_finbert_live.py
import os
from datetime import datetime, timezone

import pytest

from saalr_core.marketdata.news import RawHeadline
from saalr_core.sentiment.types import Label

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAALR_LIVE_FINBERT"),
    reason="set SAALR_LIVE_FINBERT=1 to download + run the real FinBERT model",
)


def _h(title: str) -> RawHeadline:
    return RawHeadline(title, "", datetime(2024, 3, 1, tzinfo=timezone.utc), "R", "u", ["ACME"])


def test_finbert_is_directional():
    from ml_worker.finbert import FinBertScorer

    scored = FinBertScorer().score_headlines(
        [
            _h("Acme beats earnings and raises full-year guidance"),
            _h("Acme plunges after disclosing an accounting-fraud probe"),
        ]
    )
    assert scored[0].label == Label.BULLISH and scored[0].score > 0
    assert scored[1].label == Label.BEARISH and scored[1].score < 0
```

- [ ] **Step 4: Write the runbook note**

```markdown
# Runbook — FinBERT sentiment (C1)

The sentiment-scoring core: a Massive news adapter (`saalr_core/marketdata/news.py`), the pure
time-decay aggregation (`saalr_core/sentiment/`), and the real FinBERT scorer
(`apps/ml-worker/ml_worker/finbert.py`, torch + transformers).

## torch is opt-in
`apps/ml-worker` is NOT a root dependency, so normal `uv sync` / `uv run pytest` never install
torch. The default test gate (`uv run pytest packages/core/tests`) is torch-free — an inline stub
stands in for the model.

## Run the real model (downloads ~440 MB on first run)
```bash
uv sync --package saalr-ml-worker            # installs torch (CPU) + transformers
SAALR_LIVE_FINBERT=1 uv run --package saalr-ml-worker pytest apps/ml-worker/tests -v
```
The first run downloads `ProsusAI/finbert` to the Hugging Face cache (`~/.cache/huggingface`).

## Live news smoke (needs a Massive news entitlement)
```bash
RUN_LIVE_SMOKE=1 uv run pytest tests/integration/test_market_smoke.py::test_massive_news_live -v
```
```

- [ ] **Step 5: Verify the package builds + imports (installs torch CPU, one-time)**

Run:
```bash
uv sync --package saalr-ml-worker
uv run --package saalr-ml-worker python -c "import ml_worker.finbert; print('import ok')"
uv run --package saalr-ml-worker pytest apps/ml-worker/tests -v   # the live test is SKIPPED (no env var)
```
Expected: `import ok` (the module imports without loading torch — torch is lazy); the live test collects and **skips**. This proves the package builds and the scorer module is importable. Do NOT set `SAALR_LIVE_FINBERT` here — running the real model (440 MB download + inference) is an optional, separate validation. If the torch install is prohibitively slow, report that and rely on the ruff check + the skip-collection as the verification.

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check apps/ml-worker/ml_worker/finbert.py apps/ml-worker/tests/test_finbert_live.py
git add apps/ml-worker/pyproject.toml apps/ml-worker/ml_worker apps/ml-worker/tests docs/runbooks/finbert-sentiment.md uv.lock
git commit -m "feat(ml-worker): FinBERT scorer (torch-isolated, lazy-loaded) + runbook"
```

---

## Task 4: Gate

**Files:** none (verification only).

- [ ] **Step 1: Core suite (torch-free)**

Run: `uv run pytest packages/core/tests -q`
Expected: all green (includes the new news-parse + sentiment tests; no torch pulled).

- [ ] **Step 2: Lint**

Run: `uvx ruff check packages/core/saalr_core/marketdata/news.py packages/core/saalr_core/sentiment apps/ml-worker`
Expected: clean.

- [ ] **Step 3: Confirm the default gate is torch-free**

Run: `uv run python -c "import importlib.util, sys; print('torch present:', importlib.util.find_spec('torch') is not None)"`
Note: torch may be present if Task 3 Step 5 installed it into the shared venv. That's fine — the point is that the CORE TESTS do not import it. Confirm `packages/core/tests` passed in Step 1 without any ml_worker import.

- [ ] **Step 4: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "chore(ml): FinBERT C1 — core suite + lint green"
```

---

## Self-review notes (addressed)

- **Spec coverage:** Massive news adapter + parse + live smoke (T1), pure types/protocol + §4.3 aggregation with the neutral floor + the stub pipeline test (T2), the torch-isolated lazy FinBERT scorer + env-gated live test + runbook (T3), torch-free gate (T4).
- **torch isolation:** `apps/ml-worker` is not a root dep, so the default gate never installs torch; `finbert.py` imports torch/transformers lazily inside `_pipeline()` so even `import ml_worker.finbert` is torch-free. The fast suite uses an inline stub.
- **Honesty floor:** `aggregate_sentiment` returns `score 0.0, confident False` when `total_weight < min_weight` (and on empty input) — tested directly.
- **Type consistency:** `RawHeadline(title, description, published_at, source, url, tickers)`; `ScoredHeadline(published_at, score, confidence, label, title)`; `Label` enum string values `bearish/neutral/bullish`; FinBERT maps `positive→BULLISH / negative→BEARISH / neutral→NEUTRAL`, `score = P(pos)-P(neg)`, `confidence = max prob`. The `SentimentScorer` protocol signature matches both the stub and `FinBertScorer`.
- **Adapter parity:** `news.py` reuses the exact `_get`/pagination shape of `aggregates.py` (duplication is the established codebase pattern, not refactored).
