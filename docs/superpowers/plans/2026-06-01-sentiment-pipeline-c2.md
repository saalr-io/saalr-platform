# Sentiment pipeline C2 (persist + API + MC wiring) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist per-ticker FinBERT sentiment (`news_sentiment` table), refresh it via a thin ml-worker CLI, expose `GET /v1/market/sentiment`, and wire the score into the Monte-Carlo `drift_adjust` honestly (apply only when present + confident + fresh).

**Architecture:** Torch-free pipeline + repo in `saalr-core` (injected `SentimentScorer`); a thin ml-worker CLI wires the real `FinBertScorer`; the API read endpoint + MC wiring reuse `require_ml_forecast` and the C1/B pure pieces.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Alembic (sync psycopg2), FastAPI, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-06-01-sentiment-pipeline-c2-design.md`

**Conventions / facts (verified):**
- `from __future__ import annotations` at the top of every module.
- Migrations live in `infra/migrations/versions/`; latest is `0003`. Pattern (`0003_instruments.py`): `revision`, `down_revision`, `op.execute("""CREATE TABLE … ; CREATE INDEX … ; GRANT … TO saalr_app;""")` + a `downgrade()` dropping the table. The integration conftest runs `alembic upgrade head` once per session.
- Models live in `saalr_core/db/models/market_data.py` (imported via `saalr_core.db.models`). `test_schema_matches_models` asserts **model column names == DB column names** for every `Base.metadata` table — so the `NewsSentiment` model and the `0004` columns must match exactly.
- `saalr_core.ids.new_id()` → UUID. `aggregate_sentiment(...)` (C1) returns `{"score","label","confident","n_headlines","total_weight","as_of"(ISO str)}`.
- C1 pieces: `saalr_core.marketdata.news.{RawHeadline, MassiveNewsProvider}`, `saalr_core.sentiment.types.{Label, ScoredHeadline, SentimentScorer}`, `saalr_core.sentiment.aggregate.aggregate_sentiment`, `apps/ml-worker/ml_worker/finbert.FinBertScorer`.
- B piece: `saalr_ml.montecarlo.sentiment_adjusted_drift(sentiment, sigma, t_years)` and `monte_carlo_pop(..., drift_adjust=...)`.
- Gate reuse: `apps/api/saalr_api/forecast/gating.require_ml_forecast` (402 free).
- Integration env: Postgres 55432, Redis 6379. Export before pytest:
  ```bash
  export ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr"
  export APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr"
  ```
- `app_sessionmaker` fixture = the `saalr_app` role; `admin_engine` = postgres. Pro upgrade: `tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]` then `UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t`.
- ml-worker tests run under `uv run --package saalr-ml-worker pytest …` (torch installed; the `sentiment` CLI lazy-imports `FinBertScorer` so the parser test never loads torch).

---

## Task 1: `news_sentiment` migration + model + repo

**Files:**
- Create: `infra/migrations/versions/0004_news_sentiment.py`
- Modify: `packages/core/saalr_core/db/models/market_data.py` (+ `NewsSentiment`)
- Create: `packages/core/saalr_core/sentiment/repo.py`

- [ ] **Step 1: Write the migration**

```python
# infra/migrations/versions/0004_news_sentiment.py
"""news_sentiment table for FinBERT sentiment aggregates

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-01
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE news_sentiment (
          sentiment_id  UUID PRIMARY KEY,
          symbol        TEXT NOT NULL,
          market        CHAR(2) NOT NULL,
          score         DOUBLE PRECISION NOT NULL,
          label         TEXT NOT NULL,
          confident     BOOLEAN NOT NULL,
          n_headlines   INTEGER NOT NULL,
          total_weight  DOUBLE PRECISION NOT NULL,
          as_of         TIMESTAMPTZ NOT NULL,
          computed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX idx_news_sentiment_symbol
          ON news_sentiment(symbol, market, computed_at DESC);

        -- non-RLS shared market data; the worker INSERTs, the API SELECTs
        GRANT SELECT, INSERT ON news_sentiment TO saalr_app;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS news_sentiment;")
```

- [ ] **Step 2: Add the model (columns must match the migration exactly)**

In `packages/core/saalr_core/db/models/market_data.py`:
- Extend the imports: add `Float, Integer` to the `sqlalchemy` import line; add
  `from sqlalchemy.dialects.postgresql import UUID as PG_UUID` (keep the existing `TIMESTAMP` import);
  add `from uuid import UUID` and `from saalr_core.ids import new_id` at the top.
- Append:

```python
class NewsSentiment(Base):
    __tablename__ = "news_sentiment"
    sentiment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    confident: Mapped[bool] = mapped_column(Boolean, nullable=False)
    n_headlines: Mapped[int] = mapped_column(Integer, nullable=False)
    total_weight: Mapped[float] = mapped_column(Float, nullable=False)
    as_of: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Write the repo**

```python
# packages/core/saalr_core/sentiment/repo.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.market_data import Instrument, NewsSentiment
from saalr_core.ids import new_id


async def save_sentiment(session: AsyncSession, symbol: str, market: str, agg: dict) -> None:
    session.add(
        NewsSentiment(
            sentiment_id=new_id(),
            symbol=symbol,
            market=market,
            score=float(agg["score"]),
            label=agg["label"],
            confident=bool(agg["confident"]),
            n_headlines=int(agg["n_headlines"]),
            total_weight=float(agg["total_weight"]),
            as_of=datetime.fromisoformat(agg["as_of"]),
        )
    )
    await session.flush()


async def latest_sentiment(session: AsyncSession, symbol: str, market: str) -> dict | None:
    row = (
        await session.execute(
            select(NewsSentiment)
            .where(NewsSentiment.symbol == symbol, NewsSentiment.market == market)
            .order_by(NewsSentiment.computed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "symbol": row.symbol,
        "market": row.market,
        "score": row.score,
        "label": row.label,
        "confident": row.confident,
        "n_headlines": row.n_headlines,
        "as_of": row.as_of,
        "computed_at": row.computed_at,
    }


async def list_active_instruments(session: AsyncSession, market: str | None = None) -> list[tuple[str, str]]:
    stmt = select(Instrument.symbol, Instrument.market).where(Instrument.is_active.is_(True))
    if market is not None:
        stmt = stmt.where(Instrument.market == market)
    rows = (await session.execute(stmt.order_by(Instrument.symbol))).all()
    return [(r.symbol, r.market) for r in rows]
```

- [ ] **Step 4: Apply the migration + verify schema parity**

Run (env exported):
```bash
uv run alembic upgrade head
uv run pytest tests/integration/test_migrations.py tests/integration/test_schema_matches_models.py -q
```
Expected: migration applies; the schema test passes (the new `NewsSentiment` model columns match the `news_sentiment` table). Then `uvx ruff check infra/migrations/versions/0004_news_sentiment.py packages/core/saalr_core/db/models/market_data.py packages/core/saalr_core/sentiment/repo.py`.

- [ ] **Step 5: Commit**

```bash
git add infra/migrations/versions/0004_news_sentiment.py packages/core/saalr_core/db/models/market_data.py packages/core/saalr_core/sentiment/repo.py
git commit -m "feat(sentiment): news_sentiment table + model + repo (save/latest/instruments)"
```

---

## Task 2: Refresh pipeline (`saalr_core/sentiment/pipeline.py`)

**Files:**
- Create: `packages/core/saalr_core/sentiment/pipeline.py`
- Test: `tests/integration/test_sentiment_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_sentiment_pipeline.py
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from saalr_core.marketdata.news import RawHeadline
from saalr_core.sentiment import pipeline, repo
from saalr_core.sentiment.types import Label, ScoredHeadline

_NOW = datetime(2025, 1, 10, tzinfo=timezone.utc)


class _StubProvider:
    def __init__(self, heads):
        self._heads = heads
        self.calls = []

    async def get_news(self, symbol, limit=50, published_after=None):
        self.calls.append((symbol, published_after))
        return self._heads


class _StubScorer:
    def score_headlines(self, headlines):
        return [ScoredHeadline(h.published_at, 0.8, 0.9, Label.BULLISH, h.title) for h in headlines]


async def test_refresh_persists_and_latest_reads(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol='AAPL'"))
    heads = [RawHeadline("Acme beats", "", _NOW - timedelta(hours=2), "R", "u", ["AAPL"])]
    provider = _StubProvider(heads)
    async with app_sessionmaker() as s, s.begin():
        agg = await pipeline.refresh_symbol(s, provider, _StubScorer(), "AAPL", "US", _NOW)
    assert agg["confident"] is True and agg["score"] > 0
    # the provider was asked for news after (as_of - lookback)
    assert provider.calls[0][1] == _NOW - timedelta(hours=168)

    async with app_sessionmaker() as s:
        latest = await repo.latest_sentiment(s, "AAPL", "US")
    assert latest is not None and latest["score"] > 0 and latest["label"] == "bullish"


async def test_latest_is_none_when_empty(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol='NONE'"))
    async with app_sessionmaker() as s:
        assert await repo.latest_sentiment(s, "NONE", "US") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_sentiment_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.sentiment.pipeline'`.

- [ ] **Step 3: Write the pipeline**

```python
# packages/core/saalr_core/sentiment/pipeline.py
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.sentiment import repo
from saalr_core.sentiment.aggregate import aggregate_sentiment


async def refresh_symbol(
    session: AsyncSession,
    provider,
    scorer,
    symbol: str,
    market: str,
    as_of: datetime,
    lookback_hours: int = 168,
) -> dict:
    """Fetch recent news, score it (injected SentimentScorer), aggregate, and persist.
    Torch-free: `provider` and `scorer` are protocols, so tests inject stubs."""
    headlines = await provider.get_news(
        symbol, published_after=as_of - timedelta(hours=lookback_hours)
    )
    scored = scorer.score_headlines(headlines)
    agg = aggregate_sentiment(scored, as_of)
    await repo.save_sentiment(session, symbol, market, agg)
    return agg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_sentiment_pipeline.py -v`
Expected: PASS (2). (Runs under plain `uv run pytest` — saalr-core only, no torch; the `app_sessionmaker`/`saalr_app` write proves the migration's grant.)

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/sentiment/pipeline.py tests/integration/test_sentiment_pipeline.py
git add packages/core/saalr_core/sentiment/pipeline.py tests/integration/test_sentiment_pipeline.py
git commit -m "feat(sentiment): refresh_symbol pipeline (fetch -> score -> aggregate -> persist)"
```

---

## Task 3: ml-worker CLI (`sentiment` command, torch-lazy)

**Files:**
- Create: `apps/ml-worker/ml_worker/cli.py`
- Create: `apps/ml-worker/ml_worker/__main__.py`
- Test: `apps/ml-worker/tests/test_cli_parser.py`

- [ ] **Step 1: Write the failing parser test**

```python
# apps/ml-worker/tests/test_cli_parser.py
def test_sentiment_subcommand_parses():
    from ml_worker.cli import build_parser

    args = build_parser().parse_args(["sentiment", "--market", "US", "--lookback-hours", "72"])
    assert args.cmd == "sentiment" and args.market == "US" and args.lookback_hours == 72
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --package saalr-ml-worker pytest apps/ml-worker/tests/test_cli_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ml_worker.cli'`.

- [ ] **Step 3: Write the CLI + entrypoint**

```python
# apps/ml-worker/ml_worker/cli.py
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker
from saalr_core.marketdata.news import MassiveNewsProvider
from saalr_core.marketdata.provider import ProviderError
from saalr_core.sentiment import pipeline, repo


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ml_worker", description="Saalr ML worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sentiment", help="refresh news sentiment for active instruments")
    s.add_argument("--market", default=None)
    s.add_argument("--lookback-hours", type=int, default=168, dest="lookback_hours")
    return p


async def _cmd_sentiment(args) -> None:
    from .finbert import FinBertScorer  # lazy: torch/transformers load only here

    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    sm = create_sessionmaker(engine)
    provider = MassiveNewsProvider(settings.massive_api_key)
    scorer = FinBertScorer()
    now = datetime.now(timezone.utc)
    try:
        async with sm() as s:
            instruments = await repo.list_active_instruments(s, args.market)
        for symbol, market in instruments:
            try:
                async with sm() as s, s.begin():
                    agg = await pipeline.refresh_symbol(
                        s, provider, scorer, symbol, market, now, args.lookback_hours
                    )
                print(f"{symbol}: {agg['label']} {agg['score']:.3f}")
            except ProviderError as exc:
                print(f"{symbol}: FAILED {exc}")
    finally:
        await engine.dispose()


_DISPATCH = {"sentiment": _cmd_sentiment}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
```

```python
# apps/ml-worker/ml_worker/__main__.py
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --package saalr-ml-worker pytest apps/ml-worker/tests/test_cli_parser.py -v`
Expected: PASS (1). `build_parser` imports `ml_worker.cli`, which imports `FinBertScorer` only inside `_cmd_sentiment`, so the parser test never loads torch. Quick smoke: `uv run --package saalr-ml-worker python -m ml_worker --help` lists the `sentiment` subcommand.

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check apps/ml-worker/ml_worker/cli.py apps/ml-worker/ml_worker/__main__.py apps/ml-worker/tests/test_cli_parser.py
git add apps/ml-worker/ml_worker/cli.py apps/ml-worker/ml_worker/__main__.py apps/ml-worker/tests/test_cli_parser.py
git commit -m "feat(ml-worker): sentiment refresh CLI (torch lazy-loaded)"
```

---

## Task 4: Read API (`GET /v1/market/sentiment`)

**Files:**
- Create: `apps/api/saalr_api/sentiment/__init__.py` (empty)
- Create: `apps/api/saalr_api/sentiment/router.py`
- Modify: `apps/api/saalr_api/main.py` (register the router)
- Test: `tests/integration/test_sentiment_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_sentiment_api.py
import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tid):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tid})


async def _seed_sentiment(admin_engine, symbol, score=0.6, label="bullish"):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol=:s"), {"s": symbol})
        await conn.execute(
            text(
                """INSERT INTO news_sentiment
                   (sentiment_id, symbol, market, score, label, confident, n_headlines,
                    total_weight, as_of, computed_at)
                   VALUES (gen_random_uuid(), :s, 'US', :sc, :lb, true, 5, 3.2, now(), now())"""
            ),
            {"s": symbol, "sc": score, "lb": label},
        )


async def test_sentiment_pro_has_data(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:sent-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_sentiment(admin_engine, "AAPL", score=0.6, label="bullish")

            r = await c.get("/v1/market/sentiment?ticker=AAPL", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["has_data"] is True and body["label"] == "bullish"
            assert abs(body["score"] - 0.6) < 1e-9 and body["computed_at"] is not None


async def test_sentiment_free_is_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:sent-free@x.com"}
            r = await c.get("/v1/market/sentiment?ticker=AAPL", headers=h)
            assert r.status_code == 402


async def test_sentiment_unknown_is_neutral(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:sent-none@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            async with admin_engine.begin() as conn:
                await conn.execute(text("DELETE FROM news_sentiment WHERE symbol='ZZZZ'"))
            r = await c.get("/v1/market/sentiment?ticker=ZZZZ", headers=h)
            assert r.status_code == 200
            body = r.json()
            assert body["has_data"] is False and body["score"] == 0.0 and body["confident"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_sentiment_api.py -v`
Expected: FAIL — 404 on the route / ModuleNotFoundError on `saalr_api.sentiment`.

- [ ] **Step 3: Write the router + register it**

```python
# apps/api/saalr_api/sentiment/router.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.sentiment import repo as sentiment_repo

from ..auth import Principal
from ..forecast.gating import require_ml_forecast

router = APIRouter(prefix="/v1/market", tags=["sentiment"])


@router.get("/sentiment")
async def get_sentiment(
    ticker: str = Query(...),
    market: str = Query("US"),
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    if not ticker or not ticker.isalpha():
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "unknown ticker"}})
    if market not in ("US",):
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": "unsupported market"}})
    session, _principal = ctx
    ticker = ticker.upper()
    row = await sentiment_repo.latest_sentiment(session, ticker, market)
    if row is None:
        return {
            "ticker": ticker, "market": market, "score": 0.0, "label": "neutral",
            "confident": False, "n_headlines": 0, "has_data": False,
            "computed_at": None, "as_of": None,
        }
    return {
        "ticker": ticker, "market": market, "score": row["score"], "label": row["label"],
        "confident": row["confident"], "n_headlines": row["n_headlines"], "has_data": True,
        "computed_at": row["computed_at"].isoformat(), "as_of": row["as_of"].isoformat(),
    }
```

In `apps/api/saalr_api/main.py`: add `from .sentiment.router import router as sentiment_router` and `app.include_router(sentiment_router)` (after the forecast/montecarlo routers).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_sentiment_api.py -v`
Expected: PASS (3).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/sentiment apps/api/saalr_api/main.py tests/integration/test_sentiment_api.py
git add apps/api/saalr_api/sentiment apps/api/saalr_api/main.py tests/integration/test_sentiment_api.py
git commit -m "feat(api): GET /v1/market/sentiment (ml_forecast-gated; neutral when no data)"
```

---

## Task 5: Monte-Carlo sentiment-drift wiring

**Files:**
- Modify: `apps/api/saalr_api/montecarlo/schemas.py` (+ `use_sentiment`)
- Modify: `apps/api/saalr_api/montecarlo/router.py` (drift wiring)
- Test: append to `tests/integration/test_montecarlo.py`

- [ ] **Step 1: Add the schema field**

In `apps/api/saalr_api/montecarlo/schemas.py`, add to `MonteCarloRequest`:
```python
    use_sentiment: bool = False
```

- [ ] **Step 2: Write the failing test (append to `tests/integration/test_montecarlo.py`)**

Add this import near the top of the file: `from sqlalchemy import text` (it is already imported — reuse it). Append:

```python
async def _seed_bull_sentiment(admin_engine, symbol):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol=:s"), {"s": symbol})
        await conn.execute(
            text(
                """INSERT INTO news_sentiment
                   (sentiment_id, symbol, market, score, label, confident, n_headlines,
                    total_weight, as_of, computed_at)
                   VALUES (gen_random_uuid(), :s, 'US', 0.8, 'bullish', true, 6, 4.0, now(), now())"""
            ),
            {"s": symbol},
        )


async def test_montecarlo_sentiment_raises_call_pop(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-sent@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)
            await _seed_bull_sentiment(admin_engine, "AAPL")

            base = await c.post(
                "/v1/strategies/montecarlo",
                json={"config": _long_call_config(), "use_sentiment": False}, headers=h,
            )
            withs = await c.post(
                "/v1/strategies/montecarlo",
                json={"config": _long_call_config(), "use_sentiment": True}, headers=h,
            )
            assert base.status_code == 200 and withs.status_code == 200
            assert withs.json()["sentiment"]["applied"] is True
            assert base.json()["sentiment"]["applied"] is False
            # bullish drift shifts terminal prices up -> a long call's POP rises
            assert withs.json()["pop"] > base.json()["pop"]


async def test_montecarlo_sentiment_no_data(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-sent2@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)
            async with admin_engine.begin() as conn:
                await conn.execute(text("DELETE FROM news_sentiment WHERE symbol='AAPL'"))
            r = await c.post(
                "/v1/strategies/montecarlo",
                json={"config": _long_call_config(), "use_sentiment": True}, headers=h,
            )
            assert r.status_code == 200
            assert r.json()["sentiment"] == {"applied": False, "reason": "no_data"}
```

> Note: the two requests in `test_montecarlo_sentiment_raises_call_pop` use the same default `seed=0`, so the only difference is the drift — the POP comparison is deterministic. `_long_call_config`, `_seed_bars`, `_make_pro`, `_client` already exist in this file.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_montecarlo.py::test_montecarlo_sentiment_raises_call_pop -v`
Expected: FAIL — the response has no `sentiment` key (KeyError) / `use_sentiment` ignored.

- [ ] **Step 4: Wire the drift into the router**

In `apps/api/saalr_api/montecarlo/router.py`:
- Add imports: `from datetime import timezone` is already imported via `datetime`; add `from saalr_ml.montecarlo import monte_carlo_pop, sentiment_adjusted_drift` (extend the existing import) and `from saalr_core.sentiment import repo as sentiment_repo`. Add a module constant `SENTIMENT_MAX_AGE_HOURS = 168`.
- Replace the final compute+return block (currently `result = monte_carlo_pop(...)` and the `return {...}`) with:

```python
    drift_adjust = 0.0
    sentiment_out: dict = {"applied": False, "reason": "not_requested"}
    if body.use_sentiment:
        sent = await sentiment_repo.latest_sentiment(session, underlying, market)
        if sent is None:
            sentiment_out = {"applied": False, "reason": "no_data"}
        elif not sent["confident"]:
            sentiment_out = {"applied": False, "reason": "low_confidence"}
        else:
            age_h = (datetime.now(timezone.utc) - sent["computed_at"]).total_seconds() / 3600.0
            if age_h > SENTIMENT_MAX_AGE_HOURS:
                sentiment_out = {"applied": False, "reason": "stale"}
            else:
                drift_adjust = sentiment_adjusted_drift(sent["score"], sigma, t_years)
                sentiment_out = {
                    "applied": True, "score": sent["score"], "label": sent["label"],
                    "computed_at": sent["computed_at"].isoformat(),
                }

    result = monte_carlo_pop(
        legs, spot, t_years, sigma, rate, drift_adjust=drift_adjust, paths=body.paths, seed=body.seed
    )
    return {
        **result,
        "underlying": underlying,
        "market": market,
        "spot": spot,
        "sigma": sigma,
        "sigma_source": sigma_source,
        "horizon_days": days,
        "rate": rate,
        "sentiment": sentiment_out,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_montecarlo.py -v`
Expected: PASS — the 2 new sentiment tests + the existing MC tests (the added `sentiment` key doesn't break them).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/montecarlo tests/integration/test_montecarlo.py
git add apps/api/saalr_api/montecarlo tests/integration/test_montecarlo.py
git commit -m "feat(api): Monte-Carlo use_sentiment drift (apply only when present+confident+fresh)"
```

---

## Task 6: Full gate

**Files:** none (verification only). 55432 + Redis up.

- [ ] **Step 1: Core suite**

Run: `uv run pytest packages/core/tests -q`
Expected: green.

- [ ] **Step 2: Integration (sentiment + MC + forecast regression), torch-free**

Run: `uv run pytest tests/integration/test_sentiment_pipeline.py tests/integration/test_sentiment_api.py tests/integration/test_montecarlo.py tests/integration/test_vol_forecast.py tests/integration/test_schema_matches_models.py -q`
Expected: all green.

- [ ] **Step 3: ml-worker CLI parser**

Run: `uv run --package saalr-ml-worker pytest apps/ml-worker/tests -q`
Expected: green (the live FinBERT test stays skipped; the new sentiment parser test passes).

- [ ] **Step 4: Lint**

Run: `uvx ruff check packages/core/saalr_core/sentiment apps/api/saalr_api/sentiment apps/api/saalr_api/montecarlo apps/ml-worker/ml_worker`
Expected: clean.

- [ ] **Step 5: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "chore(sentiment): C2 — suite + lint green"
```

---

## Self-review notes (addressed)

- **Spec coverage:** table+model+repo (T1, schema-parity verified by the existing test), torch-free pipeline (T2), thin lazy-torch CLI (T3), gated read endpoint with neutral-when-empty (T4), MC `use_sentiment` drift applied only when present+confident+fresh else 0+reason (T5), gate (T6).
- **Schema parity:** `NewsSentiment` column names exactly match `0004` (`sentiment_id, symbol, market, score, label, confident, n_headlines, total_weight, as_of, computed_at`); `test_schema_matches_models` enforces it in T1 Step 4.
- **torch isolation:** pipeline/repo/API are saalr-core/saalr-api (torch-free); only the CLI command lazy-imports `FinBertScorer`, so the parser test and all integration tests run without loading torch.
- **Honesty:** `aggregate_sentiment`'s neutral floor flows through; the read endpoint returns neutral `has_data:false` when empty; MC drift is 0 with an explicit `reason` for no_data/low_confidence/stale.
- **Type consistency:** `save_sentiment` consumes the `aggregate_sentiment` dict keys (`score/label/confident/n_headlines/total_weight/as_of`) and parses `as_of` ISO→datetime; `latest_sentiment` returns aware datetimes; the MC wiring reads `sent["score"/"confident"/"computed_at"/"label"]` and calls `sentiment_adjusted_drift(score, sigma, t_years)`; the same-seed POP comparison isolates the drift effect.
- **Grant:** `0004` explicitly grants `SELECT, INSERT` to `saalr_app`; the T2 pipeline test (writing as `saalr_app`) proves it.
