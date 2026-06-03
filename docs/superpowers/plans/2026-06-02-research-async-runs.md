# RA-2 — Async research runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert research-note generation from synchronous to asynchronous — `POST /research/run` enqueues a job (202) and a dedicated research-agent worker generates the note; clients poll `GET /research/notes/{id}` — with a Premium gate, a 10/UTC-day per-tenant rate limit, a 6h cache fast-path, and in-flight dedup.

**Architecture:** Reuse the backtest-async (slice 8b) machinery: Redis Streams + consumer group + claim-stale crash recovery + 3-phase load/compute/persist. The `research_notes` table gains a `status` lifecycle (migration 0009). Generation moves out of `apps/api` into the `apps/research-agent` worker; shared row-CRUD + the closes loader move to `saalr-core` so the worker never imports `apps/api`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Postgres, Redis (redis-py asyncio), pytest. `openai` is an optional extra (only the worker env installs it).

**Spec:** `docs/superpowers/specs/2026-06-02-research-async-runs-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- DB tests need Postgres on **55432** and Redis on **6379**. Prefix DB/Redis test commands:
  `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <args>`
- Error shape: `HTTPException(status, {"error": {"code", "message"}})` → `resp.json()["detail"]["error"]["code"]`. No global exception handler.
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore`, `.env`, `uv.lock` (except the legitimate `uv sync` workspace-member change in Task 5 — diff-verify it), or `tools/`.

---

### Task 1: Migration 0009 — `research_notes` status lifecycle

**Files:**
- Create: `infra/migrations/versions/0009_research_notes_lifecycle.py`
- Modify: `packages/core/saalr_core/db/models/research.py`
- Test (existing, must pass): `tests/integration/test_schema_matches_models.py`

- [ ] **Step 1: Write the migration**

Create `infra/migrations/versions/0009_research_notes_lifecycle.py`:
```python
"""research_notes async lifecycle: status + error_message, nullable result cols, UPDATE grant

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-02
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE research_notes
          ADD COLUMN status TEXT NOT NULL DEFAULT 'succeeded'
            CHECK (status IN ('queued','running','succeeded','failed')),
          ADD COLUMN error_message TEXT,
          ALTER COLUMN summary           DROP NOT NULL,
          ALTER COLUMN signals_json      DROP NOT NULL,
          ALTER COLUMN sources_json      DROP NOT NULL,
          ALTER COLUMN model             DROP NOT NULL,
          ALTER COLUMN prompt_tokens     DROP NOT NULL,
          ALTER COLUMN completion_tokens DROP NOT NULL,
          ALTER COLUMN cost_usd          DROP NOT NULL;

        GRANT UPDATE ON research_notes TO saalr_app;

        CREATE INDEX idx_research_notes_tenant_created
          ON research_notes(tenant_id, created_at DESC);
    """)


def downgrade() -> None:
    # One-way nullability relaxation: NOT NULL is not re-added (rows with nulls may exist).
    op.execute("""
        DROP INDEX IF EXISTS idx_research_notes_tenant_created;
        REVOKE UPDATE ON research_notes FROM saalr_app;
        ALTER TABLE research_notes
          DROP COLUMN IF EXISTS error_message,
          DROP COLUMN IF EXISTS status;
    """)
```

CONFIRM before writing: the current migration head is `0008`. Look in `infra/migrations/versions/` for the file whose `revision = "0008"` and verify nothing has `down_revision = "0008"` yet. If the head is not `0008`, STOP and report BLOCKED.

- [ ] **Step 2: Update the model**

In `packages/core/saalr_core/db/models/research.py`, change the seven result columns to nullable and add the two lifecycle columns. The full updated class body (keep the existing imports + `__tablename__`):
```python
class ResearchNote(Base):
    __tablename__ = "research_notes"
    note_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    signals_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sources_json: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Apply the migration**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run alembic upgrade head`
Expected: applies `0009`, no error.

- [ ] **Step 4: Schema-match + mapper smoke**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_schema_matches_models.py -q`
Expected: PASS. The `research_notes` column-name set now includes `status` + `error_message`.
Run: `uv run python -c "import saalr_core.db.models; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('mappers OK')"`
Expected: `mappers OK`.

- [ ] **Step 5: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/db/models/research.py
git add infra/migrations/versions/0009_research_notes_lifecycle.py packages/core/saalr_core/db/models/research.py
git commit -m "feat(research): research_notes async status lifecycle (migration 0009)"
```

---

### Task 2: Move `load_closes` into `saalr-core`

The worker (Task 5) must read daily closes but cannot import `apps/api`. Move `load_closes` to `saalr-core` and re-export it from the forecast repo so the forecast + Monte-Carlo slices are unchanged.

**Files:**
- Create: `packages/core/saalr_core/marketdata/bars.py`
- Modify: `apps/api/saalr_api/forecast/repo.py`
- Test: `tests/integration/test_load_closes_move.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_load_closes_move.py`:
```python
def test_load_closes_is_shared_from_core():
    from saalr_api.forecast.repo import load_closes as reexported
    from saalr_core.marketdata.bars import load_closes as core_fn
    assert core_fn is reexported
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_load_closes_move.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.marketdata.bars`.

- [ ] **Step 3: Create the core module**

Create `packages/core/saalr_core/marketdata/bars.py`:
```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_closes(
    session: AsyncSession, symbol: str, market: str, lookback_days: int = 900
) -> list[float]:
    """Daily closes for `symbol` over the trailing window (non-RLS shared `bars`)."""
    start = (datetime.now(timezone.utc).date()) - timedelta(days=lookback_days)
    rows = (
        await session.execute(
            text(
                """
                SELECT close FROM bars
                WHERE symbol = :sym AND market = :mkt AND interval = '1d' AND ts::date >= :s
                ORDER BY ts
                """
            ),
            {"sym": symbol, "mkt": market, "s": start},
        )
    ).all()
    return [float(r.close) for r in rows]
```

- [ ] **Step 4: Re-export from the forecast repo**

In `apps/api/saalr_api/forecast/repo.py`, delete the `load_closes` function body and re-export the core one. The new top of the file becomes (keep `record_validation`, `_json`, `today_str` exactly as they are below):
```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.ids import new_id
from saalr_core.marketdata.bars import load_closes  # noqa: F401  (re-export for existing importers)


async def record_validation(
    session: AsyncSession,
    model_name: str,
    market: str,
    cohort_label: str,
    baseline_name: str,
    status: str,
    metric_summary_json: dict,
) -> None:
    """INSERT a model_validation_runs row (non-RLS shared table; saalr_app has grants)."""
    now = datetime.now(timezone.utc)
    await session.execute(
        text(
            """
            INSERT INTO model_validation_runs
              (validation_id, model_name, market, cohort_label, baseline_name, status,
               metric_summary_json, started_at, completed_at)
            VALUES
              (:vid, :model, :market, :cohort, :baseline, :status,
               CAST(:metrics AS JSONB), :started, :completed)
            """
        ),
        {
            "vid": str(new_id()), "model": model_name, "market": market, "cohort": cohort_label,
            "baseline": baseline_name, "status": status, "metrics": _json(metric_summary_json),
            "started": now, "completed": now,
        },
    )


def _json(d: dict) -> str:
    import json

    return json.dumps(d)


def today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()
```
(Note: `timedelta` and the `AsyncSession`-typed `load_closes` are gone from this file; `record_validation` still uses `AsyncSession`, so keep that import.)

- [ ] **Step 5: Run the test + regression**

Run: `uv run pytest tests/integration/test_load_closes_move.py -q`
Expected: PASS.
Run (regression — the forecast + Monte-Carlo paths use `load_closes`): `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_vol_forecast.py tests/integration/test_montecarlo.py -q`
Expected: PASS (behaviour unchanged).

- [ ] **Step 6: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/marketdata/bars.py apps/api/saalr_api/forecast/repo.py tests/integration/test_load_closes_move.py
git add packages/core/saalr_core/marketdata/bars.py apps/api/saalr_api/forecast/repo.py tests/integration/test_load_closes_move.py
git commit -m "refactor(marketdata): move load_closes to saalr-core (shared by the research worker)"
```

---

### Task 3: `research_queue` (Redis Streams)

Parallel to `saalr_core/queue/backtest_queue.py`, keyed on `note_id`.

**Files:**
- Create: `packages/core/saalr_core/queue/research_queue.py`
- Test: `packages/core/tests/test_research_queue.py`

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_research_queue.py`:
```python
from uuid import uuid4

from saalr_core.queue.research_queue import GROUP, STREAM, Job, _parse


def test_constants_are_research_scoped():
    assert STREAM == "saalr:research:jobs:v1"
    assert GROUP == "research-workers"


def test_parse_builds_jobs_and_skips_deleted_entries():
    tid, nid = uuid4(), uuid4()
    entries = [
        ("1-0", {"tenant_id": str(tid), "note_id": str(nid)}),
        ("2-0", None),  # an entry deleted between pending and claim
    ]
    jobs = _parse(entries)
    assert jobs == [Job(msg_id="1-0", tenant_id=tid, note_id=nid)]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_research_queue.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.queue.research_queue`.

- [ ] **Step 3: Implement**

Create `packages/core/saalr_core/queue/research_queue.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from redis.exceptions import ResponseError

STREAM = "saalr:research:jobs:v1"
GROUP = "research-workers"
_MAXLEN = 10_000


@dataclass(frozen=True)
class Job:
    msg_id: str
    tenant_id: UUID
    note_id: UUID


def _parse(entries) -> list[Job]:
    jobs: list[Job] = []
    for msg_id, fields in entries:
        if not fields:  # an entry deleted between pending and claim
            continue
        jobs.append(
            Job(
                msg_id=msg_id,
                tenant_id=UUID(fields["tenant_id"]),
                note_id=UUID(fields["note_id"]),
            )
        )
    return jobs


async def ensure_group(redis, stream: str = STREAM, group: str = GROUP) -> None:
    try:
        await redis.xgroup_create(stream, group, id="$", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def enqueue(redis, tenant_id: UUID, note_id: UUID, stream: str = STREAM) -> str:
    return await redis.xadd(
        stream,
        {"tenant_id": str(tenant_id), "note_id": str(note_id)},
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
    # Page through the pending-entries list until the cursor wraps to "0-0"; a single
    # XAUTOCLAIM returns at most `count` entries, so without this loop a crash that left
    # more than `count` jobs pending would only reclaim the first batch.
    jobs: list[Job] = []
    cursor = "0-0"
    while True:
        result = await redis.xautoclaim(
            stream, group, consumer, min_idle_ms, start_id=cursor, count=count
        )
        cursor = result[0]
        entries = result[1] if len(result) > 1 else []
        jobs.extend(_parse(entries))
        if not entries or cursor in ("0-0", "0"):
            return jobs
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_research_queue.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/queue/research_queue.py packages/core/tests/test_research_queue.py
git add packages/core/saalr_core/queue/research_queue.py packages/core/tests/test_research_queue.py
git commit -m "feat(research): research_queue Redis-Streams module"
```

---

### Task 4: Research repo (core) + API enqueue rewrite + API tests

Move RA-1's note CRUD into `saalr-core` + add the lifecycle/limit fns; rewrite the API `research` module to enqueue instead of generate; rewrite the integration tests for the async shape.

**Files:**
- Create: `packages/core/saalr_core/research/repo.py`
- Replace: `apps/api/saalr_api/research/repo.py` (becomes a re-export shim)
- Replace: `apps/api/saalr_api/research/service.py` (enqueue path; generation deleted)
- Replace: `apps/api/saalr_api/research/router.py` (status-aware endpoints)
- Modify: `apps/api/saalr_api/main.py` (research-stream `ensure_group`)
- Modify: `tests/integration/conftest.py` (truncate `research_notes`)
- Replace: `tests/integration/test_research.py` (async-shape API tests)

- [ ] **Step 1: Write the failing tests**

Replace `tests/integration/test_research.py` entirely with:
```python
import os
from decimal import Decimal

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text
from uuid import UUID

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.research import repo as rrepo

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _tier(admin_engine, tenant_id, tier):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier=:tier WHERE tenant_id=:t"),
                           {"tier": tier, "t": tenant_id})


async def _me(c, h):
    body = (await c.get("/me", headers=h)).json()
    return UUID(body["tenant"]["id"]), UUID(body["user"]["id"])


async def _clean_stream():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.delete("saalr:research:jobs:v1")
    await r.aclose()


async def _seed_succeeded(app, tid, uid, ticker="AAPL"):
    async with tenant_session(app.state.sessionmaker, tid) as s:
        nid = await rrepo.create_queued_run(s, tenant_id=tid, user_id=uid, ticker=ticker, market="US")
        await rrepo.save_succeeded(s, nid, summary="cached note", signals={"spot": 1.0},
                                   sources=[], model="stub-chat", prompt_tokens=1,
                                   completion_tokens=1, cost_usd=Decimal("0"))
    return nid


async def _seed_runs(app, tid, uid, *, queued=0, failed=0):
    async with tenant_session(app.state.sessionmaker, tid) as s:
        for _ in range(queued):
            await rrepo.create_queued_run(s, tenant_id=tid, user_id=uid, ticker="AAPL", market="US")
        for _ in range(failed):
            nid = await rrepo.create_queued_run(s, tenant_id=tid, user_id=uid, ticker="AAPL", market="US")
            await rrepo.save_failed(s, nid, "RESEARCH_NO_PRICE_DATA")


async def test_run_enqueues_202_and_poll_is_queued(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rar1@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            r = await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)
            assert r.status_code == 202, r.text
            body = r.json()
            assert body["status"] == "queued"
            assert body["poll_url"] == f"/research/notes/{body['note_id']}"
            poll = await c.get(body["poll_url"], headers=h)
            assert poll.status_code == 200 and poll.json()["status"] == "queued"


async def test_cached_succeeded_note_returns_200(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rar2@x.com"}
            tid, uid = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            nid = await _seed_succeeded(app, tid, uid)
            r = await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["cached"] is True and body["note_id"] == str(nid)
            assert body["status"] == "succeeded"


async def test_in_flight_dedup_returns_same_note(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rar3@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            a = await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)
            b = await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)
            assert a.status_code == 202 and b.status_code == 202
            assert a.json()["note_id"] == b.json()["note_id"]


async def test_rate_limit_429_after_ten_runs(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rar4@x.com"}
            tid, uid = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            await _seed_runs(app, tid, uid, queued=10)
            r = await c.post("/research/run", json={"ticker": "TSLA", "refresh": True}, headers=h)
            assert r.status_code == 429
            assert r.json()["detail"]["error"]["code"] == "RATE_LIMIT_RESEARCH_DAILY_EXCEEDED"


async def test_failed_runs_do_not_count_toward_limit(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rar5@x.com"}
            tid, uid = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            await _seed_runs(app, tid, uid, queued=5, failed=20)  # only 5 count
            r = await c.post("/research/run", json={"ticker": "TSLA", "refresh": True}, headers=h)
            assert r.status_code == 202, r.text


async def test_gating_pro_and_free_402(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            hp = {"Authorization": "Bearer dev:rar6@x.com"}
            tid, _ = await _me(c, hp)
            await _tier(admin_engine, str(tid), "pro")
            rp = await c.post("/research/run", json={"ticker": "AAPL"}, headers=hp)
            assert rp.status_code == 402
            assert rp.json()["detail"]["error"]["code"] == "ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM"
            hf = {"Authorization": "Bearer dev:rar7@x.com"}  # free default
            assert (await c.post("/research/run", json={"ticker": "AAPL"}, headers=hf)).status_code == 402


async def test_validation_400(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rar8@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            assert (await c.post("/research/run", json={"ticker": "12 3"}, headers=h)).status_code == 400
            assert (await c.post("/research/run", json={"ticker": "AAPL", "market": "IN"},
                                 headers=h)).status_code == 400


async def test_rls_isolation_poll_and_list(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            ha = {"Authorization": "Bearer dev:rar-a@x.com"}
            tida, _ = await _me(c, ha)
            await _tier(admin_engine, str(tida), "premium")
            nid = (await c.post("/research/run", json={"ticker": "AAPL"}, headers=ha)).json()["note_id"]
            hb = {"Authorization": "Bearer dev:rar-b@x.com"}
            tidb, _ = await _me(c, hb)
            await _tier(admin_engine, str(tidb), "premium")
            assert (await c.get(f"/research/notes/{nid}", headers=hb)).status_code == 404
            assert (await c.get("/research/notes", headers=hb)).json()["notes"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_research.py -q`
Expected: FAIL — `saalr_core.research.repo` does not exist / endpoints return the old sync shape.

- [ ] **Step 3: Create the core research repo**

Create `packages/core/saalr_core/research/repo.py`:
```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update

from saalr_core.db.models.research import ResearchNote
from saalr_core.ids import new_id


async def create_queued_run(session, *, tenant_id, user_id, ticker, market) -> UUID:
    note_id = new_id()
    session.add(ResearchNote(
        note_id=note_id, tenant_id=tenant_id, user_id=user_id, ticker=ticker,
        market=market, status="queued",
    ))
    await session.flush()
    return note_id


async def mark_running(session, note_id) -> None:
    await session.execute(
        update(ResearchNote).where(ResearchNote.note_id == note_id).values(status="running")
    )


async def save_succeeded(session, note_id, *, summary, signals, sources, model,
                         prompt_tokens, completion_tokens, cost_usd) -> None:
    await session.execute(
        update(ResearchNote).where(ResearchNote.note_id == note_id).values(
            status="succeeded", summary=summary, signals_json=signals, sources_json=sources,
            model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            cost_usd=cost_usd, error_message=None,
        )
    )


async def save_failed(session, note_id, code: str) -> None:
    await session.execute(
        update(ResearchNote).where(ResearchNote.note_id == note_id).values(
            status="failed", error_message=code
        )
    )


async def recent_succeeded_note(session, ticker, market, since) -> ResearchNote | None:
    return (await session.execute(
        select(ResearchNote).where(
            ResearchNote.ticker == ticker, ResearchNote.market == market,
            ResearchNote.status == "succeeded", ResearchNote.created_at >= since)
        .order_by(ResearchNote.created_at.desc()).limit(1)
    )).scalar_one_or_none()


async def in_flight_run(session, ticker, market) -> ResearchNote | None:
    return (await session.execute(
        select(ResearchNote).where(
            ResearchNote.ticker == ticker, ResearchNote.market == market,
            ResearchNote.status.in_(("queued", "running")))
        .order_by(ResearchNote.created_at.desc()).limit(1)
    )).scalar_one_or_none()


async def count_runs_today(session, tenant_id, since) -> int:
    return (await session.execute(
        select(func.count()).select_from(ResearchNote).where(
            ResearchNote.tenant_id == tenant_id, ResearchNote.created_at >= since,
            ResearchNote.status != "failed")
    )).scalar_one()


async def list_succeeded_notes(session, limit, cursor) -> list[ResearchNote]:
    stmt = (select(ResearchNote).where(ResearchNote.status == "succeeded")
            .order_by(ResearchNote.created_at.desc(), ResearchNote.note_id.desc()))
    if cursor is not None:
        created_at, nid = cursor
        stmt = stmt.where(
            (ResearchNote.created_at < created_at)
            | ((ResearchNote.created_at == created_at) & (ResearchNote.note_id < nid))
        )
    return list((await session.execute(stmt.limit(limit))).scalars().all())


async def get_note(session, note_id) -> ResearchNote | None:
    return await session.get(ResearchNote, note_id)
```

- [ ] **Step 4: Turn the API repo into a re-export shim**

Replace `apps/api/saalr_api/research/repo.py` entirely with:
```python
from __future__ import annotations

from saalr_core.research.repo import (  # noqa: F401
    count_runs_today,
    create_queued_run,
    get_note,
    in_flight_run,
    list_succeeded_notes,
    mark_running,
    recent_succeeded_note,
    save_failed,
    save_succeeded,
)
```

- [ ] **Step 5: Rewrite the API service (enqueue path)**

Replace `apps/api/saalr_api/research/service.py` entirely with:
```python
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from saalr_core.db.session import tenant_session
from saalr_core.queue.research_queue import enqueue

from . import repo

_logger = logging.getLogger("saalr.research")
_CACHE_TTL = timedelta(hours=6)
_DAILY_LIMIT = 10


def _out(note, *, cached: bool) -> dict:
    return {
        "note_id": str(note.note_id), "ticker": note.ticker, "market": note.market,
        "summary": note.summary, "signals": note.signals_json, "sources": note.sources_json,
        "model": note.model,
        "usage": {"prompt_tokens": note.prompt_tokens, "completion_tokens": note.completion_tokens},
        "cost_usd": str(note.cost_usd) if note.cost_usd is not None else None,
        "status": note.status, "cached": cached, "created_at": note.created_at.isoformat(),
    }


def _accepted(note_id, status: str) -> dict:
    return {"note_id": str(note_id), "status": status, "poll_url": f"/research/notes/{note_id}"}


def _utc_midnight() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


async def run_research(session, principal, redis, sessionmaker, ticker: str, market: str,
                       refresh: bool) -> dict:
    """Enqueue (or short-circuit) a research run. Returns {http_status, body}."""
    if not refresh:
        cached = await repo.recent_succeeded_note(
            session, ticker, market, datetime.now(timezone.utc) - _CACHE_TTL)
        if cached is not None:
            return {"http_status": 200, "body": _out(cached, cached=True)}

    inflight = await repo.in_flight_run(session, ticker, market)
    if inflight is not None:
        return {"http_status": 202, "body": _accepted(inflight.note_id, inflight.status)}

    if await repo.count_runs_today(session, principal.tenant_id, _utc_midnight()) >= _DAILY_LIMIT:
        raise HTTPException(429, {"error": {"code": "RATE_LIMIT_RESEARCH_DAILY_EXCEEDED",
                                            "message": f"daily research limit of {_DAILY_LIMIT} reached"}})

    # Create the row in its OWN committed transaction BEFORE enqueuing, so the worker
    # cannot read a row that does not yet exist (get_principal's session commits only
    # after the handler returns).
    async with tenant_session(sessionmaker, principal.tenant_id) as cs:
        note_id = await repo.create_queued_run(
            cs, tenant_id=principal.tenant_id, user_id=principal.user_id,
            ticker=ticker, market=market)

    try:
        await enqueue(redis, principal.tenant_id, note_id)
    except Exception as exc:  # noqa: BLE001 - row stays 'queued' + reclaimable; surface 503
        _logger.warning("research enqueue failed for %s: %s", note_id, exc)
        raise HTTPException(503, {"error": {"code": "RESEARCH_ENQUEUE_FAILED",
                                            "message": "could not enqueue research run"}}) from exc

    return {"http_status": 202, "body": _accepted(note_id, "queued")}
```

- [ ] **Step 6: Rewrite the router (status-aware)**

Replace `apps/api/saalr_api/research/router.py` entirely with:
```python
from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from . import repo, service
from .gating import require_research_agent
from .schemas import RunRequest

router = APIRouter(prefix="/research", tags=["research"])

_ERROR_MESSAGES = {
    "RESEARCH_NO_PRICE_DATA": "no price data for ticker",
    "RESEARCH_LLM_UNAVAILABLE": "the research assistant is temporarily unavailable",
    "RESEARCH_GENERATION_FAILED": "research generation failed",
}


def _note_row(note) -> dict:
    return {"note_id": str(note.note_id), "ticker": note.ticker, "market": note.market,
            "model": note.model,
            "cost_usd": str(note.cost_usd) if note.cost_usd is not None else None,
            "created_at": note.created_at.isoformat()}


@router.post("/run")
async def run(body: RunRequest, request: Request, response: Response,
              ctx: tuple[AsyncSession, Principal] = Depends(require_research_agent)) -> dict:
    session, principal = ctx
    ticker = body.ticker.strip().upper()
    if not ticker or not ticker.isalpha():
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "invalid ticker"}})
    if body.market not in ("US",):
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "unsupported market"}})
    result = await service.run_research(
        session, principal, request.app.state.redis, request.app.state.sessionmaker,
        ticker, body.market, body.refresh)
    response.status_code = result["http_status"]
    return result["body"]


@router.get("/notes")
async def list_notes(limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
                     ctx: tuple[AsyncSession, Principal] = Depends(require_research_agent)) -> dict:
    session, _ = ctx
    decoded = None
    if cursor:
        try:
            ts, nid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            decoded = (datetime.fromisoformat(ts), UUID(nid))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                                "message": "bad cursor"}}) from exc
    rows = await repo.list_succeeded_notes(session, limit, decoded)
    nxt = None
    if len(rows) == limit:
        last = rows[-1]
        nxt = base64.urlsafe_b64encode(f"{last.created_at.isoformat()}|{last.note_id}".encode()).decode()
    return {"notes": [_note_row(r) for r in rows], "next_cursor": nxt}


@router.get("/notes/{note_id}")
async def get_one(note_id: UUID,
                  ctx: tuple[AsyncSession, Principal] = Depends(require_research_agent)) -> dict:
    session, _ = ctx
    note = await repo.get_note(session, note_id)
    if note is None:
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "note not found"}})
    if note.status in ("queued", "running"):
        return {"note_id": str(note.note_id), "status": note.status}
    if note.status == "failed":
        code = note.error_message or "RESEARCH_GENERATION_FAILED"
        return {"note_id": str(note.note_id), "status": "failed",
                "error": {"code": code, "message": _ERROR_MESSAGES.get(code, "research generation failed")}}
    return {**_note_row(note), "status": "succeeded", "summary": note.summary,
            "signals": note.signals_json, "sources": note.sources_json,
            "usage": {"prompt_tokens": note.prompt_tokens,
                      "completion_tokens": note.completion_tokens}}
```

- [ ] **Step 7: Wire the research stream into `main.py`**

In `apps/api/saalr_api/main.py`, add an aliased import next to the backtest queue import (line ~21 `from saalr_core.queue.backtest_queue import ensure_group`):
```python
from saalr_core.queue.research_queue import ensure_group as ensure_research_group
```
In the lifespan, right after `await ensure_group(app.state.redis)`:
```python
        await ensure_research_group(app.state.redis)
```

- [ ] **Step 8: Truncate `research_notes` between tests**

In `tests/integration/conftest.py`, add `"research_notes"` to the `TENANT_TABLES` list (so the rate-limit + in-flight tests start clean). The list becomes:
```python
TENANT_TABLES = [
    "executions", "orders", "positions", "broker_accounts", "backtests",
    "strategies", "billing_events", "subscriptions", "api_keys",
    "memberships", "audit_log", "user_progress", "research_notes", "tenants",
]
```

- [ ] **Step 9: Run the new suite + regression**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_research.py -q`
Expected: PASS (8 passed).
Run regression: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_content.py tests/integration/test_schema_matches_models.py -q`
Expected: PASS.

- [ ] **Step 10: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/research/repo.py apps/api/saalr_api/research tests/integration/test_research.py tests/integration/conftest.py apps/api/saalr_api/main.py
git add packages/core/saalr_core/research/repo.py apps/api/saalr_api/research/repo.py apps/api/saalr_api/research/service.py apps/api/saalr_api/research/router.py apps/api/saalr_api/main.py tests/integration/conftest.py tests/integration/test_research.py
git commit -m "feat(research): async enqueue API + status-aware poll (RA-2)"
```

---

### Task 5: research-agent worker + end-to-end tests + runbook

The worker generates the note. Generation logic moves out of the API into the worker. The worker depends on `saalr-core[openai] + saalr-ml + saalr-content` (so `openai`/`torch` stay out of the default root env).

**Files:**
- Modify: `apps/research-agent/pyproject.toml`
- Create: `apps/research-agent/research_agent/__init__.py` (empty)
- Create: `apps/research-agent/research_agent/service.py`
- Create: `apps/research-agent/research_agent/consumer.py`
- Create: `apps/research-agent/research_agent/cli.py`
- Create: `apps/research-agent/research_agent/__main__.py`
- Create: `docs/runbooks/research-agent.md`
- Test: `tests/integration/test_research_worker.py`

> **Worker-test invocation (IMPORTANT):** the e2e test imports `research_agent`, which lives in the `saalr-research-agent` package (NOT a root dep). Run it via `--package`, exactly like the backtest e2e test:
> `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q`
> The default API gate (`uv run pytest tests/integration ...`) must `--ignore=tests/integration/test_research_worker.py` (alongside the existing backtest/ingest ignores), because `research_agent` is not importable there.

- [ ] **Step 1: Update the worker pyproject**

Replace `apps/research-agent/pyproject.toml` entirely with:
```toml
[project]
name = "saalr-research-agent"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "saalr-core[openai]",
  "saalr-ml",
  "saalr-content",
  "sqlalchemy>=2.0",
  "asyncpg>=0.29",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["research_agent"]

[tool.uv.sources]
saalr-core = { workspace = true }
saalr-ml = { workspace = true }
saalr-content = { workspace = true }

[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write the failing e2e tests**

Create `tests/integration/test_research_worker.py`:
```python
import os
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text
from uuid import UUID

from research_agent.consumer import run_consumer
from saalr_api.main import create_app
from saalr_content.loader import load_catalog
from saalr_core.db.session import create_engine, create_sessionmaker
from saalr_core.rag.chat import ChatError, StubChatProvider
from saalr_core.rag.embeddings import HashEmbeddingProvider

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _tier(admin_engine, tenant_id, tier):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier=:tier WHERE tenant_id=:t"),
                           {"tier": tier, "t": tenant_id})


async def _tid(c, h):
    return (await c.get("/me", headers=h)).json()["tenant"]["id"]


async def _clean_stream():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.delete("saalr:research:jobs:v1")
    await r.aclose()


async def _seed_bars(admin_engine, symbol, n=40, base=50.0):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol=:s"), {"s": symbol})
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol=:s"), {"s": symbol})
        for i in range(n):
            from datetime import timedelta
            ts = start + timedelta(days=i)
            px = Decimal(str(round(base + (i % 5) * 0.3, 4)))
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:s,'US','1d',:c,:c,:c,:c,1000)"""),
                {"ts": ts, "s": symbol, "c": px})


class _FailChat:
    model_name = "stub-chat"

    async def complete(self, system, user):
        raise ChatError("boom")


async def _run_worker_once(*, chat, embed, catalog):
    engine = create_engine(os.environ["APP_DATABASE_URL"])
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await run_consumer(redis, create_sessionmaker(engine), "test-research",
                           chat_provider=chat, embedding_provider=embed, catalog=catalog,
                           block_ms=1000, count=10, once=True)
    finally:
        await redis.aclose()
        await engine.dispose()


async def _post(c, h, ticker="AAPL"):
    return (await c.post("/research/run", json={"ticker": ticker}, headers=h)).json()["poll_url"]


async def test_e2e_post_consume_poll_succeeds(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw1@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            poll = await _post(c, h)
            await _run_worker_once(chat=StubChatProvider(), embed=HashEmbeddingProvider(),
                                   catalog=load_catalog())
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "succeeded", done
            assert done["summary"] and done["model"] == "stub-chat"
            assert done["signals"]["spot"] is not None


async def test_e2e_graceful_degradation(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)  # <250 -> no GARCH; no sentiment row
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw2@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            poll = await _post(c, h)
            await _run_worker_once(chat=StubChatProvider(), embed=HashEmbeddingProvider(),
                                   catalog=load_catalog())
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "succeeded"
            assert done["signals"]["vol_forecast"] is None
            assert done["signals"]["sentiment"] is None


async def test_e2e_no_bars_failed(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw3@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            poll = await _post(c, h, ticker="ZZZZ")
            await _run_worker_once(chat=StubChatProvider(), embed=HashEmbeddingProvider(),
                                   catalog=load_catalog())
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "failed"
            assert done["error"]["code"] == "RESEARCH_NO_PRICE_DATA"


async def test_e2e_llm_down_failed(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw4@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            poll = await _post(c, h)
            await _run_worker_once(chat=_FailChat(), embed=HashEmbeddingProvider(),
                                   catalog=load_catalog())
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "failed"
            assert done["error"]["code"] == "RESEARCH_LLM_UNAVAILABLE"
```

- [ ] **Step 3: Run to verify it fails**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q`
Expected: FAIL — `ModuleNotFoundError: research_agent`.

- [ ] **Step 4: Create the worker package**

Create `apps/research-agent/research_agent/__init__.py` (EMPTY file).

Create `apps/research-agent/research_agent/service.py`:
```python
from __future__ import annotations

import logging
from uuid import UUID

from saalr_core.db.session import tenant_session
from saalr_core.marketdata.bars import load_closes
from saalr_core.rag.chat import ChatError
from saalr_core.rag.embeddings import EmbeddingError
from saalr_core.rag.qa import retrieve_context
from saalr_core.research import repo
from saalr_core.research.note import ResearchInputs, build_research_prompt, estimate_cost
from saalr_core.sentiment.repo import latest_sentiment
from saalr_ml.forecast import vol_forecast

log = logging.getLogger("saalr.research.worker")


class NoPriceData(Exception):
    pass


async def gather_inputs(session, *, embedding_provider, catalog, ticker: str, market: str) -> ResearchInputs:
    closes = await load_closes(session, ticker, market)
    if not closes:
        raise NoPriceData(ticker)
    spot = closes[-1]

    vol = None
    if len(closes) >= 250:
        try:
            f = vol_forecast(closes, horizon=10)
            pf = f["primary_forecast"]
            vol = {
                "horizon_days": f["horizon_days"],
                "primary_model": f["primary_model"],
                "forecast_mean": round(sum(pf) / len(pf), 4) if pf else None,
                "status": f["alternative_models"][0]["status"] if f.get("alternative_models") else None,
            }
        except Exception as exc:  # noqa: BLE001 - best-effort signal; degrade, never fail the note
            log.warning("garch forecast unavailable for %s: %s", ticker, exc)
            vol = None

    sent = await latest_sentiment(session, ticker, market)
    sentiment = None
    if sent is not None:
        sentiment = {
            "score": round(float(sent["score"]), 4), "label": sent["label"],
            "confident": sent["confident"],
            "as_of": sent["as_of"].isoformat() if sent.get("as_of") else None,
        }

    excerpts: list[tuple[str, str, str]] = []
    if embedding_provider is not None:
        try:
            vectors = await embedding_provider.embed(
                [f"options {ticker} implied volatility sentiment risk"])
            if len(vectors) == 1:
                hits = await retrieve_context(
                    session, vectors[0], model=embedding_provider.model_name, k=3)
                for hit in hits:
                    title = hit.module_slug
                    module = catalog.by_slug(hit.module_slug) if catalog is not None else None
                    if module is not None:
                        title = module.title
                    excerpts.append((hit.module_slug, title, hit.content))
        except Exception as exc:  # noqa: BLE001 - best-effort enrichment; degrade, never fail the note
            log.warning("content retrieval unavailable for %s: %s", ticker, exc)
            excerpts = []

    return ResearchInputs(ticker, market, spot, vol, sentiment, excerpts)


async def run_research_job(sessionmaker, tenant_id: UUID, note_id: UUID, *,
                           chat_provider, embedding_provider, catalog) -> dict:
    """Generate the note for a queued run. 3 phases, each isolating its failure mode.

    A re-delivered job whose row is already succeeded/failed is a no-op (idempotent)."""
    # Phase 1 — load + mark running.
    try:
        async with tenant_session(sessionmaker, tenant_id) as session:
            note = await repo.get_note(session, note_id)
            if note is None:
                return {"status": "missing"}
            if note.status in ("succeeded", "failed"):
                return {"status": note.status}
            ticker, market = note.ticker, note.market
            await repo.mark_running(session, note_id)
    except Exception as exc:  # noqa: BLE001 - persisted as failed in a fresh tx
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_GENERATION_FAILED", exc)

    # Phase 2 — compute (DB reads close before the LLM call; provider calls hold no tx).
    try:
        async with tenant_session(sessionmaker, tenant_id) as session:
            inputs = await gather_inputs(
                session, embedding_provider=embedding_provider, catalog=catalog,
                ticker=ticker, market=market)
        if chat_provider is None:
            raise ChatError("no chat provider configured")
        system, user = build_research_prompt(inputs)
        result = await chat_provider.complete(system, user)
    except NoPriceData as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_NO_PRICE_DATA", exc)
    except (ChatError, EmbeddingError) as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_LLM_UNAVAILABLE", exc)
    except Exception as exc:  # noqa: BLE001
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_GENERATION_FAILED", exc)

    # Phase 3 — persist success.
    signals = {"spot": inputs.spot, "vol_forecast": inputs.vol_forecast, "sentiment": inputs.sentiment}
    sources = [{"slug": slug, "title": title} for slug, title, _c in inputs.content_excerpts]
    cost = estimate_cost(chat_provider.model_name, result.prompt_tokens, result.completion_tokens)
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_succeeded(
            session, note_id, summary=result.text, signals=signals, sources=sources,
            model=chat_provider.model_name, prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens, cost_usd=cost)
    return {"status": "succeeded"}


async def _fail(sessionmaker, tenant_id, note_id, code: str, exc: Exception) -> dict:
    log.warning("research job %s failed: %s (%s)", note_id, code, exc)
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_failed(session, note_id, code)
    return {"status": "failed", "code": code}
```

Create `apps/research-agent/research_agent/consumer.py`:
```python
from __future__ import annotations

import logging

from saalr_core.queue.research_queue import ack, claim_stale, consume_batch, ensure_group

from .service import run_research_job

log = logging.getLogger("saalr.research.consumer")


async def _process(redis, sessionmaker, job, *, chat_provider, embedding_provider, catalog) -> None:
    try:
        await run_research_job(
            sessionmaker, job.tenant_id, job.note_id,
            chat_provider=chat_provider, embedding_provider=embedding_provider, catalog=catalog)
    except Exception:  # noqa: BLE001 - poison guard: run_research_job persists failures itself
        log.exception("research job %s failed unexpectedly", job.note_id)
    finally:
        await ack(redis, job.msg_id)


async def run_consumer(redis, sessionmaker, consumer: str, *, chat_provider, embedding_provider,
                       catalog, block_ms: int = 5000, count: int = 10, once: bool = False,
                       claim_min_idle_ms: int = 60_000) -> None:
    await ensure_group(redis)
    for job in await claim_stale(redis, consumer, claim_min_idle_ms, count):
        await _process(redis, sessionmaker, job, chat_provider=chat_provider,
                       embedding_provider=embedding_provider, catalog=catalog)
    while True:
        for job in await consume_batch(redis, consumer, block_ms, count):
            await _process(redis, sessionmaker, job, chat_provider=chat_provider,
                           embedding_provider=embedding_provider, catalog=catalog)
        if once:
            return
```

Create `apps/research-agent/research_agent/cli.py`:
```python
from __future__ import annotations

import argparse
import asyncio
import socket

import redis.asyncio as aioredis

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="research_agent", description="Saalr research-agent worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    cn = sub.add_parser("consume", help="run the Redis-Streams research consume loop")
    cn.add_argument("--block-ms", type=int, default=5000, dest="block_ms")
    cn.add_argument("--count", type=int, default=10)
    cn.add_argument("--once", action="store_true")
    cn.add_argument("--consumer", default=None)
    return p


async def _cmd_consume(args) -> None:
    # lazy imports keep build_parser light (and torch/openai out of arg parsing)
    from saalr_content.loader import load_catalog
    from saalr_core.rag.chat import make_chat_provider
    from saalr_core.rag.embeddings import make_embedding_provider

    from .consumer import run_consumer

    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    consumer = args.consumer or f"research-{socket.gethostname()}"
    try:
        await run_consumer(
            redis, create_sessionmaker(engine), consumer,
            chat_provider=make_chat_provider(settings),
            embedding_provider=make_embedding_provider(settings),
            catalog=load_catalog(),
            block_ms=args.block_ms, count=args.count, once=args.once,
        )
    finally:
        await redis.aclose()
        await engine.dispose()


_DISPATCH = {"consume": _cmd_consume}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
```

Create `apps/research-agent/research_agent/__main__.py`:
```python
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create the runbook**

Create `docs/runbooks/research-agent.md`:
```markdown
# Research-agent worker (RA-2)

Generates async research notes from queued `research_notes` rows. The API
(`POST /research/run`) enqueues to the Redis stream `saalr:research:jobs:v1`
(consumer group `research-workers`); this worker consumes, generates, and
persists the note (status `queued → running → succeeded/failed`).

## Run

    uv run --package saalr-research-agent python -m research_agent consume

Flags: `--once` (drain then exit), `--block-ms`, `--count`, `--consumer <name>`.

## Environment

- `APP_DATABASE_URL` — Postgres (RLS app role).
- `REDIS_URL` — default `redis://localhost:6379/0`.
- `OPENAI_API_KEY` — when set (and the `openai` extra installed, which this
  worker's `saalr-core[openai]` dep provides), the worker uses real OpenAI
  embeddings + chat; otherwise `make_*_provider` returns `None` and a run fails
  with `RESEARCH_LLM_UNAVAILABLE`.

## Crash recovery

On startup the worker calls `claim_stale` (XAUTOCLAIM) to reclaim jobs left
pending by a crashed worker after `claim_min_idle_ms` (default 60s) and
reprocesses them. Delivery is at-least-once; `run_research_job` is idempotent
(a re-delivered job whose row is already `succeeded`/`failed` is a no-op).
Each job is acked in a `finally` (poison guard) — a job that always throws is
not redelivered forever; its row is persisted as `failed`.

## Rate limit

10 runs / UTC-day per tenant, enforced at the API (`count_runs_today`
excludes `failed` runs). Cache hits (`<6h` succeeded note) and in-flight
dedup short-circuit before enqueue and do not consume quota.
```

- [ ] **Step 6: Run the e2e suite**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q`
Expected: PASS (4 passed). (This invocation installs `saalr-research-agent` + its `openai` extra into the env — that is expected and isolated; Step 8 restores the lean env.)

- [ ] **Step 7: Lint + commit**

The `--package` run mutated `uv.lock` (added research-agent's resolution). The research-agent is a workspace member that now has real deps, so committing the `uv.lock` change is legitimate — but diff-verify it first.
```bash
uvx ruff check apps/research-agent/research_agent tests/integration/test_research_worker.py
git add apps/research-agent/pyproject.toml apps/research-agent/research_agent tests/integration/test_research_worker.py docs/runbooks/research-agent.md
git diff --staged uv.lock | head -40   # inspect; if it only adds saalr-research-agent + its deps, stage it:
git add uv.lock
git commit -m "feat(research): research-agent worker — async note generation (RA-2)"
```

- [ ] **Step 8: Restore the lean default env + verify isolation**

Run: `uv sync` then `uv run python -c "import importlib.util as u; print('openai', 'present' if u.find_spec('openai') else 'ABSENT')"`
Expected: `openai ABSENT` (the default env is openai-free; only `--package saalr-research-agent` pulls it in).

---

## Final verification (after all tasks)

- [ ] **Pure/unit:** `uv run pytest packages/core/tests/test_research_queue.py packages/core/tests/test_research_note.py -q` — green.
- [ ] **API gate (DB+Redis, no worker import):** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run pytest tests/integration/test_research.py tests/integration/test_load_closes_move.py tests/integration/test_schema_matches_models.py tests/integration/test_content.py -q` — green.
- [ ] **Regression (load_closes move):** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run pytest tests/integration/test_vol_forecast.py tests/integration/test_montecarlo.py -q` — green.
- [ ] **Worker e2e:** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q` — green (4 passed).
- [ ] **Isolation:** `uv sync && uv run python -c "import importlib.util as u; print('openai', 'present' if u.find_spec('openai') else 'ABSENT')"` — `openai ABSENT`.
- [ ] **Lint:** `uvx ruff check packages/core/saalr_core/research packages/core/saalr_core/queue/research_queue.py packages/core/saalr_core/marketdata/bars.py apps/api/saalr_api/research apps/research-agent/research_agent` — clean.
- [ ] **Final code-review subagent** over the whole RA-2 diff.

## Self-review notes
- **Spec coverage:** async 202/poll (T4 router + T5 worker); augmented `research_notes` lifecycle (T1); 10/UTC-day rate limit excluding failed (T4 `count_runs_today` + test); 6h cache fast-path + in-flight dedup (T4 service + tests); generation moved to the worker (T5); `load_closes`/note-CRUD moved to core (T2/T4); Redis-Streams queue (T3); crash safety reused from backtest (T5 consumer); runbook (T5). All spec sections map to a task.
- **Signature consistency:** `run_research(session, principal, redis, sessionmaker, ticker, market, refresh) -> {http_status, body}` (T4 service) matches the router call (T4). `run_research_job(sessionmaker, tenant_id, note_id, *, chat_provider, embedding_provider, catalog)` (T5 service) matches `run_consumer`'s `_process` (T5 consumer) and the e2e helper (T5 test). Repo fns (`create_queued_run`, `mark_running`, `save_succeeded`, `save_failed`, `recent_succeeded_note`, `in_flight_run`, `count_runs_today`, `list_succeeded_notes`, `get_note`) are defined once in core (T4) and re-exported by the API shim (T4) + imported by the worker (T5) with identical names.
- **Deliberate choices flagged for the reviewer:** the broad `except Exception` for best-effort GARCH/RAG signals (carried from RA-1); `error_message` stores the machine error *code* (the poll maps it to a message via `_ERROR_MESSAGES`); `count_runs_today` filters `tenant_id` explicitly even though the RLS session already scopes it (defense-in-depth); `GRANT UPDATE` in 0009 may be redundant if the baseline default privileges already grant it — harmless and explicit.
- **Worker test isolation:** `test_research_worker.py` must be `--ignore`d by the default API gate (it imports `research_agent`); it runs only under `--package saalr-research-agent`. Documented at the top of Task 5 and in the final verification.
