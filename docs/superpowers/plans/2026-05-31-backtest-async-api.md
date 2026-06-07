# Backtest async API + queue (8b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the §5.3 async backtest API — `POST /v1/strategies/{id}/backtest` → 202 queued, a Redis-Streams worker consume loop that runs the 8a `run_backtest`, and `GET /v1/backtests/{id}` polling — open to all tiers.

**Architecture:** A shared Redis-Streams queue module in `saalr-core` (producer = API, consumer = worker). The Backtest-row CRUD moves into `saalr-core` so the API and worker share it. The API creates the row in a committed transaction, then enqueues; the worker consumes, calls the existing `run_backtest`, and acks; crash-safety via consumer-group reclaim.

**Tech Stack:** Python 3.12, FastAPI, redis.asyncio (Redis Streams), SQLAlchemy 2.0 async, pydantic, uv workspace, pytest (`pytest-asyncio`), ruff.

**Spec:** `docs/superpowers/specs/2026-05-31-backtest-async-api-design.md`

**Conventions / facts (verified against the codebase):**
- `from __future__ import annotations` at the top of every module.
- Redis is already wired: `app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)`; `settings.redis_url` default `redis://localhost:6379/0`; the test env honours `REDIS_URL`. `decode_responses=True` means stream reads return `str`, not `bytes`.
- `get_principal` dependency yields `(session, principal)` with `app.current_tenant` set; its `session` is inside `async with session.begin()` and commits **after** the handler returns. `Principal` has `.tenant_id`, `.user_id`, `.email`, `.tier`.
- `tenant_session(sessionmaker, tenant_id)` opens ONE committed transaction with the RLS GUC set. `app.state.sessionmaker` exists.
- 8a row-CRUD currently in `apps/backtest-worker/backtest_worker/repo.py`: `get_backtest`, `create_backtest(session, tenant_id, strategy_id, start, end, config_snapshot) -> UUID`, `mark_running`, `save_result`, plus `get_strategy` and `load_underlying_closes`. `Backtest` model fields: backtest_id, tenant_id, strategy_id, start_date, end_date, status, metrics_json(JSONB), trade_log_uri, config_snapshot(JSONB), error_message, started_at, completed_at, created_at.
- `run_backtest(sessionmaker, tenant_id, backtest_id) -> {"status": "...", ...}` (8a, in `backtest_worker/service.py`) — three-phase, persists succeeded/failed, never re-raises in-pipeline errors. `ENGINE_VERSION` is in `saalr_core.backtest.engine`.
- API strategies repo: `saalr_api.strategies.repo.get_strategy(session, strategy_id)`.
- Worker packages are importable only under `uv run --package saalr-backtest-worker pytest …`. Integration DB = Docker Postgres on host **55432**; export before pytest:
  ```bash
  export ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr"
  export APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr"
  ```
  Redis must be running on `localhost:6379` (compose `redis:7-alpine`).

---

## Task 1: Move Backtest-row CRUD into `saalr-core` (shared, behaviour-neutral)

The API and worker both need the row CRUD. Move it to core; the worker re-exports so 8a code/tests are untouched.

**Files:**
- Create: `packages/core/saalr_core/backtest/repo.py`
- Modify: `apps/backtest-worker/backtest_worker/repo.py` (remove the 4 row functions; re-export from core; keep `get_strategy` + `load_underlying_closes`)

- [ ] **Step 1: Create the core repo**

```python
# packages/core/saalr_core/backtest/repo.py
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.trading import Backtest


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_backtest(session: AsyncSession, backtest_id: UUID) -> Backtest | None:
    return (
        await session.execute(select(Backtest).where(Backtest.backtest_id == backtest_id))
    ).scalar_one_or_none()


async def create_backtest(
    session: AsyncSession,
    tenant_id: UUID,
    strategy_id: UUID,
    start: date,
    end: date,
    config_snapshot: dict,
) -> UUID:
    row = Backtest(
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        start_date=start,
        end_date=end,
        status="queued",
        config_snapshot=config_snapshot,
    )
    session.add(row)
    await session.flush()
    return row.backtest_id


async def mark_running(session: AsyncSession, backtest_id: UUID) -> None:
    bt = await get_backtest(session, backtest_id)
    bt.status = "running"
    bt.started_at = _utcnow()


async def save_result(
    session: AsyncSession,
    backtest_id: UUID,
    metrics_json: dict | None,
    status: str,
    error: str | None = None,
) -> None:
    bt = await get_backtest(session, backtest_id)
    bt.status = status
    bt.metrics_json = metrics_json
    bt.error_message = error
    bt.completed_at = _utcnow()
```

- [ ] **Step 2: Rewrite the worker repo to re-export the row CRUD**

Replace the entire contents of `apps/backtest-worker/backtest_worker/repo.py` with:

```python
# apps/backtest-worker/backtest_worker/repo.py
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.backtest.repo import (  # noqa: F401 - re-exported for the worker's service/CLI
    create_backtest,
    get_backtest,
    mark_running,
    save_result,
)
from saalr_core.db.models.trading import Strategy


async def get_strategy(session: AsyncSession, strategy_id: UUID) -> Strategy | None:
    return (
        await session.execute(select(Strategy).where(Strategy.strategy_id == strategy_id))
    ).scalar_one_or_none()


async def load_underlying_closes(
    session: AsyncSession, symbol: str, market: str, start: date, end: date, lookback: int
) -> dict[date, float]:
    """Daily closes in [start - warmup, end]. Warmup pads back enough calendar days to
    fill the realized-vol lookback window. `bars` is non-RLS (shared market data)."""
    pad_start = start - timedelta(days=int(lookback * 1.6) + 7)
    rows = (
        await session.execute(
            text(
                """
                SELECT ts, close FROM bars
                WHERE symbol = :sym AND market = :mkt AND interval = '1d'
                  AND ts::date >= :s AND ts::date <= :e
                ORDER BY ts
                """
            ),
            {"sym": symbol, "mkt": market, "s": pad_start, "e": end},
        )
    ).all()
    return {r.ts.date(): float(r.close) for r in rows}
```

- [ ] **Step 3: Verify 8a tests stay green (no behaviour change)**

Run:
```bash
uv run pytest packages/core/tests -q
uv run --package saalr-backtest-worker pytest tests/integration/test_backtest.py apps/backtest-worker/tests -q
```
Expected: core all pass; backtest integration 2 + cli 2 pass. Then `uvx ruff check packages/core/saalr_core/backtest/repo.py apps/backtest-worker/backtest_worker/repo.py` → clean.

- [ ] **Step 4: Commit**

```bash
git add packages/core/saalr_core/backtest/repo.py apps/backtest-worker/backtest_worker/repo.py
git commit -m "refactor(backtest): move Backtest-row CRUD into saalr_core (shared by API + worker)"
```

---

## Task 2: Redis-Streams queue module + integration test

**Files:**
- Modify: `packages/core/pyproject.toml` (add `redis>=5`)
- Create: `packages/core/saalr_core/queue/__init__.py` (empty)
- Create: `packages/core/saalr_core/queue/backtest_queue.py`
- Test: `tests/integration/test_backtest_queue.py`

- [ ] **Step 1: Add the redis dependency to saalr-core**

In `packages/core/pyproject.toml`, add `"redis>=5"` to the `dependencies` list (keep the existing entries). Then run `uv sync` to update the lock.

- [ ] **Step 2: Write the failing test**

```python
# tests/integration/test_backtest_queue.py
import os

import pytest_asyncio
import redis.asyncio as aioredis

from saalr_core.ids import new_id
from saalr_core.queue import backtest_queue as q

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest_asyncio.fixture
async def redis():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield r
    await r.aclose()


async def test_ensure_group_idempotent(redis):
    stream = f"test:bt:{new_id()}"
    try:
        await q.ensure_group(redis, stream=stream, group="g")
        await q.ensure_group(redis, stream=stream, group="g")  # must not raise (BUSYGROUP swallowed)
    finally:
        await redis.delete(stream)


async def test_enqueue_consume_ack_roundtrip(redis):
    stream = f"test:bt:{new_id()}"
    try:
        await q.ensure_group(redis, stream=stream, group="g")
        tid, bid = new_id(), new_id()
        await q.enqueue(redis, tid, bid, stream=stream)
        jobs = await q.consume_batch(redis, "c1", block_ms=200, count=10, stream=stream, group="g")
        assert len(jobs) == 1
        assert jobs[0].tenant_id == tid and jobs[0].backtest_id == bid
        assert (await redis.xpending(stream, "g"))["pending"] == 1
        await q.ack(redis, jobs[0].msg_id, stream=stream, group="g")
        assert (await redis.xpending(stream, "g"))["pending"] == 0
    finally:
        await redis.delete(stream)


async def test_consume_batch_empty_on_timeout(redis):
    stream = f"test:bt:{new_id()}"
    try:
        await q.ensure_group(redis, stream=stream, group="g")
        assert await q.consume_batch(redis, "c1", block_ms=50, count=10, stream=stream, group="g") == []
    finally:
        await redis.delete(stream)


async def test_claim_stale_reclaims_unacked(redis):
    stream = f"test:bt:{new_id()}"
    try:
        await q.ensure_group(redis, stream=stream, group="g")
        tid, bid = new_id(), new_id()
        await q.enqueue(redis, tid, bid, stream=stream)
        await q.consume_batch(redis, "c1", block_ms=200, count=10, stream=stream, group="g")  # c1 never acks
        claimed = await q.claim_stale(redis, "c2", min_idle_ms=0, count=10, stream=stream, group="g")
        assert len(claimed) == 1 and claimed[0].backtest_id == bid
    finally:
        await redis.delete(stream)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_backtest_queue.py -v` (Redis on 6379)
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.queue'`

- [ ] **Step 4: Write the queue module**

```python
# packages/core/saalr_core/queue/backtest_queue.py
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from redis.exceptions import ResponseError

STREAM = "saalr:bt:jobs:v1"
GROUP = "bt-workers"
_MAXLEN = 10_000


@dataclass(frozen=True)
class Job:
    msg_id: str
    tenant_id: UUID
    backtest_id: UUID


def _parse(entries) -> list[Job]:
    jobs: list[Job] = []
    for msg_id, fields in entries:
        if not fields:  # an entry deleted between pending and claim
            continue
        jobs.append(
            Job(
                msg_id=msg_id,
                tenant_id=UUID(fields["tenant_id"]),
                backtest_id=UUID(fields["backtest_id"]),
            )
        )
    return jobs


async def ensure_group(redis, stream: str = STREAM, group: str = GROUP) -> None:
    try:
        await redis.xgroup_create(stream, group, id="$", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def enqueue(redis, tenant_id: UUID, backtest_id: UUID, stream: str = STREAM) -> str:
    return await redis.xadd(
        stream,
        {"tenant_id": str(tenant_id), "backtest_id": str(backtest_id)},
        maxlen=_MAXLEN,
        approximate=True,
    )


async def consume_batch(
    redis, consumer: str, block_ms: int, count: int, stream: str = STREAM, group: str = GROUP
) -> list[Job]:
    resp = await redis.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
    if not resp:
        return []
    _stream_name, entries = resp[0]
    return _parse(entries)


async def ack(redis, msg_id: str, stream: str = STREAM, group: str = GROUP) -> None:
    await redis.xack(stream, group, msg_id)
    await redis.xdel(stream, msg_id)


async def claim_stale(
    redis, consumer: str, min_idle_ms: int, count: int, stream: str = STREAM, group: str = GROUP
) -> list[Job]:
    result = await redis.xautoclaim(
        stream, group, consumer, min_idle_ms, start_id="0-0", count=count
    )
    # redis-py returns [next_cursor, claimed_entries, deleted_ids]; older builds omit the 3rd.
    entries = result[1] if len(result) > 1 else []
    return _parse(entries)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_backtest_queue.py -v`
Expected: PASS (all 4). If `xpending` returns a different shape, confirm redis-py ≥5 returns a dict with key `"pending"` under `decode_responses=True` (it does).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/queue tests/integration/test_backtest_queue.py
git add packages/core/pyproject.toml uv.lock packages/core/saalr_core/queue tests/integration/test_backtest_queue.py
git commit -m "feat(backtest): Redis-Streams queue module (enqueue/consume/ack/claim)"
```

---

## Task 3: API request schema + duration heuristic (pure, unit-tested)

**Files:**
- Create: `apps/api/saalr_api/backtests/__init__.py` (empty)
- Create: `apps/api/saalr_api/backtests/schemas.py`
- Test: `tests/integration/test_backtest_schemas.py` (pure, but lives with API tests)

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_backtest_schemas.py
from datetime import date

import pytest
from pydantic import ValidationError

from saalr_api.backtests.schemas import BacktestRequest, estimated_duration_seconds


def test_request_parses_dates_and_defaults():
    r = BacktestRequest(start_date="2025-01-01", end_date="2025-06-30")
    assert r.start_date == date(2025, 1, 1) and r.end_date == date(2025, 6, 30)
    assert r.initial_capital == 100_000.0 and r.include_costs is True


def test_request_rejects_end_before_start():
    with pytest.raises(ValidationError):
        BacktestRequest(start_date="2025-06-30", end_date="2025-01-01")
    with pytest.raises(ValidationError):
        BacktestRequest(start_date="2025-01-01", end_date="2025-01-01")  # equal not allowed


def test_estimated_duration_bounds():
    assert estimated_duration_seconds(date(2025, 1, 1), date(2025, 1, 2)) == 5  # floor
    assert estimated_duration_seconds(date(2020, 1, 1), date(2025, 1, 1)) == 120  # cap
    mid = estimated_duration_seconds(date(2025, 1, 1), date(2025, 7, 1))  # ~181 days // 7 = 25
    assert mid == 25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_backtest_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_api.backtests'`

- [ ] **Step 3: Write the schema module**

```python
# apps/api/saalr_api/backtests/schemas.py
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, model_validator


class BacktestRequest(BaseModel):
    start_date: date
    end_date: date
    initial_capital: float = 100_000.0
    include_costs: bool = True

    @model_validator(mode="after")
    def _end_after_start(self) -> "BacktestRequest":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


def estimated_duration_seconds(start: date, end: date) -> int:
    """A rough hint for clients; not a guarantee."""
    days = (end - start).days
    return min(120, max(5, days // 7))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_backtest_schemas.py -v`
Expected: PASS (all 3)

- [ ] **Step 5: Commit**

```bash
git add apps/api/saalr_api/backtests/__init__.py apps/api/saalr_api/backtests/schemas.py tests/integration/test_backtest_schemas.py
git commit -m "feat(backtest-api): request schema + duration heuristic"
```

---

## Task 4: API router (POST 202 + GET poll) + register + ensure_group at startup

**Files:**
- Create: `apps/api/saalr_api/backtests/router.py`
- Modify: `apps/api/saalr_api/main.py` (ensure_group at startup; include the router)
- Test: `tests/integration/test_backtest_api.py` (POST/GET/idempotency/RLS/validation — no worker yet)

- [ ] **Step 1: Write the router**

```python
# apps/api/saalr_api/backtests/router.py
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.backtest import repo as bt_repo
from saalr_core.backtest.engine import ENGINE_VERSION
from saalr_core.db.session import tenant_session
from saalr_core.queue.backtest_queue import enqueue

from ..auth import Principal, get_principal
from ..strategies import repo as strat_repo
from .schemas import BacktestRequest, estimated_duration_seconds

router = APIRouter(tags=["backtests"])


def _idem_key(tenant_id, key: str) -> str:
    return f"saalr:idem:bt:{tenant_id}:{key}"


def _accepted(backtest_id, start, end, status: str) -> dict:
    return {
        "backtest_id": str(backtest_id),
        "status": status,
        "estimated_duration_seconds": estimated_duration_seconds(start, end),
        "poll_url": f"/v1/backtests/{backtest_id}",
    }


@router.post("/v1/strategies/{strategy_id}/backtest", status_code=202)
async def create_backtest_run(
    strategy_id: UUID,
    body: BacktestRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> dict:
    session, principal = ctx
    redis = request.app.state.redis
    sm = request.app.state.sessionmaker

    strat = await strat_repo.get_strategy(session, strategy_id)
    if strat is None:
        raise HTTPException(
            404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "strategy not found"}}
        )

    if idempotency_key:
        existing = await redis.get(_idem_key(principal.tenant_id, idempotency_key))
        if existing:
            row = await bt_repo.get_backtest(session, UUID(existing))
            if row is not None:
                return _accepted(row.backtest_id, row.start_date, row.end_date, row.status)

    params = {
        "start": body.start_date.isoformat(),
        "end": body.end_date.isoformat(),
        "initial_capital": body.initial_capital,
        "include_costs": body.include_costs,
    }
    snapshot = {"config": strat.config_json, "params": params, "engine_version": ENGINE_VERSION}

    # Commit the row in its OWN transaction BEFORE enqueuing, so the worker cannot
    # read it before it exists. (get_principal's session commits only after this
    # handler returns.)
    async with tenant_session(sm, principal.tenant_id) as create_session:
        backtest_id = await bt_repo.create_backtest(
            create_session, principal.tenant_id, strategy_id, body.start_date, body.end_date, snapshot
        )

    try:
        await enqueue(redis, principal.tenant_id, backtest_id)
    except Exception as exc:  # noqa: BLE001 - row stays 'queued', reclaimable; surface 503
        raise HTTPException(
            503, {"error": {"code": "BACKTEST_ENQUEUE_FAILED", "message": "could not enqueue job"}}
        ) from exc

    if idempotency_key:
        await redis.set(_idem_key(principal.tenant_id, idempotency_key), str(backtest_id), nx=True, ex=86400)

    return _accepted(backtest_id, body.start_date, body.end_date, "queued")


@router.get("/v1/backtests/{backtest_id}")
async def get_backtest_run(
    backtest_id: UUID,
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> dict:
    session, _ = ctx
    row = await bt_repo.get_backtest(session, backtest_id)
    if row is None:
        raise HTTPException(
            404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "backtest not found"}}
        )
    out: dict = {"backtest_id": str(row.backtest_id), "status": row.status}
    if row.status == "succeeded":
        out["metrics"] = (row.metrics_json or {}).get("metrics", {})
        out["trade_log_url"] = None
    elif row.status == "failed":
        out["error"] = {"code": "BACKTEST_FAILED", "message": row.error_message}
    return out
```

- [ ] **Step 2: Register the router + ensure_group at startup**

In `apps/api/saalr_api/main.py`:
- Add import near the other core imports: `from saalr_core.queue.backtest_queue import ensure_group`
- Add the router import near the others: `from .backtests.router import router as backtests_router`
- In the lifespan, right after `app.state.redis = aioredis.from_url(...)`, add: `await ensure_group(app.state.redis)`
- After `app.include_router(strategies_router)`, add: `app.include_router(backtests_router)`

- [ ] **Step 3: Write the failing API integration test**

```python
# tests/integration/test_backtest_api.py
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text

from saalr_api.main import create_app

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, start, prices):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol = :s"), {"s": symbol})
        for i, px in enumerate(prices):
            ts = start + timedelta(days=i)
            await conn.execute(
                text(
                    """INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                       VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""
                ),
                {"ts": ts, "sym": symbol, "o": Decimal(str(px)), "h": Decimal(str(px + 1)),
                 "l": Decimal(str(px - 1)), "c": Decimal(str(px)), "v": 1000},
            )


_OPTION = {"kind": "option", "option_type": "CALL", "side": "BUY", "strike": 100,
           "expiry": "2025-03-01", "qty": 1, "entry_price": None}


async def _make_strategy(c, headers, underlying="AAPL"):
    body = {"name": "BT", "config": {"underlying": underlying, "legs": [_OPTION]}, "market": "US"}
    r = await c.post("/v1/strategies", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["strategy_id"]


async def test_post_returns_202_then_get_is_queued(app_sessionmaker, admin_engine):
    # clean the shared stream + create the app (lifespan ensure_group on a clean stream)
    r0 = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r0.delete("saalr:bt:jobs:v1")
    await r0.aclose()
    await _seed_bars(admin_engine, "AAPL", datetime(2025, 1, 1, tzinfo=timezone.utc),
                     [100.0 + i * 0.3 for i in range(80)])

    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-api@x.com"}
            sid = await _make_strategy(c, h)
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-02-01", "end_date": "2025-03-10"}, headers=h)
            assert r.status_code == 202, r.text
            body = r.json()
            assert body["status"] == "queued"
            assert body["poll_url"] == f"/v1/backtests/{body['backtest_id']}"
            assert body["estimated_duration_seconds"] >= 5

            poll = await c.get(body["poll_url"], headers=h)
            assert poll.status_code == 200 and poll.json()["status"] == "queued"


async def test_idempotency_key_returns_same_backtest(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-idem@x.com"}
            sid = await _make_strategy(c, h)
            req = {"start_date": "2025-02-01", "end_date": "2025-03-10"}
            hk = {**h, "Idempotency-Key": "fixed-key-123"}
            r1 = await c.post(f"/v1/strategies/{sid}/backtest", json=req, headers=hk)
            r2 = await c.post(f"/v1/strategies/{sid}/backtest", json=req, headers=hk)
            assert r1.status_code == 202 and r2.status_code == 202
            assert r1.json()["backtest_id"] == r2.json()["backtest_id"]


async def test_validation_end_before_start_is_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-val@x.com"}
            sid = await _make_strategy(c, h)
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-03-10", "end_date": "2025-02-01"}, headers=h)
            assert r.status_code == 422


async def test_get_other_tenant_backtest_is_404(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            ha = {"Authorization": "Bearer dev:bt-a@x.com"}
            hb = {"Authorization": "Bearer dev:bt-b@x.com"}
            sid = await _make_strategy(c, ha)
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-02-01", "end_date": "2025-03-10"}, headers=ha)
            bt_id = r.json()["backtest_id"]
            # tenant B must not see tenant A's backtest
            other = await c.get(f"/v1/backtests/{bt_id}", headers=hb)
            assert other.status_code == 404
```

- [ ] **Step 4: Run test to verify it passes**

Run (Redis up + 55432 env exported):
```bash
uv run --package saalr-backtest-worker pytest tests/integration/test_backtest_api.py -v
```
> `--package saalr-backtest-worker` is used so the whole `tests/integration` tree can co-run later; this file itself only needs `saalr_api`, but using the flag consistently avoids import gaps when the suite runs together.
Expected: PASS (4). The `_make_strategy` POST auto-provisions the tenant via dev auth.

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/backtests apps/api/saalr_api/main.py tests/integration/test_backtest_api.py
git add apps/api/saalr_api/backtests/router.py apps/api/saalr_api/main.py tests/integration/test_backtest_api.py
git commit -m "feat(backtest-api): POST 202 enqueue + GET poll, idempotency, RLS"
```

---

## Task 5: Worker consumer + `consume` CLI + end-to-end test

**Files:**
- Create: `apps/backtest-worker/backtest_worker/consumer.py`
- Modify: `apps/backtest-worker/backtest_worker/cli.py` (add `consume`)
- Test: append to `tests/integration/test_backtest_api.py` (end-to-end succeeded + failed) and `apps/backtest-worker/tests/test_cli_parser.py` (consume parser)

- [ ] **Step 1: Write the consumer**

```python
# apps/backtest-worker/backtest_worker/consumer.py
from __future__ import annotations

import logging

from saalr_core.queue.backtest_queue import Job, ack, claim_stale, consume_batch, ensure_group

from .service import run_backtest

log = logging.getLogger("saalr.backtest.consumer")


async def _process(redis, sessionmaker, job: Job) -> None:
    try:
        await run_backtest(sessionmaker, job.tenant_id, job.backtest_id)
    except Exception:  # noqa: BLE001 - poison guard: run_backtest persists in-pipeline failures itself
        log.exception("backtest job %s failed unexpectedly", job.backtest_id)
    finally:
        await ack(redis, job.msg_id)


async def run_consumer(
    redis,
    sessionmaker,
    consumer: str,
    block_ms: int = 5000,
    count: int = 10,
    once: bool = False,
    claim_min_idle_ms: int = 60_000,
) -> None:
    await ensure_group(redis)
    # reclaim + reprocess jobs left pending by a crashed worker
    for job in await claim_stale(redis, consumer, claim_min_idle_ms, count):
        await _process(redis, sessionmaker, job)
    while True:
        for job in await consume_batch(redis, consumer, block_ms, count):
            await _process(redis, sessionmaker, job)
        if once:
            return
```

- [ ] **Step 2: Add the `consume` CLI subcommand**

In `apps/backtest-worker/backtest_worker/cli.py`:
- Add imports at the top: `import socket` and `import redis.asyncio as aioredis`, and `from .consumer import run_consumer`.
- In `build_parser`, add:
```python
    cn = sub.add_parser("consume", help="run the Redis-Streams backtest consume loop")
    cn.add_argument("--block-ms", type=int, default=5000, dest="block_ms")
    cn.add_argument("--count", type=int, default=10)
    cn.add_argument("--once", action="store_true")
    cn.add_argument("--consumer", default=None)
```
- Add the handler:
```python
async def _cmd_consume(args) -> None:
    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    consumer = args.consumer or f"bt-{socket.gethostname()}"
    try:
        await run_consumer(
            redis, create_sessionmaker(engine), consumer,
            block_ms=args.block_ms, count=args.count, once=args.once,
        )
    finally:
        await redis.aclose()
        await engine.dispose()
```
- Register it in `_DISPATCH`: `"consume": _cmd_consume`.
- Note: the existing `_cmd_backtest`/`_cmd_run` use `_with_sessionmaker`; `_cmd_consume` manages its own engine+redis because it also needs the redis client. Keep `main()` unchanged (`asyncio.run(_DISPATCH[args.cmd](args))`) — it already dispatches on `args` only.

> The existing `_DISPATCH` handlers are called as `handler(args)`. Confirm `main()` passes `args` (it does). If `_cmd_backtest`/`_cmd_run` take `(args)` already, `_cmd_consume(args)` matches.

- [ ] **Step 3: Add the consume parser test**

Append to `apps/backtest-worker/tests/test_cli_parser.py`:

```python
def test_consume_subcommand_parses():
    from backtest_worker.cli import build_parser

    args = build_parser().parse_args(["consume", "--once", "--block-ms", "100", "--consumer", "c1"])
    assert args.cmd == "consume"
    assert args.once is True and args.block_ms == 100 and args.consumer == "c1"
```

- [ ] **Step 4: Append the end-to-end tests**

Append to `tests/integration/test_backtest_api.py` (the `_seed_bars`, `_client`, `_make_strategy`, `REDIS_URL` helpers are already in the file):

```python
from saalr_core.db.session import create_engine, create_sessionmaker  # add to imports at top
from backtest_worker.consumer import run_consumer  # add to imports at top


async def _run_worker_once():
    settings_url = os.environ["APP_DATABASE_URL"]
    engine = create_engine(settings_url)
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await run_consumer(redis, create_sessionmaker(engine), "test-consumer",
                           block_ms=1000, count=10, once=True)
    finally:
        await redis.aclose()
        await engine.dispose()


async def test_end_to_end_post_consume_poll_succeeds(app_sessionmaker, admin_engine):
    r0 = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r0.delete("saalr:bt:jobs:v1")
    await r0.aclose()
    await _seed_bars(admin_engine, "AAPL", datetime(2025, 1, 1, tzinfo=timezone.utc),
                     [100.0 + i * 0.3 for i in range(80)])

    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-e2e@x.com"}
            sid = await _make_strategy(c, h)
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-02-01", "end_date": "2025-03-10",
                                   "include_costs": False}, headers=h)
            poll_url = r.json()["poll_url"]

            await _run_worker_once()

            done = await c.get(poll_url, headers=h)
            assert done.status_code == 200
            data = done.json()
            assert data["status"] == "succeeded", data
            assert "sharpe" in data["metrics"]
            assert data["trade_log_url"] is None


async def test_end_to_end_failed_when_no_bars(app_sessionmaker, admin_engine):
    r0 = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r0.delete("saalr:bt:jobs:v1")
    await r0.aclose()

    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-e2e-fail@x.com"}
            sid = await _make_strategy(c, h, underlying="ZZZZ")  # no bars
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-02-01", "end_date": "2025-03-10"}, headers=h)
            poll_url = r.json()["poll_url"]

            await _run_worker_once()

            done = await c.get(poll_url, headers=h)
            assert done.json()["status"] == "failed"
            assert done.json()["error"]["code"] == "BACKTEST_FAILED"
```

- [ ] **Step 5: Run tests to verify they pass**

Run (Redis up + 55432 env exported):
```bash
uv run --package saalr-backtest-worker pytest tests/integration/test_backtest_api.py apps/backtest-worker/tests/test_cli_parser.py -v
```
Expected: PASS — 6 API tests (4 from Task 4 + 2 e2e) + 3 CLI parser tests. If the e2e `succeeded` assertion fails because the worker read no job, confirm the stream was deleted BEFORE `create_app()` (so the lifespan `ensure_group` runs on a clean stream and the group exists before the POST enqueues).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check apps/backtest-worker/backtest_worker/consumer.py apps/backtest-worker/backtest_worker/cli.py
git add apps/backtest-worker/backtest_worker/consumer.py apps/backtest-worker/backtest_worker/cli.py apps/backtest-worker/tests/test_cli_parser.py tests/integration/test_backtest_api.py
git commit -m "feat(backtest-worker): Redis-Streams consume loop + consume CLI + end-to-end tests"
```

---

## Task 6: Full gate

**Files:** none (verification only). Redis up + 55432 env exported.

- [ ] **Step 1: Core suite**

Run: `uv run pytest packages/core/tests -q`
Expected: green.

- [ ] **Step 2: Full integration suite (both worker packages can't co-install — split as in 8a)**

Run:
```bash
uv run --package saalr-backtest-worker pytest tests/integration --ignore=tests/integration/test_ingest.py -q
uv run --package saalr-ingest-worker pytest tests/integration/test_ingest.py -q
```
Expected: first run covers backtest queue/api/e2e + 8a backtest + api/market/strategies/etc.; second covers ingest. All green (live-only tests skip). If the first run errors importing `ingest_worker` from some other integration file, also `--ignore` that file and run it under the ingest package — report which split you used.

- [ ] **Step 3: Worker CLI smoke + lint**

Run:
```bash
uv run --package saalr-backtest-worker python -m backtest_worker --help   # lists backtest/run/consume
uvx ruff check packages/core/saalr_core/queue packages/core/saalr_core/backtest apps/api/saalr_api/backtests apps/backtest-worker
```
Expected: help shows three subcommands; ruff clean.

- [ ] **Step 4: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "chore(backtest): 8b suite + lint green"
```

---

## Self-review notes (addressed)

- **Spec coverage:** queue module (T2), row-CRUD share (T1), POST 202 + idempotency + commit-before-enqueue (T4), GET poll mapping incl. `trade_log_url:null` + failed error (T4/T5), worker consume loop + claim-stale crash-safety (T5), `consume` CLI (T5), schema + duration (T3), `ensure_group` at API startup (T4), no tier gate (POST has no entitlement check). All §5.3 response fields present.
- **Ordering traps captured:** (a) `ensure_group` runs at API startup so the group exists before the first enqueue; the e2e tests delete the stream BEFORE `create_app()` so the lifespan re-creates the group cleanly. (b) the row is created in a separate committed `tenant_session` BEFORE `enqueue`, so the worker never reads an uncommitted row.
- **At-least-once safety:** `run_backtest` is deterministic and overwrites the row, so redelivery (claim-stale) is harmless; `_process` always acks (poison guard) and relies on `run_backtest` persisting in-pipeline failures.
- **Type consistency:** `Job(msg_id, tenant_id: UUID, backtest_id: UUID)`; `enqueue` stringifies UUIDs, `_parse` rebuilds them; `decode_responses=True` so fields are `str`. `create_backtest` signature matches 8a. Worker `repo.py` re-exports the moved functions so `service.py` (`repo.create_backtest`, `repo.get_backtest`, `repo.mark_running`, `repo.save_result`) keeps working unchanged.
- **No new gate on backtest:** confirmed the POST handler performs no `entitlements_for` check.
