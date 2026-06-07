# RA-3c — Agent transcript persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the multi-agent transcript (the six agents' memo text from RA-3b) to a new `research_transcripts` table behind a pluggable `TranscriptStore`, and serve it at `GET /research/notes/{id}/transcript` (Premium) merged with each agent's `llm_usage` cost.

**Architecture:** A dedicated RLS table (migration 0011) + a `transcript_repo`; a backend-agnostic `TranscriptStore` Protocol with a `DbTranscriptStore` (S3-ready), injected like the chat/embedding providers; `run_agent_graph` returns the transcript; the worker persists it best-effort in phase 3; a new read endpoint joins memos + usage.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Postgres + RLS, Redis, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-06-03-agent-transcript-persistence-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- DB tests need Postgres on **55432**, Redis on **6379**. Prefix:
  `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <args>`
- Error shape: `HTTPException(status, {"error": {"code", "message"}})` → `resp.json()["detail"]["error"]["code"]`. No global handler.
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore`, `.env`, `uv.lock`, or `tools/`.

---

### Task 1: `research_transcripts` table — migration 0011 + model + repo

**Files:**
- Create: `infra/migrations/versions/0011_research_transcripts.py`
- Modify: `packages/core/saalr_core/db/models/research.py` (add `ResearchTranscript`)
- Create: `packages/core/saalr_core/research/transcript_repo.py`
- Test: `tests/integration/test_research_transcript_repo.py`
- Test (existing, must pass): `tests/integration/test_schema_matches_models.py`

- [ ] **Step 1: Confirm head + write the migration**

Confirm head `0010` (find the file whose `revision = "0010"`; nothing should have `down_revision = "0010"` yet). If not, STOP and report BLOCKED.

Create `infra/migrations/versions/0011_research_transcripts.py`:
```python
"""research_transcripts — per-note multi-agent transcript (RA-3c)

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-03
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE research_transcripts (
          transcript_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
          note_id         UUID NOT NULL UNIQUE REFERENCES research_notes(note_id),
          transcript_json JSONB NOT NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        GRANT SELECT, INSERT ON research_transcripts TO saalr_app;

        ALTER TABLE research_transcripts ENABLE ROW LEVEL SECURITY;
        ALTER TABLE research_transcripts FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON research_transcripts
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON research_transcripts;")
    op.execute("DROP TABLE IF EXISTS research_transcripts;")
```

- [ ] **Step 2: Add the model**

In `packages/core/saalr_core/db/models/research.py`, append a `ResearchTranscript` class (the file already imports `datetime`, `UUID`, `ForeignKey`, `Text`, `func`, `JSONB`, `TIMESTAMP`, `PG_UUID`, `Mapped`, `mapped_column`, `Base`, `new_id` for `ResearchNote` — reuse them; add nothing to `__init__.py` since `research` is already imported there):
```python
class ResearchTranscript(Base):
    __tablename__ = "research_transcripts"
    transcript_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    note_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("research_notes.note_id"), nullable=False, unique=True)
    transcript_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
```
First READ the existing `research.py` to confirm those names are imported (they are, for `ResearchNote`). If any are missing (e.g. `JSONB`), add the import.

- [ ] **Step 3: Write the repo**

Create `packages/core/saalr_core/research/transcript_repo.py`:
```python
from __future__ import annotations

from sqlalchemy import select

from saalr_core.db.models.research import ResearchTranscript
from saalr_core.ids import new_id


async def insert_transcript(session, *, tenant_id, note_id, steps: list) -> None:
    session.add(ResearchTranscript(
        transcript_id=new_id(), tenant_id=tenant_id, note_id=note_id, transcript_json=steps))
    await session.flush()


async def get_transcript(session, note_id) -> list | None:
    return (await session.execute(
        select(ResearchTranscript.transcript_json).where(ResearchTranscript.note_id == note_id)
    )).scalar_one_or_none()
```

- [ ] **Step 4: Write the failing repo test**

Create `tests/integration/test_research_transcript_repo.py`:
```python
from uuid import UUID, uuid4

import httpx

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.research import repo as note_repo
from saalr_core.research import transcript_repo


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _me(c, h):
    body = (await c.get("/me", headers=h)).json()
    return UUID(body["tenant"]["id"]), UUID(body["user"]["id"])


_STEPS = [{"role": "fundamentals", "memo": "F"}, {"role": "pm", "memo": "P"}]


async def test_insert_then_get_round_trips(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            tid, uid = await _me(c, {"Authorization": "Bearer dev:tr1@x.com"})
            async with tenant_session(app.state.sessionmaker, tid) as s:
                note_id = await note_repo.create_queued_run(
                    s, tenant_id=tid, user_id=uid, ticker="AAPL", market="US")
            async with tenant_session(app.state.sessionmaker, tid) as s:
                await transcript_repo.insert_transcript(
                    s, tenant_id=tid, note_id=note_id, steps=_STEPS)
            async with tenant_session(app.state.sessionmaker, tid) as s:
                got = await transcript_repo.get_transcript(s, note_id)
                assert got == _STEPS
                assert await transcript_repo.get_transcript(s, uuid4()) is None
```

- [ ] **Step 5: Apply migration + run tests**

Run (DB env prefix): `uv run alembic upgrade head`
Expected: applies `0011`, no error.
Run (DB env prefix): `uv run pytest tests/integration/test_schema_matches_models.py tests/integration/test_research_transcript_repo.py -q`
Expected: PASS.
Run: `uv run python -c "import saalr_core.db.models; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('mappers OK')"`
Expected: `mappers OK`.

- [ ] **Step 6: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/db/models/research.py packages/core/saalr_core/research/transcript_repo.py tests/integration/test_research_transcript_repo.py
git add infra/migrations/versions/0011_research_transcripts.py packages/core/saalr_core/db/models/research.py packages/core/saalr_core/research/transcript_repo.py tests/integration/test_research_transcript_repo.py
git commit -m "feat(research): research_transcripts table (migration 0011) + repo"
```

---

### Task 2: `TranscriptStore` + graph returns the transcript

**Files:**
- Create: `packages/core/saalr_core/research/transcript_store.py`
- Modify: `packages/core/saalr_core/research/graph.py`
- Test: `tests/integration/test_transcript_store.py`
- Test: `tests/integration/test_agent_graph.py` (append one assertion-test)

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_transcript_store.py`:
```python
from uuid import UUID, uuid4

import httpx

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.research import repo as note_repo
from saalr_core.research.transcript_store import DbTranscriptStore, make_transcript_store


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _me(c, h):
    body = (await c.get("/me", headers=h)).json()
    return UUID(body["tenant"]["id"]), UUID(body["user"]["id"])


_STEPS = [{"role": "fundamentals", "memo": "F"}, {"role": "pm", "memo": "P"}]


async def test_db_store_save_then_load(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            tid, uid = await _me(c, {"Authorization": "Bearer dev:ts1@x.com"})
            async with tenant_session(app.state.sessionmaker, tid) as s:
                note_id = await note_repo.create_queued_run(
                    s, tenant_id=tid, user_id=uid, ticker="AAPL", market="US")
            store = DbTranscriptStore(app.state.sessionmaker)
            await store.save(tenant_id=tid, note_id=note_id, steps=_STEPS)
            assert await store.load(tenant_id=tid, note_id=note_id) == _STEPS
            assert await store.load(tenant_id=tid, note_id=uuid4()) is None


async def test_make_transcript_store_returns_db_store(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        store = make_transcript_store(object(), app.state.sessionmaker)
        assert isinstance(store, DbTranscriptStore)
```

Append to `tests/integration/test_agent_graph.py` (it already imports `run_agent_graph`, `ChatGateway`, `StubChatProvider`, `ResearchInputs`, `Decimal`, `uuid4`, `_me`, `_client`):
```python
async def test_run_agent_graph_returns_full_transcript(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            tid, uid = await _me(c, {"Authorization": "Bearer dev:graph3@x.com"})
            res = await run_agent_graph(
                app.state.sessionmaker, tid, uid, inputs=ResearchInputs("AAPL", "US", 50.0, None, None, []),
                gateway=ChatGateway([StubChatProvider()]), cap=Decimal("10"), note_id=uuid4())
            roles = [s["role"] for s in res.transcript]
            assert roles == ["fundamentals", "sentiment", "technical", "risk", "trader", "pm"]
            assert all(s["memo"] for s in res.transcript)
            assert res.transcript[-1]["memo"] == res.note_markdown
```

- [ ] **Step 2: Run to verify they fail**

Run (DB env prefix): `uv run pytest tests/integration/test_transcript_store.py tests/integration/test_agent_graph.py -q`
Expected: FAIL — `saalr_core.research.transcript_store` missing; `AgentGraphResult` has no `transcript`.

- [ ] **Step 3: Create the store**

Create `packages/core/saalr_core/research/transcript_store.py`:
```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from saalr_core.db.session import tenant_session
from saalr_core.research import transcript_repo


@runtime_checkable
class TranscriptStore(Protocol):
    async def save(self, *, tenant_id, note_id, steps: list[dict]) -> None: ...
    async def load(self, *, tenant_id, note_id) -> list[dict] | None: ...


class DbTranscriptStore:
    """Postgres-backed transcript store. Each method opens its own tenant session, so the
    TranscriptStore interface stays backend-agnostic (an S3TranscriptStore swaps in later)."""

    def __init__(self, sessionmaker) -> None:
        self._sm = sessionmaker

    async def save(self, *, tenant_id, note_id, steps: list[dict]) -> None:
        async with tenant_session(self._sm, tenant_id) as s:
            await transcript_repo.insert_transcript(s, tenant_id=tenant_id, note_id=note_id, steps=steps)

    async def load(self, *, tenant_id, note_id) -> list[dict] | None:
        async with tenant_session(self._sm, tenant_id) as s:
            return await transcript_repo.get_transcript(s, note_id)


def make_transcript_store(settings, sessionmaker) -> TranscriptStore:
    """DB store now; the S3 branch is deferred to the AWS-foundation slice."""
    return DbTranscriptStore(sessionmaker)
```

- [ ] **Step 4: Graph returns the transcript**

In `packages/core/saalr_core/research/graph.py`:
- Add the `transcript` field to `AgentGraphResult` (after `provider`):
```python
@dataclass(frozen=True)
class AgentGraphResult:
    note_markdown: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    model: str
    provider: str
    transcript: list[dict]
```
- In `run_agent_graph`, after the PM call (`pm = await _call("research_agent:pm", system, user)`), set the PM memo and build the transcript, then include it in the return:
```python
    memos["pm"] = pm.text
    transcript = [{"role": r, "memo": memos[r]} for r in (*ANALYST_ROLES, "trader", "pm")]

    return AgentGraphResult(
        note_markdown=pm.text, prompt_tokens=totals["p"], completion_tokens=totals["c"],
        cost_usd=totals["cost"], model=pm.model or gateway.model_name,
        provider=pm.provider or getattr(gateway, "name", "unknown"), transcript=transcript)
```

- [ ] **Step 5: Run to verify they pass**

Run (DB env prefix): `uv run pytest tests/integration/test_transcript_store.py tests/integration/test_agent_graph.py -q`
Expected: PASS (test_agent_graph.py now has 3 tests; test_transcript_store.py has 2).

- [ ] **Step 6: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/research/transcript_store.py packages/core/saalr_core/research/graph.py tests/integration/test_transcript_store.py tests/integration/test_agent_graph.py
git add packages/core/saalr_core/research/transcript_store.py packages/core/saalr_core/research/graph.py tests/integration/test_transcript_store.py tests/integration/test_agent_graph.py
git commit -m "feat(research): TranscriptStore (DB-backed) + graph returns the transcript"
```

---

### Task 3: Worker persists the transcript (best-effort)

**Files:**
- Modify: `apps/research-agent/research_agent/service.py`
- Modify: `apps/research-agent/research_agent/consumer.py`
- Modify: `apps/research-agent/research_agent/cli.py`
- Test: `tests/integration/test_research_worker.py` (extend)

> **Worker-test invocation:** `--package saalr-research-agent` (env prefix as above).

- [ ] **Step 1: Extend the e2e tests**

In `tests/integration/test_research_worker.py`, add a raising store + two tests. The `_run_worker_once` helper currently builds the store implicitly via the consumer; change it to accept an optional `transcript_store` and pass it through. Replace the existing `_run_worker_once` with:
```python
from saalr_core.research.transcript_store import DbTranscriptStore


async def _run_worker_once(*, chat, cap=_CAP, transcript_store=None):
    engine = create_engine(os.environ["APP_DATABASE_URL"])
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    sm = create_sessionmaker(engine)
    store = transcript_store if transcript_store is not None else DbTranscriptStore(sm)
    try:
        await run_consumer(redis, sm, "test-research",
                           chat_provider=chat, embedding_provider=HashEmbeddingProvider(),
                           catalog=load_catalog(), cap=cap, transcript_store=store,
                           block_ms=1000, count=10, once=True)
    finally:
        await redis.aclose()
        await engine.dispose()
```
Append these tests:
```python
class _RaisingStore:
    async def save(self, *, tenant_id, note_id, steps):
        raise RuntimeError("transcript backend down")

    async def load(self, *, tenant_id, note_id):
        return None


async def test_e2e_persists_transcript(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rwt1@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            poll = await _post(c, h)
            await _run_worker_once(chat=ChatGateway([StubChatProvider()]))
            assert (await c.get(poll, headers=h)).json()["status"] == "succeeded"
            async with admin_engine.begin() as conn:
                row = (await conn.execute(
                    text("SELECT transcript_json FROM research_transcripts WHERE tenant_id=:t"),
                    {"t": str(tid)})).first()
            assert row is not None
            roles = [s["role"] for s in row.transcript_json]
            assert roles == ["fundamentals", "sentiment", "technical", "risk", "trader", "pm"]


async def test_e2e_transcript_failure_is_best_effort(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rwt2@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            poll = await _post(c, h)
            await _run_worker_once(chat=ChatGateway([StubChatProvider()]),
                                   transcript_store=_RaisingStore())
            # the note still succeeds even though the transcript write raised
            assert (await c.get(poll, headers=h)).json()["status"] == "succeeded"
            async with admin_engine.begin() as conn:
                row = (await conn.execute(
                    text("SELECT 1 FROM research_transcripts WHERE tenant_id=:t"),
                    {"t": str(tid)})).first()
            assert row is None
```

- [ ] **Step 2: Run to verify they fail**

Run (DB+Redis env prefix): `uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q`
Expected: FAIL — `run_consumer()` got an unexpected keyword argument `transcript_store`.

- [ ] **Step 3: Thread the store + persist in `service.py`**

In `apps/research-agent/research_agent/service.py`:
- Add `transcript_store` to the `run_research_job` signature (keyword-only, after `cap`):
```python
async def run_research_job(sessionmaker, tenant_id: UUID, note_id: UUID, *,
                           chat_provider, embedding_provider, catalog, cap: Decimal,
                           transcript_store) -> dict:
```
- Phases 1 and 2 are UNCHANGED. In phase 3, after the `save_succeeded` `async with` block and before `return {"status": "succeeded"}`, add the best-effort transcript persist:
```python
    try:
        await transcript_store.save(tenant_id=tenant_id, note_id=note_id, steps=graph.transcript)
    except Exception as exc:  # noqa: BLE001 - supplementary; a transcript write must not fail the note
        log.warning("transcript persist failed for %s: %s", note_id, exc)
    return {"status": "succeeded"}
```

- [ ] **Step 4: Thread `transcript_store` through `consumer.py`**

In `apps/research-agent/research_agent/consumer.py`, add `transcript_store` to both functions and pass it through:
```python
async def _process(redis, sessionmaker, job, *, chat_provider, embedding_provider, catalog, cap,
                   transcript_store) -> None:
    try:
        await run_research_job(
            sessionmaker, job.tenant_id, job.note_id,
            chat_provider=chat_provider, embedding_provider=embedding_provider,
            catalog=catalog, cap=cap, transcript_store=transcript_store)
    except Exception:  # noqa: BLE001 - poison guard: run_research_job persists failures itself
        log.exception("research job %s failed unexpectedly", job.note_id)
    finally:
        await ack(redis, job.msg_id)


async def run_consumer(redis, sessionmaker, consumer: str, *, chat_provider, embedding_provider,
                       catalog, cap, transcript_store, block_ms: int = 5000, count: int = 10,
                       once: bool = False, claim_min_idle_ms: int = 60_000) -> None:
    await ensure_group(redis)
    for job in await claim_stale(redis, consumer, claim_min_idle_ms, count):
        await _process(redis, sessionmaker, job, chat_provider=chat_provider,
                       embedding_provider=embedding_provider, catalog=catalog, cap=cap,
                       transcript_store=transcript_store)
    while True:
        for job in await consume_batch(redis, consumer, block_ms, count):
            await _process(redis, sessionmaker, job, chat_provider=chat_provider,
                           embedding_provider=embedding_provider, catalog=catalog, cap=cap,
                           transcript_store=transcript_store)
        if once:
            return
```

- [ ] **Step 5: Build the store in `cli.py`**

In `apps/research-agent/research_agent/cli.py`, update `_cmd_consume` to build the store (add the lazy import + a `sm` local + the `transcript_store=` kwarg):
```python
async def _cmd_consume(args) -> None:
    # lazy imports keep build_parser light
    from saalr_content.loader import load_catalog
    from saalr_core.llm.cost import monthly_cap
    from saalr_core.llm.gateway import make_chat_gateway
    from saalr_core.rag.embeddings import make_embedding_provider
    from saalr_core.research.transcript_store import make_transcript_store

    from .consumer import run_consumer

    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    sm = create_sessionmaker(engine)
    consumer = args.consumer or f"research-{socket.gethostname()}"
    try:
        await run_consumer(
            redis, sm, consumer,
            chat_provider=make_chat_gateway(settings),
            embedding_provider=make_embedding_provider(settings),
            catalog=load_catalog(),
            cap=monthly_cap(settings),
            transcript_store=make_transcript_store(settings, sm),
            block_ms=args.block_ms, count=args.count, once=args.once,
        )
    finally:
        await redis.aclose()
        await engine.dispose()
```

- [ ] **Step 6: Run the e2e suite**

Run (DB+Redis env prefix): `uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q`
Expected: PASS (9 passed — the 7 RA-3b tests, now passing `transcript_store` via the updated `_run_worker_once`, + the 2 new transcript tests).

- [ ] **Step 7: Lint + commit**
```bash
uvx ruff check apps/research-agent/research_agent tests/integration/test_research_worker.py
git add apps/research-agent/research_agent/service.py apps/research-agent/research_agent/consumer.py apps/research-agent/research_agent/cli.py tests/integration/test_research_worker.py
git commit -m "feat(research): worker persists the agent transcript best-effort (RA-3c)"
```

---

### Task 4: Read endpoint — `GET /research/notes/{id}/transcript`

**Files:**
- Modify: `packages/core/saalr_core/llm/repo.py` (add `usage_for_note`)
- Modify: `apps/api/saalr_api/research/router.py` (add the endpoint)
- Modify: `apps/api/saalr_api/main.py` (inject `app.state.transcript_store`)
- Test: `tests/integration/test_research_transcript.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_research_transcript.py`:
```python
import os
from uuid import UUID, uuid4

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text

from research_agent.consumer import run_consumer
from saalr_api.main import create_app
from saalr_content.loader import load_catalog
from saalr_core.db.session import create_engine, create_sessionmaker
from saalr_core.llm.gateway import ChatGateway
from saalr_core.rag.chat import StubChatProvider
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.research.transcript_store import DbTranscriptStore
from decimal import Decimal

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _tier(admin_engine, tenant_id, tier):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier=:tier WHERE tenant_id=:t"),
                           {"tier": tier, "t": tenant_id})


async def _tid(c, h):
    return (await c.get("/me", headers=h)).json()["tenant"]["id"]


async def _seed_bars(admin_engine, symbol, n=40, base=50.0):
    from datetime import datetime, timedelta, timezone
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol=:s"), {"s": symbol})
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol=:s"), {"s": symbol})
        for i in range(n):
            ts = start + timedelta(days=i)
            px = Decimal(str(round(base + (i % 5) * 0.3, 4)))
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:s,'US','1d',:c,:c,:c,:c,1000)"""),
                {"ts": ts, "s": symbol, "c": px})


async def _run_worker(app):
    engine = create_engine(os.environ["APP_DATABASE_URL"])
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    sm = create_sessionmaker(engine)
    try:
        await run_consumer(redis, sm, "test-tr", chat_provider=ChatGateway([StubChatProvider()]),
                           embedding_provider=HashEmbeddingProvider(), catalog=load_catalog(),
                           cap=Decimal("10"), transcript_store=DbTranscriptStore(sm),
                           block_ms=1000, count=10, once=True)
    finally:
        await redis.aclose()
        await engine.dispose()


async def _clean_stream():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r.delete("saalr:research:jobs:v1")
    await r.aclose()


async def test_transcript_endpoint_merges_memo_and_usage(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:trapi1@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            note_id = (await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)).json()["note_id"]
            await _run_worker(app)
            r = await c.get(f"/research/notes/{note_id}/transcript", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["note_id"] == note_id
            roles = [s["role"] for s in body["steps"]]
            assert roles == ["fundamentals", "sentiment", "technical", "risk", "trader", "pm"]
            first = body["steps"][0]
            assert first["memo"] and first["provider"] == "stub" and first["model"] == "stub-chat"
            assert "cost_usd" in first and isinstance(first["prompt_tokens"], int)


async def test_transcript_unknown_note_404(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:trapi2@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            r = await c.get(f"/research/notes/{uuid4()}/transcript", headers=h)
            assert r.status_code == 404


async def test_transcript_free_tier_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:trapi3@x.com"}  # free default
            r = await c.get(f"/research/notes/{uuid4()}/transcript", headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM"
```

- [ ] **Step 2: Run to verify it fails**

Run (DB+Redis env prefix): `uv run --package saalr-research-agent pytest tests/integration/test_research_transcript.py -q`
Expected: FAIL — the endpoint 404s as an unknown route / `app.state.transcript_store` missing.
(Run via `--package` because the test imports `research_agent` to drive the worker.)

- [ ] **Step 3: Add `usage_for_note` to the LLM repo**

In `packages/core/saalr_core/llm/repo.py`, add:
```python
async def usage_for_note(session, note_id) -> list:
    """All LLM-usage rows tied to a note (used by the transcript endpoint to join cost by role)."""
    return list((await session.execute(
        select(LlmUsage.purpose, LlmUsage.provider, LlmUsage.model, LlmUsage.prompt_tokens,
               LlmUsage.completion_tokens, LlmUsage.cost_usd)
        .where(LlmUsage.note_id == note_id)
    )).all())
```
(`select` and `LlmUsage` are already imported in that file.)

- [ ] **Step 4: Add the endpoint to the router**

In `apps/api/saalr_api/research/router.py`:
- Add the import near the top:
```python
from saalr_core.llm import repo as llm_repo
```
- Add the endpoint (place it after `get_one`):
```python
@router.get("/notes/{note_id}/transcript")
async def get_transcript(note_id: UUID, request: Request,
                         ctx: tuple[AsyncSession, Principal] = Depends(require_research_agent)) -> dict:
    session, principal = ctx
    note = await repo.get_note(session, note_id)
    if note is None:
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "note not found"}})
    steps = await request.app.state.transcript_store.load(
        tenant_id=principal.tenant_id, note_id=note_id)
    if steps is None:
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND",
                                            "message": "no transcript for note"}})
    by_role = {}
    for row in await llm_repo.usage_for_note(session, note_id):
        if row.purpose.startswith("research_agent:"):
            by_role[row.purpose.split(":", 1)[1]] = row
    out = []
    for step in steps:
        u = by_role.get(step["role"])
        out.append({
            "role": step["role"], "memo": step["memo"],
            "provider": u.provider if u else None,
            "model": u.model if u else None,
            "prompt_tokens": u.prompt_tokens if u else None,
            "completion_tokens": u.completion_tokens if u else None,
            "cost_usd": str(u.cost_usd) if u else None,
        })
    return {"note_id": str(note_id), "steps": out}
```

- [ ] **Step 5: Inject the store on `app.state`**

In `apps/api/saalr_api/main.py`:
- Add the import next to the other `saalr_core` imports:
```python
from saalr_core.research.transcript_store import make_transcript_store
```
- In the lifespan, after `app.state.llm_budget_cap = monthly_cap(settings)`:
```python
        app.state.transcript_store = make_transcript_store(settings, app.state.sessionmaker)
```

- [ ] **Step 6: Run the new test + regression**

Run (DB+Redis env prefix): `uv run --package saalr-research-agent pytest tests/integration/test_research_transcript.py -q`
Expected: PASS (3 passed).
Run regression (DB+Redis env prefix): `uv run pytest tests/integration/test_research.py -q`
Expected: PASS (9 — the existing research API tests; `app.state.transcript_store` is now set but they don't use it).

- [ ] **Step 7: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/llm/repo.py apps/api/saalr_api/research/router.py apps/api/saalr_api/main.py tests/integration/test_research_transcript.py
git add packages/core/saalr_core/llm/repo.py apps/api/saalr_api/research/router.py apps/api/saalr_api/main.py tests/integration/test_research_transcript.py
git commit -m "feat(research): GET /research/notes/{id}/transcript (memos + usage) (RA-3c)"
```

---

### Task 5: Runbook update

**Files:**
- Modify: `docs/runbooks/research-agent.md`

- [ ] **Step 1: Add the transcripts section**

Append to `docs/runbooks/research-agent.md`:
```markdown

## Transcripts (RA-3c)

Each succeeded run's six agent memos are persisted to `research_transcripts`
(one JSONB row keyed by `note_id`, `transcript_json` = `[{role, memo}, …]` in
graph order). The write is **best-effort** in worker phase 3: a failure logs but
does NOT fail the (already generated + paid-for) note, so a succeeded note can
lack a transcript. The `note_id UNIQUE` constraint + the best-effort catch absorb
at-least-once redelivery (a re-run can't create a second transcript row).

Read it at `GET /research/notes/{id}/transcript` (Premium) — it loads the memos
from the store and merges each agent's `provider`/`model`/tokens/`cost_usd` from
`llm_usage` (joined by `note_id` + `purpose="research_agent:<role>"`), so cost is
not duplicated in the transcript. The poll/list endpoints are unchanged.

The store is **pluggable** (`TranscriptStore` Protocol, injected on
`app.state.transcript_store` and threaded into the worker): `DbTranscriptStore`
today; an `S3TranscriptStore` drops in when the AWS-foundation slice lands, with
no caller change.
```

- [ ] **Step 2: Commit**
```bash
git add docs/runbooks/research-agent.md
git commit -m "docs(research): runbook — transcripts (RA-3c)"
```

---

## Final verification (after all tasks)

- [ ] **DB (default gate):** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run pytest tests/integration/test_research_transcript_repo.py tests/integration/test_transcript_store.py tests/integration/test_agent_graph.py tests/integration/test_schema_matches_models.py tests/integration/test_research.py -q` — green.
- [ ] **Worker + API e2e (`--package`):** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py tests/integration/test_research_transcript.py -q` — green (9 + 3).
- [ ] **Pure regression:** `uv run pytest packages/core/tests/test_research_agents.py packages/core/tests/test_llm_gateway.py -q` — green.
- [ ] **Isolation:** `uv sync && uv run python -c "import importlib.util as u; print('openai', bool(u.find_spec('openai')), 'anthropic', bool(u.find_spec('anthropic')))"` — `openai False anthropic False`.
- [ ] **Lint:** `uvx ruff check packages/core/saalr_core/research packages/core/saalr_core/llm/repo.py apps/research-agent/research_agent apps/api/saalr_api/research` — clean.
- [ ] **Final code-review subagent** over the whole RA-3c diff.

## Self-review notes
- **Spec coverage:** `research_transcripts` table + repo (T1); `TranscriptStore` Protocol + `DbTranscriptStore` + `make_transcript_store` + graph transcript (T2); worker best-effort persist + injection through consumer/cli (T3); read endpoint + `usage_for_note` join + `app.state` injection (T4); runbook (T5). All spec sections map to a task.
- **Signature consistency:** `TranscriptStore.save(*, tenant_id, note_id, steps)` / `load(*, tenant_id, note_id)` (T2) ↔ worker `transcript_store.save(...)` (T3) ↔ endpoint `transcript_store.load(...)` (T4) ↔ the test `_RaisingStore`/`DbTranscriptStore` (T3/T4). `run_research_job(..., transcript_store)` (T3 service) ↔ `_process`/`run_consumer(..., transcript_store)` (T3 consumer) ↔ `_run_worker_once`/cli (T3). `AgentGraphResult.transcript` (T2) ↔ `graph.transcript` used by the worker (T3). `transcript_repo.insert_transcript`/`get_transcript` (T1) wrapped by `DbTranscriptStore` (T2).
- **Deliberate choices flagged for the reviewer:** transcript persistence is best-effort (a succeeded note may lack a transcript); the transcript stores only memo text (usage joined from `llm_usage` by the endpoint, not duplicated); `note_id UNIQUE` + the best-effort `except` make crash-retry safe; `ResearchTranscript` lives in `db/models/research.py` (no `__init__` change — `research` is already imported); the store interface is session-free (backend-agnostic) so each `DbTranscriptStore` method opens its own `tenant_session`.
- **No-regression:** the note schema + poll/list endpoints are unchanged; RA-3b's `test_research_worker.py` tests stay green once `_run_worker_once` passes the new `transcript_store` (a `DbTranscriptStore` by default); RA-3a's `test_research.py` (9) is unaffected (it never calls the transcript endpoint, and `app.state.transcript_store` is merely set). `make_transcript_store(object(), sessionmaker)` ignores its `settings` arg today, so the unit test passes a bare `object()`.
