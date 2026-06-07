# Dev Seed Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dev-only in-app panel that injects real Massive market data on demand — backfill historical daily `bars` and capture cache-bypassing option-chain snapshots — with a browser-driven repeat loop.

**Architecture:** Two new backend endpoints under `/v1/dev/seed/*` (mounted always, gated by a router dependency that 404s unless `auth_provider=='dev'`), using a plain `sessionmaker` session to write the shared `bars` / `options_chain_snapshots` tables. Bars reuse a new shared `saalr_core.marketdata.backfill` helper; chain captures use a new cache-bypassing `MarketService.capture_snapshot`. A dev-only React page (`/app/dev`) drives them; route + sidebar link are guarded by `import.meta.env.DEV`.

**Tech Stack:** FastAPI, SQLAlchemy async, Redis (asyncio), Massive HTTP providers, React + react-router, TanStack Query (not needed here — plain fetch), Vitest, pytest.

**Spec:** [docs/superpowers/specs/2026-06-07-dev-seed-panel-design.md](../specs/2026-06-07-dev-seed-panel-design.md)

**Deviation from spec (approved during planning):** dev endpoints do **not** require `get_principal`; they gate on dev mode only and use a plain `sessionmaker` session (mirrors `/auth/dev/login` and the ingest-worker's shared-table writes). Frontend `DEV` gating + backend dev gating preserve defense-in-depth.

---

## File Structure

**Backend**
- Create `packages/core/saalr_core/marketdata/backfill.py` — shared `upsert_bars` + `backfill_symbol` (used by the dev endpoint; ingest-worker dedupe is a follow-up).
- Create `packages/core/tests/test_backfill.py` — unit tests (fake provider + fake session, no DB).
- Modify `apps/api/saalr_api/market/service.py` — extract `_build_and_persist`, add `capture_snapshot`.
- Create `packages/core/tests/test_capture_snapshot.py` — unit test for `capture_snapshot` (fake redis/provider/session). *(Lives in core/tests for a DB-free unit test; imports from `saalr_api`.)*
- Create `apps/api/saalr_api/dev/__init__.py` (empty) and `apps/api/saalr_api/dev/router.py` — the two endpoints + dev gate.
- Modify `apps/api/saalr_api/main.py` — wire `aggregates_provider` in lifespan; `include_router(dev_router)`.
- Create `tests/integration/test_dev_seed.py` — non-dev 404, bars happy path, chain accumulation.

**Frontend**
- Create `apps/web/src/lib/dev.ts` — `seedBars`, `seedChain` clients + result types.
- Create `apps/web/src/pages/DevSeed.tsx` — the panel.
- Create `apps/web/src/pages/DevSeed.test.tsx` — behavior tests.
- Modify `apps/web/src/app/Router.tsx` — DEV-guarded `/dev` route.
- Modify `apps/web/src/app/nav.ts` — add `'/dev'` to `EXTRA_LABELS` (breadcrumb label).
- Modify `apps/web/src/components/Sidebar.tsx` — DEV-guarded "Dev" link.
- Modify `apps/web/src/components/Sidebar.test.tsx` *(create if absent)* — DEV link presence/absence.

---

## Task 1: Shared bars backfill helper (`saalr-core`)

**Files:**
- Create: `packages/core/saalr_core/marketdata/backfill.py`
- Test: `packages/core/tests/test_backfill.py`

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_backfill.py`:

```python
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from saalr_core.marketdata.aggregates import BarRow
from saalr_core.marketdata.backfill import backfill_symbol, upsert_bars


class FakeResult:
    pass


class FakeSession:
    """Records execute() calls without touching a database."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    async def execute(self, stmt, params=None):
        self.calls.append((stmt, params))
        return FakeResult()


class FakeAgg:
    def __init__(self, rows: list[BarRow]) -> None:
        self._rows = rows
        self.args: tuple | None = None

    async def get_daily_bars(self, symbol, start, end, market="US"):
        self.args = (symbol, start, end, market)
        return self._rows


def _bar(d: str) -> BarRow:
    return BarRow(
        ts=datetime.fromisoformat(d).replace(tzinfo=timezone.utc),
        symbol="AAPL", market="US", interval="1d",
        open=1.0, high=2.0, low=0.5, close=1.5, volume=100,
    )


@pytest.mark.asyncio
async def test_upsert_bars_empty_is_noop():
    s = FakeSession()
    n = await upsert_bars(s, [])
    assert n == 0
    assert s.calls == []


@pytest.mark.asyncio
async def test_upsert_bars_executes_once_with_all_rows():
    s = FakeSession()
    n = await upsert_bars(s, [_bar("2026-01-02"), _bar("2026-01-03")])
    assert n == 2
    assert len(s.calls) == 1
    _stmt, params = s.calls[0]
    assert isinstance(params, list) and len(params) == 2
    assert params[0]["symbol"] == "AAPL" and params[0]["interval"] == "1d"


@pytest.mark.asyncio
async def test_backfill_symbol_fetches_then_upserts():
    s = FakeSession()
    agg = FakeAgg([_bar("2026-01-02")])
    n = await backfill_symbol(s, agg, "AAPL", "US", date(2026, 1, 1), date(2026, 1, 5))
    assert n == 1
    assert agg.args == ("AAPL", date(2026, 1, 1), date(2026, 1, 5), "US")
    assert len(s.calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest packages/core/tests/test_backfill.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.marketdata.backfill'`.

- [ ] **Step 3: Write the implementation**

Create `packages/core/saalr_core/marketdata/backfill.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .aggregates import BarRow

_UPSERT_BARS = text(
    """
    INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
    VALUES (:ts, :symbol, :market, :interval, :open, :high, :low, :close, :volume)
    ON CONFLICT (symbol, market, interval, ts) DO UPDATE SET
      open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
      close = EXCLUDED.close, volume = EXCLUDED.volume
    """
)


async def upsert_bars(session: AsyncSession, rows: list[BarRow]) -> int:
    """Idempotent upsert of daily bars into the shared `bars` table. Returns row count."""
    if not rows:
        return 0
    params = [
        {
            "ts": r.ts, "symbol": r.symbol, "market": r.market, "interval": r.interval,
            "open": Decimal(str(r.open)), "high": Decimal(str(r.high)),
            "low": Decimal(str(r.low)), "close": Decimal(str(r.close)), "volume": r.volume,
        }
        for r in rows
    ]
    await session.execute(_UPSERT_BARS, params)
    return len(rows)


async def backfill_symbol(
    session: AsyncSession, provider, symbol: str, market: str, start: date, end: date
) -> int:
    """Fetch daily bars for [start, end] from `provider` and upsert them. Returns row count."""
    rows = await provider.get_daily_bars(symbol, start, end, market)
    return await upsert_bars(session, rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest packages/core/tests/test_backfill.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/marketdata/backfill.py packages/core/tests/test_backfill.py
git commit -m "feat(core): shared bars backfill helper (upsert_bars + backfill_symbol)"
```

---

## Task 2: Cache-bypassing `capture_snapshot` + wire aggregates provider

**Files:**
- Modify: `apps/api/saalr_api/market/service.py`
- Modify: `apps/api/saalr_api/main.py:74` (lifespan provider wiring)
- Test: `packages/core/tests/test_capture_snapshot.py`

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_capture_snapshot.py`:

```python
from __future__ import annotations

import pytest

from saalr_api.market.service import MarketService
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind


class StubProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def get_option_chain(self, ticker, market):
        self.calls += 1
        return RawChain(
            underlying=ticker.upper(), market=market, as_of="2026-05-30T14:30:00+00:00",
            spot=185.0, div_yield=0.005,
            contracts=[
                RawContract("2026-09-19", 180.0, OptionKind.CALL, 9.0, 9.2, 9.1, 100, 500,
                            0.26, 0.58, 0.02, -0.05, 0.11),
            ],
        )


class StubRates:
    source_name = "fred"

    async def get_curve(self):
        return YieldCurve("2026-05-29", [(1 / 12, 0.05), (2.0, 0.045)])


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v


class FakeSession:
    def __init__(self) -> None:
        self.executes = 0

    async def execute(self, stmt, params=None):
        self.executes += 1
        return None


@pytest.mark.asyncio
async def test_capture_snapshot_ignores_primed_cache_and_persists():
    redis = FakeRedis()
    redis.store["mdq:chain:v1:US:AAPL"] = '{"stale": true}'  # primed cache must be ignored
    svc = MarketService(StubProvider(), StubRates(), redis, ttl=3600)
    session = FakeSession()

    payload = await svc.capture_snapshot(session, "AAPL", "US")

    assert payload["ticker"] == "AAPL"
    assert payload["spot"] == 185.0
    assert session.executes == 1                      # persist_chain ran
    assert "stale" not in redis.store["mdq:chain:v1:US:AAPL"]  # cache refreshed


@pytest.mark.asyncio
async def test_capture_snapshot_calls_provider_every_time():
    provider = StubProvider()
    svc = MarketService(provider, StubRates(), FakeRedis(), ttl=3600)
    session = FakeSession()
    await svc.capture_snapshot(session, "AAPL", "US")
    await svc.capture_snapshot(session, "AAPL", "US")
    assert provider.calls == 2                          # no cache short-circuit
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest packages/core/tests/test_capture_snapshot.py -q`
Expected: FAIL — `AttributeError: 'MarketService' object has no attribute 'capture_snapshot'`.

- [ ] **Step 3: Refactor `_computed_chain` and add `capture_snapshot`**

In `apps/api/saalr_api/market/service.py`, replace the `_computed_chain` method (currently lines 67-89) with the cache wrapper + an extracted builder + the new public method:

```python
    async def _computed_chain(self, session: AsyncSession, ticker: str, market: str) -> dict:
        key = f"mdq:chain:v1:{market}:{ticker.upper()}"  # bump v on payload-schema change
        cached = await self._redis.get(key)
        if cached:
            return json.loads(cached)
        return await self._build_and_persist(session, ticker, market, key)

    async def _build_and_persist(
        self, session: AsyncSession, ticker: str, market: str, key: str
    ) -> dict:
        chain = await self._provider.get_option_chain(ticker, market)
        curve = await self._rates.get_curve()
        as_of_date = datetime.fromisoformat(chain.as_of).date()
        contracts = _compute(chain, curve.rate_for, as_of_date)
        await persist_chain(session, ticker.upper(), market, chain.as_of, contracts)

        payload = {
            "ticker": ticker.upper(),
            "market": market,
            "as_of": chain.as_of,
            "spot": chain.spot,
            "risk_free_source": getattr(self._rates, "source_name", "fred"),
            "contracts": [_contract_json(c) for c in contracts],
            "computed_at_ms": _now_ms(),
        }
        await self._redis.set(key, json.dumps(payload), ex=self._ttl)
        return payload

    async def capture_snapshot(self, session: AsyncSession, ticker: str, market: str) -> dict:
        """Force a fresh provider fetch + persist a new timestamped snapshot, bypassing the
        read cache (but refreshing it). Used by the dev seed endpoint to accumulate ΔOI history."""
        key = f"mdq:chain:v1:{market}:{ticker.upper()}"
        return await self._build_and_persist(session, ticker, market, key)
```

- [ ] **Step 4: Run unit test to verify it passes**

Run: `uv run python -m pytest packages/core/tests/test_capture_snapshot.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Wire the aggregates provider in lifespan**

In `apps/api/saalr_api/main.py`, add the import near the other marketdata imports (after line 18 `from saalr_core.marketdata.massive import MassiveProvider`):

```python
from saalr_core.marketdata.aggregates import MassiveAggregatesProvider
```

Then in `lifespan`, immediately after line 74 (`app.state.market_provider = MassiveProvider(settings.massive_api_key)`), add:

```python
        app.state.aggregates_provider = MassiveAggregatesProvider(settings.massive_api_key)
```

- [ ] **Step 6: Verify existing market tests still pass**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest tests/integration/test_market.py -q`
Expected: PASS (existing chain cache/persist tests unaffected by the refactor).

- [ ] **Step 7: Commit**

```bash
git add apps/api/saalr_api/market/service.py apps/api/saalr_api/main.py packages/core/tests/test_capture_snapshot.py
git commit -m "feat(api): MarketService.capture_snapshot (cache-bypass) + wire aggregates provider"
```

---

## Task 3: Dev seed endpoints + dev gate + integration tests

**Files:**
- Create: `apps/api/saalr_api/dev/__init__.py` (empty)
- Create: `apps/api/saalr_api/dev/router.py`
- Modify: `apps/api/saalr_api/main.py` (import + `include_router`)
- Test: `tests/integration/test_dev_seed.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_dev_seed.py`:

```python
import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.marketdata.aggregates import BarRow
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind

from datetime import datetime, timedelta, timezone


class StubAgg:
    async def get_daily_bars(self, symbol, start, end, market="US"):
        return [
            BarRow(ts=datetime(2026, 1, 2, tzinfo=timezone.utc), symbol=symbol, market=market,
                   interval="1d", open=1, high=2, low=0.5, close=1.5, volume=10),
            BarRow(ts=datetime(2026, 1, 3, tzinfo=timezone.utc), symbol=symbol, market=market,
                   interval="1d", open=1, high=2, low=0.5, close=1.6, volume=11),
        ]


class StubChainProvider:
    """Returns a new as_of each call so distinct snapshot timestamps accumulate."""

    def __init__(self) -> None:
        self._n = 0

    async def get_option_chain(self, ticker, market):
        self._n += 1
        as_of = (datetime(2026, 5, 30, 14, 30, tzinfo=timezone.utc)
                 + timedelta(hours=self._n)).isoformat()
        return RawChain(
            underlying=ticker.upper(), market=market, as_of=as_of, spot=185.0, div_yield=0.005,
            contracts=[
                RawContract("2026-09-19", 180.0, OptionKind.CALL, 9.0, 9.2, 9.1, 100, 500,
                            0.26, 0.58, 0.02, -0.05, 0.11),
            ],
        )


class StubRates:
    source_name = "fred"

    async def get_curve(self):
        return YieldCurve("2026-05-29", [(1 / 12, 0.05), (2.0, 0.045)])


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_seed_endpoints_404_when_not_dev(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.settings.auth_provider = "clerk"   # simulate non-dev deployment
        async with _client(app) as c:
            rb = await c.post("/v1/dev/seed/bars", json={"ticker": "AAPL", "days": 30})
            rc = await c.post("/v1/dev/seed/chain", json={"ticker": "AAPL"})
    assert rb.status_code == 404
    assert rc.status_code == 404


async def test_seed_bars_backfills(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol='ZZZ'"))
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.aggregates_provider = StubAgg()
        async with _client(app) as c:
            r = await c.post("/v1/dev/seed/bars", json={"ticker": "ZZZ", "days": 30})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "ZZZ"
    assert body["rows_upserted"] == 2
    async with admin_engine.begin() as conn:
        n = (await conn.execute(
            text("SELECT count(*) FROM bars WHERE symbol='ZZZ'"))).scalar_one()
    assert n == 2


async def test_seed_chain_accumulates_snapshots(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM options_chain_snapshots WHERE underlying='ZZZ'"))
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubChainProvider()
        app.state.rate_provider = StubRates()
        await app.state.redis.delete("mdq:chain:v1:US:ZZZ")
        async with _client(app) as c:
            r1 = await c.post("/v1/dev/seed/chain", json={"ticker": "ZZZ"})
            r2 = await c.post("/v1/dev/seed/chain", json={"ticker": "ZZZ"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["total_snapshots"] == 2   # two distinct ts captured
    async with admin_engine.begin() as conn:
        n = (await conn.execute(text(
            "SELECT count(DISTINCT ts) FROM options_chain_snapshots WHERE underlying='ZZZ'"
        ))).scalar_one()
    assert n == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest tests/integration/test_dev_seed.py -q`
Expected: FAIL — the seed routes 404 in *all* cases (router not mounted yet), so `test_seed_bars_backfills` / `test_seed_chain_accumulates_snapshots` fail on `status_code == 200`.

- [ ] **Step 3: Create the dev router**

Create `apps/api/saalr_api/dev/__init__.py` (empty file).

Create `apps/api/saalr_api/dev/router.py`:

```python
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from saalr_core.marketdata.backfill import backfill_symbol
from saalr_core.marketdata.provider import ProviderError

from ..market.service import MarketService


def require_dev(request: Request) -> None:
    """Block all dev-seed routes unless the API is running in dev auth mode."""
    if request.app.state.settings.auth_provider != "dev":
        raise HTTPException(status_code=404, detail="not found")


router = APIRouter(prefix="/v1/dev", tags=["dev"], dependencies=[Depends(require_dev)])


class SeedBarsBody(BaseModel):
    ticker: str
    days: int = 400


class SeedChainBody(BaseModel):
    ticker: str


def _norm_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if not t or not t.isalpha():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": "unknown ticker"}},
        )
    return t


@router.post("/seed/bars")
async def seed_bars(body: SeedBarsBody, request: Request) -> dict:
    ticker = _norm_ticker(body.ticker)
    days = max(1, min(body.days, 3650))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    sm = request.app.state.sessionmaker
    try:
        async with sm() as session:
            async with session.begin():
                n = await backfill_symbol(
                    session, request.app.state.aggregates_provider, ticker, "US", start, today
                )
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "MARKET_DATA_PROVIDER_UNAVAILABLE", "message": str(exc)}},
        ) from exc
    return {"symbol": ticker, "rows_upserted": n, "first": start.isoformat(), "last": today.isoformat()}


@router.post("/seed/chain")
async def seed_chain(body: SeedChainBody, request: Request) -> dict:
    ticker = _norm_ticker(body.ticker)
    s = request.app.state
    svc = MarketService(s.market_provider, s.rate_provider, s.redis, s.vol_surface_ttl)
    sm = s.sessionmaker
    try:
        async with sm() as session:
            async with session.begin():
                payload = await svc.capture_snapshot(session, ticker, "US")
                total = (await session.execute(
                    text("SELECT count(DISTINCT ts) FROM options_chain_snapshots "
                         "WHERE underlying = :u AND market = :m"),
                    {"u": ticker, "m": "US"},
                )).scalar_one()
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "MARKET_DATA_PROVIDER_UNAVAILABLE", "message": str(exc)}},
        ) from exc
    return {
        "ticker": ticker,
        "as_of": payload["as_of"],
        "contracts": len(payload["contracts"]),
        "total_snapshots": total,
    }
```

- [ ] **Step 4: Mount the router**

In `apps/api/saalr_api/main.py`, add the import alongside the other router imports (after line 44 `from .account.router import router as account_router`):

```python
from .dev.router import router as dev_router
```

Then after line 112 (`app.include_router(account_router)`), add:

```python
    app.include_router(dev_router)
```

- [ ] **Step 5: Run integration tests to verify they pass**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest tests/integration/test_dev_seed.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add apps/api/saalr_api/dev/__init__.py apps/api/saalr_api/dev/router.py apps/api/saalr_api/main.py tests/integration/test_dev_seed.py
git commit -m "feat(api): dev-only /v1/dev/seed/{bars,chain} endpoints"
```

---

## Task 4: Frontend dev client + Seed panel + DEV-gated route/nav

**Files:**
- Create: `apps/web/src/lib/dev.ts`
- Create: `apps/web/src/pages/DevSeed.tsx`
- Test: `apps/web/src/pages/DevSeed.test.tsx`
- Modify: `apps/web/src/app/Router.tsx`, `apps/web/src/app/nav.ts`, `apps/web/src/components/Sidebar.tsx`

- [ ] **Step 1: Write the dev client**

Create `apps/web/src/lib/dev.ts`:

```typescript
import { BASE, authHeaders } from './api'

export interface SeedBarsResult {
  symbol: string
  rows_upserted: number
  first: string
  last: string
}

export interface SeedChainResult {
  ticker: string
  as_of: string
  contracts: number
  total_snapshots: number
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data?.detail?.error?.message ?? data?.detail?.error?.code ?? `request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export function seedBars(ticker: string, days: number): Promise<SeedBarsResult> {
  return post('/v1/dev/seed/bars', { ticker, days })
}

export function seedChain(ticker: string): Promise<SeedChainResult> {
  return post('/v1/dev/seed/chain', { ticker })
}
```

- [ ] **Step 2: Write the failing panel test**

Create `apps/web/src/pages/DevSeed.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { DevSeed } from './DevSeed'
import * as dev from '../lib/dev'

describe('DevSeed', () => {
  beforeEach(() => { vi.restoreAllMocks() })
  afterEach(() => { vi.useRealTimers() })

  it('backfills bars and logs the result', async () => {
    const spy = vi.spyOn(dev, 'seedBars').mockResolvedValue(
      { symbol: 'AAPL', rows_upserted: 250, first: '2025-01-01', last: '2026-01-01' })
    render(<DevSeed />)
    fireEvent.click(screen.getByTestId('seed-bars-btn'))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('AAPL', 400))
    await waitFor(() => expect(screen.getByTestId('seed-log').textContent).toContain('250'))
  })

  it('captures a snapshot and logs total_snapshots', async () => {
    const spy = vi.spyOn(dev, 'seedChain').mockResolvedValue(
      { ticker: 'AAPL', as_of: '2026-06-07T10:00:00+00:00', contracts: 12, total_snapshots: 3 })
    render(<DevSeed />)
    fireEvent.click(screen.getByTestId('seed-chain-btn'))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('AAPL'))
    await waitFor(() => expect(screen.getByTestId('seed-log').textContent).toContain('total_snapshots=3'))
  })

  it('repeat loop fires N times on the interval then auto-stops', async () => {
    vi.useFakeTimers()
    const spy = vi.spyOn(dev, 'seedChain').mockResolvedValue(
      { ticker: 'AAPL', as_of: 'x', contracts: 1, total_snapshots: 1 })
    render(<DevSeed />)
    // set 1 minute interval, 3 times
    fireEvent.change(screen.getByTestId('repeat-every-min'), { target: { value: '1' } })
    fireEvent.change(screen.getByTestId('repeat-times'), { target: { value: '3' } })
    fireEvent.click(screen.getByTestId('repeat-start'))
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000 * 3) })
    expect(spy).toHaveBeenCalledTimes(3)
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/web && npx vitest run src/pages/DevSeed.test.tsx`
Expected: FAIL — cannot resolve `./DevSeed`.

- [ ] **Step 4: Write the panel**

Create `apps/web/src/pages/DevSeed.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'
import { seedBars, seedChain } from '../lib/dev'

export function DevSeed() {
  const [ticker, setTicker] = useState('AAPL')
  const [days, setDays] = useState(400)
  const [log, setLog] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const [everyMin, setEveryMin] = useState(5)
  const [times, setTimes] = useState(12)
  const [running, setRunning] = useState(false)
  const doneRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function append(line: string) {
    setLog((l) => [`${new Date().toLocaleTimeString()}  ${line}`, ...l].slice(0, 200))
  }

  async function doBars() {
    setBusy(true)
    try {
      const r = await seedBars(ticker.trim().toUpperCase(), days)
      append(`bars ${r.symbol}: ${r.rows_upserted} rows (${r.first}…${r.last})`)
    } catch (e) {
      append(`bars error: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  async function doChain() {
    setBusy(true)
    try {
      const r = await seedChain(ticker.trim().toUpperCase())
      append(`chain ${r.ticker}: ${r.contracts} contracts · total_snapshots=${r.total_snapshots} @ ${r.as_of}`)
    } catch (e) {
      append(`chain error: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  function stopRepeat() {
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    setRunning(false)
  }

  function startRepeat() {
    stopRepeat()
    doneRef.current = 0
    setRunning(true)
    timerRef.current = setInterval(async () => {
      doneRef.current += 1
      await doChain()
      if (doneRef.current >= times) stopRepeat()
    }, Math.max(1, everyMin) * 60_000)
  }

  // clear any timer on unmount
  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current) }, [])

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Dev</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Seed market data (dev only)</h2>
        <p className="mt-1 text-xs text-txtFaint">
          Injects real Massive data: historical bars and cache-bypassing chain snapshots.
          Requires MASSIVE_API_KEY on the API.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-panel p-4">
        <label className="flex flex-col gap-1 text-[11px] text-txtDim">
          Ticker
          <input data-testid="seed-ticker" value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
            className="w-28 rounded border border-line bg-canvas px-2 py-1 font-mono text-sm text-txt" />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-txtDim">
          Days (bars)
          <input data-testid="seed-days" type="number" value={days}
            onChange={(e) => setDays(Number(e.target.value) || 0)}
            className="w-24 rounded border border-line bg-canvas px-2 py-1 font-mono text-sm text-txt" />
        </label>
        <button data-testid="seed-bars-btn" onClick={doBars} disabled={busy}
          className="rounded bg-accent/20 px-3 py-1.5 text-xs text-accent hover:bg-accent/30 disabled:opacity-40">
          Backfill bars
        </button>
        <button data-testid="seed-chain-btn" onClick={doChain} disabled={busy}
          className="rounded bg-accent/20 px-3 py-1.5 text-xs text-accent hover:bg-accent/30 disabled:opacity-40">
          Capture snapshot
        </button>
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-panel p-4">
        <span className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">Repeat capture</span>
        <label className="flex flex-col gap-1 text-[11px] text-txtDim">
          Every (min)
          <input data-testid="repeat-every-min" type="number" value={everyMin}
            onChange={(e) => setEveryMin(Number(e.target.value) || 1)}
            className="w-20 rounded border border-line bg-canvas px-2 py-1 font-mono text-sm text-txt" />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-txtDim">
          Times
          <input data-testid="repeat-times" type="number" value={times}
            onChange={(e) => setTimes(Number(e.target.value) || 1)}
            className="w-20 rounded border border-line bg-canvas px-2 py-1 font-mono text-sm text-txt" />
        </label>
        {running ? (
          <button data-testid="repeat-stop" onClick={stopRepeat}
            className="rounded bg-neg/20 px-3 py-1.5 text-xs text-neg hover:bg-neg/30">Stop</button>
        ) : (
          <button data-testid="repeat-start" onClick={startRepeat}
            className="rounded bg-accent/20 px-3 py-1.5 text-xs text-accent hover:bg-accent/30">Start</button>
        )}
      </div>

      <pre data-testid="seed-log"
        className="max-h-[40vh] overflow-auto rounded-lg border border-line bg-canvas p-3 font-mono text-[11px] text-txtDim">
        {log.join('\n') || 'No activity yet.'}
      </pre>
    </div>
  )
}
```

- [ ] **Step 5: Run the panel test to verify it passes**

Run: `cd apps/web && npx vitest run src/pages/DevSeed.test.tsx`
Expected: PASS (3 passed).

- [ ] **Step 6: Add the DEV-gated route**

In `apps/web/src/app/Router.tsx`, add the import after line 19 (`import { Start } from '../pages/Start'`):

```typescript
import { DevSeed } from '../pages/DevSeed'
```

Then immediately after the `settings` route (line 52, `<Route path="settings" element={<Settings />} />`), add:

```tsx
        {import.meta.env.DEV && <Route path="dev" element={<DevSeed />} />}
```

- [ ] **Step 7: Add the breadcrumb label**

In `apps/web/src/app/nav.ts`, add a `'/dev'` entry to the `EXTRA_LABELS` map:

```typescript
const EXTRA_LABELS: Record<string, string> = {
  '/billing/success': 'Success',
  '/billing/cancel': 'Cancelled',
  '/start': 'Get Started',
  '/dev': 'Dev Seed',
}
```

- [ ] **Step 8: Add the DEV-gated sidebar link**

In `apps/web/src/components/Sidebar.tsx`, add the link after the `SECTIONS.map(...)` block closes (immediately before the `<div className="mt-auto …">` footer). It reuses the same NavLink styling:

```tsx
      {import.meta.env.DEV && (
        <div>
          <div className="mx-2 mb-1 mt-5 font-mono text-[9px] uppercase tracking-[2px] text-txtFaint">Dev</div>
          <NavLink
            to="/dev"
            className={({ isActive }) =>
              `group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                isActive ? 'bg-panel text-txt' : 'text-txtDim hover:bg-panel/60 hover:text-txt'
              }`
            }
          >
            Dev Seed
          </NavLink>
        </div>
      )}
```

- [ ] **Step 9: Write the Sidebar DEV-gating test**

Create (or extend) `apps/web/src/components/Sidebar.test.tsx`:

```tsx
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Sidebar } from './Sidebar'

function renderSidebar() {
  return render(<MemoryRouter><Sidebar /></MemoryRouter>)
}

describe('Sidebar dev link', () => {
  afterEach(() => { vi.unstubAllEnvs() })

  it('shows the Dev Seed link in dev mode', () => {
    vi.stubEnv('DEV', true)
    renderSidebar()
    expect(screen.getByRole('link', { name: 'Dev Seed' })).toBeInTheDocument()
  })

  it('hides the Dev Seed link when not in dev mode', () => {
    vi.stubEnv('DEV', false)
    renderSidebar()
    expect(screen.queryByRole('link', { name: 'Dev Seed' })).toBeNull()
  })
})
```

- [ ] **Step 10: Run the frontend gate checks**

Run: `cd apps/web && npx vitest run src/components/Sidebar.test.tsx src/pages/DevSeed.test.tsx src/app/nav.test.ts`
Expected: PASS (all green).

- [ ] **Step 11: Typecheck + full web suite**

Run: `cd apps/web && npx tsc --noEmit && npx vitest run`
Expected: tsc clean (exit 0); all test files pass.

- [ ] **Step 12: Commit**

```bash
git add apps/web/src/lib/dev.ts apps/web/src/pages/DevSeed.tsx apps/web/src/pages/DevSeed.test.tsx apps/web/src/app/Router.tsx apps/web/src/app/nav.ts apps/web/src/components/Sidebar.tsx apps/web/src/components/Sidebar.test.tsx
git commit -m "feat(web): dev-only Seed panel (/app/dev) for market-data injection"
```

---

## Final verification

- [ ] **Backend suite (touched paths):**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest packages/core/tests/test_backfill.py packages/core/tests/test_capture_snapshot.py tests/integration/test_dev_seed.py tests/integration/test_market.py -q`
Expected: all PASS.

- [ ] **Manual smoke (optional, needs MASSIVE_API_KEY + dev stack up):** log in (founder), open `/app/dev`, set ticker `AAPL`, click **Backfill bars** (expect rows), **Capture snapshot** (expect `total_snapshots` increment), then start the repeat loop and watch the log grow.

- [ ] **Lint:** `ruff check apps/api/saalr_api/dev packages/core/saalr_core/marketdata/backfill.py`
Expected: no errors.
