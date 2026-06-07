# Research-note core (RA-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /research/run` — a synchronous, Premium research-note generator that fuses spot + GARCH vol forecast + FinBERT sentiment + RAG concept excerpts into one LLM-authored markdown note with a deterministic signals snapshot, sources, and a stamped token/cost; plus `GET /research/notes` and `GET /research/notes/{id}`.

**Architecture:** A pure `saalr_core/research/note.py` (prompt builder + cost estimator). A `research_notes` RLS table (migration 0008). An API `research` module composes the platform's existing signals (best-effort, degrading gracefully), calls the injectable RAG-2 `ChatProvider`, persists, and serves a 6h per-ticker cache. Gated Premium via a new `require_research_agent` dependency. Stub-testable with no API key.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Postgres + pgvector, pytest. `openai` is an optional dep (lazy via the chat provider).

**Spec:** `docs/superpowers/specs/2026-06-02-research-note-core-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- DB tests need Postgres on **55432**. Prefix pytest:
  `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <args>`
- Error shape: `HTTPException(status, {"error": {"code", "message"}})` → `resp.json()["detail"]["error"]["code"]`.
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore`, `.env`, `uv.lock`, or `tools/`.

---

### Task 1: Pure research note (`saalr_core/research/note.py`)

**Files:**
- Create: `packages/core/saalr_core/research/__init__.py` (empty)
- Create: `packages/core/saalr_core/research/note.py`
- Test: `packages/core/tests/test_research_note.py`

Pure (no DB/network). Tested under the default gate.

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_research_note.py`:
```python
from decimal import Decimal

from saalr_core.research.note import ResearchInputs, build_research_prompt, estimate_cost


def _inputs(spot=50.0, vol={"primary_model": "garch", "forecast_mean": 0.21},
            sentiment={"score": 0.3, "label": "bullish"}, excerpts=None):
    return ResearchInputs("AAPL", "US", spot, vol, sentiment,
                          excerpts if excerpts is not None
                          else [("greeks-delta", "The Greeks: Delta", "Delta measures exposure.")])


def test_prompt_has_sections_and_grounding():
    system, user = build_research_prompt(_inputs())
    for sec in ("Overview", "Volatility", "Sentiment", "Risks", "Summary"):
        assert sec in system
    assert "Do not invent" in system
    assert "AAPL" in user and "50.0" in user
    assert "garch" in user and "bullish" in user
    assert "Delta measures exposure." in user and "greeks-delta" in user


def test_prompt_annotates_missing_signals():
    system, user = build_research_prompt(_inputs(spot=None, vol=None, sentiment=None, excerpts=[]))
    assert "unavailable" in user  # spot + vol unavailable annotated
    assert "no recent sentiment" in user
    assert "(none)" in user  # no excerpts


def test_estimate_cost_rate_math():
    # 1M prompt + 1M completion at gpt-4o-mini ($0.15 / $0.60 per 1M)
    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == Decimal("0.750000")
    assert estimate_cost("stub-chat", 1000, 1000) == Decimal("0.000000")
    assert estimate_cost("unknown-model", 1000, 1000) == Decimal("0.000000")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_research_note.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.research.note`.

- [ ] **Step 3: Implement**

Create `packages/core/saalr_core/research/__init__.py` (EMPTY file).

Create `packages/core/saalr_core/research/note.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# USD per 1,000,000 tokens (prompt, completion). Estimate; the real bill is the source of truth.
_RATES: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "stub-chat": (Decimal(0), Decimal(0)),
}

_SYSTEM = (
    "You are a Saalr research analyst. Write a concise markdown research note with these sections: "
    "Overview, Volatility, Sentiment, Risks, Summary. Use ONLY the signals and concept excerpts "
    "provided. When a signal is unavailable, say so explicitly. Do not invent data, prices, or "
    "recommendations; this is educational analysis, not advice."
)


@dataclass(frozen=True)
class ResearchInputs:
    ticker: str
    market: str
    spot: float | None
    vol_forecast: dict | None
    sentiment: dict | None
    content_excerpts: list[tuple[str, str, str]]  # (slug, title, content)


def build_research_prompt(inputs: ResearchInputs) -> tuple[str, str]:
    """Pure: (system, user) grounding the note in the composed signals + concept excerpts."""
    lines = [f"Ticker: {inputs.ticker} ({inputs.market})", "", "Signals:"]
    lines.append(f"- Spot: {inputs.spot}" if inputs.spot is not None else "- Spot: unavailable")
    lines.append(f"- Volatility forecast (GARCH): {inputs.vol_forecast}"
                 if inputs.vol_forecast is not None else "- Volatility forecast: unavailable")
    lines.append(f"- Sentiment: {inputs.sentiment}"
                 if inputs.sentiment is not None else "- Sentiment: no recent sentiment")
    lines += ["", "Concept excerpts:"]
    if inputs.content_excerpts:
        for i, (slug, _title, content) in enumerate(inputs.content_excerpts, 1):
            lines.append(f"[{i}] ({slug}) {content}")
    else:
        lines.append("(none)")
    return _SYSTEM, "\n".join(lines)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Estimated USD cost for a completion. Unknown model -> 0. Quantized to 6 dp."""
    rate_p, rate_c = _RATES.get(model, (Decimal(0), Decimal(0)))
    cost = (Decimal(prompt_tokens) / Decimal(1_000_000) * rate_p
            + Decimal(completion_tokens) / Decimal(1_000_000) * rate_c)
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_research_note.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/research packages/core/tests/test_research_note.py
git add packages/core/saalr_core/research packages/core/tests/test_research_note.py
git commit -m "feat(research): pure research-note prompt builder + cost estimator"
```

---

### Task 2: `research_notes` table — migration + model

**Files:**
- Create: `infra/migrations/versions/0008_research_notes.py`
- Create: `packages/core/saalr_core/db/models/research.py`
- Modify: `packages/core/saalr_core/db/models/__init__.py`
- Test: `tests/integration/test_schema_matches_models.py` (existing — must pass)

DB on 55432. RLS tenant table (mirrors `user_progress` 0006).

- [ ] **Step 1: Write the migration**

Create `infra/migrations/versions/0008_research_notes.py`:
```python
"""research_notes table for the RA-1 research-note core

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-02
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE research_notes (
          note_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id           UUID NOT NULL REFERENCES users(user_id),
          ticker            TEXT NOT NULL,
          market            CHAR(2) NOT NULL,
          summary           TEXT NOT NULL,
          signals_json      JSONB NOT NULL,
          sources_json      JSONB NOT NULL,
          model             TEXT NOT NULL,
          prompt_tokens     INTEGER NOT NULL,
          completion_tokens INTEGER NOT NULL,
          cost_usd          NUMERIC(12,6) NOT NULL,
          created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX idx_research_notes_lookup
          ON research_notes(tenant_id, ticker, created_at DESC);

        GRANT SELECT, INSERT ON research_notes TO saalr_app;

        ALTER TABLE research_notes ENABLE ROW LEVEL SECURITY;
        ALTER TABLE research_notes FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON research_notes
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON research_notes;")
    op.execute("DROP TABLE IF EXISTS research_notes;")
```

- [ ] **Step 2: Write the model**

Create `packages/core/saalr_core/db/models/research.py`:
```python
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


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
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    signals_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sources_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Register the model**

In `packages/core/saalr_core/db/models/__init__.py`, the current line imports the model modules. Add `research` to it (alphabetical), e.g. it becomes:
```python
from . import audit, billing, config, content, market_data, research, tenancy, trading  # noqa: F401
```
(If the current set differs, just add `research` to the existing comma-separated import; the point is that `research` is imported so `ResearchNote` registers with `Base.metadata`.)

- [ ] **Step 4: Apply the migration**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run alembic upgrade head`
Expected: applies `0008`. No error.

- [ ] **Step 5: Schema-match test + mapper smoke**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_schema_matches_models.py -q`
Expected: PASS. Columns match: note_id, tenant_id, user_id, ticker, market, summary, signals_json, sources_json, model, prompt_tokens, completion_tokens, cost_usd, created_at.
Run: `uv run python -c "import saalr_core.db.models; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('mappers OK')"`
Expected: `mappers OK`.

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/db/models/research.py
git add infra/migrations/versions/0008_research_notes.py packages/core/saalr_core/db/models/research.py packages/core/saalr_core/db/models/__init__.py
git commit -m "feat(research): research_notes RLS table + ResearchNote model (migration 0008)"
```

---

### Task 3: Research API — gating, repo, service, endpoints

**Files:**
- Create: `apps/api/saalr_api/research/__init__.py` (empty)
- Create: `apps/api/saalr_api/research/gating.py`
- Create: `apps/api/saalr_api/research/schemas.py`
- Create: `apps/api/saalr_api/research/repo.py`
- Create: `apps/api/saalr_api/research/service.py`
- Create: `apps/api/saalr_api/research/router.py`
- Modify: `apps/api/saalr_api/main.py` (include the router)
- Test: `tests/integration/test_research.py`

DB on 55432. Composes existing helpers: `apps/api/saalr_api/forecast/repo.py::load_closes`, `saalr_core.sentiment.repo.latest_sentiment`, `saalr_ml.forecast.vol_forecast`, `saalr_core.rag.qa.retrieve_context`. The chat + embedding providers are already on `app.state` from RAG-1/RAG-2.

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_research.py`:
```python
import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_content.loader import load_catalog
from saalr_core.rag.chat import StubChatProvider
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.rag.index import reindex_catalog


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
    from decimal import Decimal
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol=:s"), {"s": symbol})
        for i in range(n):
            ts = start + timedelta(days=i)
            px = Decimal(str(round(base + (i % 5) * 0.3, 4)))  # mild variation
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:s,'US','1d',:c,:c,:c,:c,1000)"""),
                {"ts": ts, "s": symbol, "c": px})


async def _build_index(app, provider):
    async with app.state.sessionmaker() as s, s.begin():
        await reindex_catalog(s, provider, load_catalog(), model=provider.model_name)


async def _premium_app(admin_engine, email):
    app = create_app()
    return app


async def test_run_produces_and_persists_note(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.chat_provider = StubChatProvider()
        app.state.embedding_provider = HashEmbeddingProvider()
        await _build_index(app, app.state.embedding_provider)
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:res1@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            r = await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["summary"] and body["model"] == "stub-chat" and body["cached"] is False
            assert body["signals"]["spot"] is not None
            assert isinstance(body["usage"]["prompt_tokens"], int)
            assert isinstance(body["cost_usd"], str)
            nid = body["note_id"]
            lst = (await c.get("/research/notes", headers=h)).json()["notes"]
            assert any(n["note_id"] == nid for n in lst)
            one = (await c.get(f"/research/notes/{nid}", headers=h)).json()
            assert one["summary"] and "signals" in one and "sources" in one


async def test_six_hour_cache_and_refresh(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.chat_provider = StubChatProvider()
        app.state.embedding_provider = HashEmbeddingProvider()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:res2@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            first = (await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)).json()
            second = (await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)).json()
            assert second["cached"] is True and second["note_id"] == first["note_id"]
            fresh = (await c.post("/research/run", json={"ticker": "AAPL", "refresh": True}, headers=h)).json()
            assert fresh["cached"] is False and fresh["note_id"] != first["note_id"]


async def test_gating_pro_and_free_402(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.chat_provider = StubChatProvider()
        async with _client(app) as c:
            hp = {"Authorization": "Bearer dev:res3@x.com"}
            await _tier(admin_engine, await _tid(c, hp), "pro")
            rp = await c.post("/research/run", json={"ticker": "AAPL"}, headers=hp)
            assert rp.status_code == 402
            assert rp.json()["detail"]["error"]["code"] == "ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM"
            hf = {"Authorization": "Bearer dev:res4@x.com"}  # free (default)
            rf = await c.post("/research/run", json={"ticker": "AAPL"}, headers=hf)
            assert rf.status_code == 402


async def test_no_bars_404(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.chat_provider = StubChatProvider()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:res5@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            r = await c.post("/research/run", json={"ticker": "ZZZZ"}, headers=h)
            assert r.status_code == 404 and r.json()["detail"]["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_no_chat_provider_503(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.chat_provider = None
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:res6@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            r = await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)
            assert r.status_code == 503 and r.json()["detail"]["error"]["code"] == "FEATURE_UNAVAILABLE"


async def test_graceful_signals_without_garch_or_sentiment(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", n=40)  # < 250 -> GARCH skipped; no sentiment row seeded
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.chat_provider = StubChatProvider()
        app.state.embedding_provider = HashEmbeddingProvider()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:res7@x.com"}
            await _tier(admin_engine, await _tid(c, h), "premium")
            body = (await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)).json()
            assert body["signals"]["vol_forecast"] is None
            assert body["signals"]["sentiment"] is None


async def test_rls_isolation(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.chat_provider = StubChatProvider()
        async with _client(app) as c:
            ha = {"Authorization": "Bearer dev:res-a@x.com"}
            await _tier(admin_engine, await _tid(c, ha), "premium")
            await c.post("/research/run", json={"ticker": "AAPL"}, headers=ha)
            hb = {"Authorization": "Bearer dev:res-b@x.com"}
            await _tier(admin_engine, await _tid(c, hb), "premium")
            assert (await c.get("/research/notes", headers=hb)).json()["notes"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run (DB env prefix): `uv run pytest tests/integration/test_research.py -q`
Expected: FAIL (no `/research/*` routes → 404/405).

- [ ] **Step 3: gating + schemas**

Create `apps/api/saalr_api/research/__init__.py` (EMPTY file).

Create `apps/api/saalr_api/research/gating.py`:
```python
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal


async def require_research_agent(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    _session, principal = ctx
    if not entitlements_for(principal.tier)["research_agent"]:
        raise HTTPException(
            status_code=402,
            detail={"error": {"code": "ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM",
                              "message": "research notes require a Premium plan"}},
        )
    yield ctx
```

Create `apps/api/saalr_api/research/schemas.py`:
```python
from __future__ import annotations

from pydantic import BaseModel


class RunRequest(BaseModel):
    ticker: str
    market: str = "US"
    refresh: bool = False
```

- [ ] **Step 4: repo**

Create `apps/api/saalr_api/research/repo.py`:
```python
from __future__ import annotations

from sqlalchemy import select

from saalr_core.db.models.research import ResearchNote
from saalr_core.ids import new_id


async def recent_note(session, ticker, market, since) -> ResearchNote | None:
    """Newest note for (ticker, market) created at/after `since` (RLS-scoped)."""
    return (await session.execute(
        select(ResearchNote)
        .where(ResearchNote.ticker == ticker, ResearchNote.market == market,
               ResearchNote.created_at >= since)
        .order_by(ResearchNote.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def insert_note(session, *, tenant_id, user_id, ticker, market, summary, signals, sources,
                      model, prompt_tokens, completion_tokens, cost_usd) -> ResearchNote:
    row = ResearchNote(
        note_id=new_id(), tenant_id=tenant_id, user_id=user_id, ticker=ticker, market=market,
        summary=summary, signals_json=signals, sources_json=sources, model=model,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cost_usd=cost_usd,
    )
    session.add(row)
    await session.flush()
    return row


async def list_notes(session, limit, cursor) -> list[ResearchNote]:
    stmt = select(ResearchNote).order_by(ResearchNote.created_at.desc(), ResearchNote.note_id.desc())
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

- [ ] **Step 5: service**

Create `apps/api/saalr_api/research/service.py`:
```python
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from saalr_core.rag.chat import ChatError
from saalr_core.rag.qa import retrieve_context
from saalr_core.research.note import ResearchInputs, build_research_prompt, estimate_cost
from saalr_core.sentiment.repo import latest_sentiment
from saalr_ml.forecast import vol_forecast

from ..forecast.repo import load_closes
from . import repo

_logger = logging.getLogger("saalr.research")
_CACHE_TTL = timedelta(hours=6)


def _out(note, *, cached: bool) -> dict:
    return {
        "note_id": str(note.note_id), "ticker": note.ticker, "market": note.market,
        "summary": note.summary, "signals": note.signals_json, "sources": note.sources_json,
        "model": note.model,
        "usage": {"prompt_tokens": note.prompt_tokens, "completion_tokens": note.completion_tokens},
        "cost_usd": str(note.cost_usd), "cached": cached, "created_at": note.created_at.isoformat(),
    }


async def gather_inputs(session, state, ticker: str, market: str) -> ResearchInputs:
    closes = await load_closes(session, ticker, market)
    if not closes:
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND",
                                            "message": "no price data for ticker"}})
    spot = closes[-1]

    # GARCH vol forecast is a best-effort enrichment: never let it fail the note.
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
        except Exception as exc:  # noqa: BLE001 - best-effort signal; degrade, never 500
            _logger.warning("garch forecast unavailable for %s: %s", ticker, exc)
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
    embed = getattr(state, "embedding_provider", None)
    if embed is not None:
        try:
            vectors = await embed.embed([f"options {ticker} implied volatility sentiment risk"])
            if len(vectors) == 1:
                hits = await retrieve_context(session, vectors[0], model=embed.model_name, k=3)
                catalog = getattr(state, "catalog", None)
                for hit in hits:
                    title = hit.module_slug
                    module = catalog.by_slug(hit.module_slug) if catalog is not None else None
                    if module is not None:
                        title = module.title
                    excerpts.append((hit.module_slug, title, hit.content))
        except Exception as exc:  # noqa: BLE001 - best-effort enrichment; degrade, never 500
            _logger.warning("content retrieval unavailable for %s: %s", ticker, exc)
            excerpts = []

    return ResearchInputs(ticker, market, spot, vol, sentiment, excerpts)


async def run_research(session, principal, state, ticker: str, market: str, refresh: bool) -> dict:
    if not refresh:
        cached = await repo.recent_note(session, ticker, market,
                                        datetime.now(timezone.utc) - _CACHE_TTL)
        if cached is not None:
            return _out(cached, cached=True)
    inputs = await gather_inputs(session, state, ticker, market)
    chat = getattr(state, "chat_provider", None)
    if chat is None:
        raise HTTPException(503, {"error": {"code": "FEATURE_UNAVAILABLE",
                                            "message": "the research assistant is not configured"}})
    system, user = build_research_prompt(inputs)
    try:
        result = await chat.complete(system, user)
    except ChatError as exc:
        _logger.warning("research chat failed for %s: %s", ticker, exc)
        raise HTTPException(502, {"error": {"code": "LLM_UNAVAILABLE",
                                            "message": "the research assistant is temporarily unavailable"}}) from exc
    signals = {"spot": inputs.spot, "vol_forecast": inputs.vol_forecast, "sentiment": inputs.sentiment}
    sources = [{"slug": slug, "title": title} for slug, title, _content in inputs.content_excerpts]
    cost = estimate_cost(chat.model_name, result.prompt_tokens, result.completion_tokens)
    note = await repo.insert_note(
        session, tenant_id=principal.tenant_id, user_id=principal.user_id, ticker=ticker,
        market=market, summary=result.text, signals=signals, sources=sources, model=chat.model_name,
        prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens, cost_usd=cost,
    )
    return _out(note, cached=False)
```

- [ ] **Step 6: router**

Create `apps/api/saalr_api/research/router.py`:
```python
from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from . import repo, service
from .gating import require_research_agent
from .schemas import RunRequest

router = APIRouter(prefix="/research", tags=["research"])


def _note_row(note) -> dict:
    return {"note_id": str(note.note_id), "ticker": note.ticker, "market": note.market,
            "model": note.model, "cost_usd": str(note.cost_usd),
            "created_at": note.created_at.isoformat()}


@router.post("/run")
async def run(body: RunRequest, request: Request,
              ctx: tuple[AsyncSession, Principal] = Depends(require_research_agent)) -> dict:
    session, principal = ctx
    ticker = body.ticker.strip().upper()
    if not ticker or not ticker.isalpha():
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "invalid ticker"}})
    if body.market not in ("US",):
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "unsupported market"}})
    return await service.run_research(session, principal, request.app.state, ticker, body.market,
                                      body.refresh)


@router.get("/notes")
async def list_notes(limit: int = Query(20, le=100), cursor: str | None = None,
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
    rows = await repo.list_notes(session, limit, decoded)
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
    return {**_note_row(note), "summary": note.summary, "signals": note.signals_json,
            "sources": note.sources_json,
            "usage": {"prompt_tokens": note.prompt_tokens, "completion_tokens": note.completion_tokens}}
```

- [ ] **Step 7: Wire the router into `main.py`**

In `apps/api/saalr_api/main.py`, add the import alongside the other feature routers (e.g. after `from .content.router import router as content_router`):
```python
from .research.router import router as research_router
```
Add the registration alongside the other `app.include_router(...)` calls:
```python
    app.include_router(research_router)
```

- [ ] **Step 8: Run the new suite + regression**

Run (DB env prefix): `uv run pytest tests/integration/test_research.py -q`
Expected: PASS (7 passed).
Run (DB env prefix): `uv run pytest tests/integration/test_content.py tests/integration/test_schema_matches_models.py -q`
Expected: PASS (no regression).

- [ ] **Step 9: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/research apps/api/saalr_api/main.py tests/integration/test_research.py
git add apps/api/saalr_api/research apps/api/saalr_api/main.py tests/integration/test_research.py
git commit -m "feat(research): POST /research/run + /research/notes — premium research-note core"
```

---

## Final verification (after all tasks)

- [ ] Core (pure): `uv run pytest packages/core/tests/test_research_note.py -q` — 3 passed.
- [ ] DB suites (DB env prefix): `uv run pytest tests/integration/test_research.py tests/integration/test_schema_matches_models.py tests/integration/test_content.py -q` — all green.
- [ ] Isolation: `uv sync && uv run python -c "import importlib.util as u; print('openai', 'present' if u.find_spec('openai') else 'ABSENT')"` — `openai ABSENT`.
- [ ] Lint: `uvx ruff check packages/core/saalr_core/research apps/api/saalr_api/research apps/api/saalr_api/main.py` — clean.
- [ ] Final code-review subagent over the whole slice diff.

## Self-review notes
- **No API key needed to test:** `StubChatProvider` + `HashEmbeddingProvider` make the whole `/research/run` pipeline deterministic. The real OpenAI provider is reused from RAG-2 (lazy `openai`).
- **Graceful degradation (deliberate broad `except`):** the GARCH and content signals are best-effort enrichments — `gather_inputs` catches broadly (with a `_logger.warning`) and degrades to `null`/`[]`, so a research note NEVER 500s because a secondary signal choked. The only hard failure is no price bars → 404. `# noqa: BLE001` documents the intentional broad catch.
- **6h cache** keys on `(tenant, ticker, market)` newest-within-6h (RLS-scoped); `refresh=true` bypasses; covered by `test_six_hour_cache_and_refresh`.
- **Premium gate** via `require_research_agent` (reuses the `get_principal` → entitlement pattern of `require_ml_forecast`); pro AND free → 402.
- **Signature consistency:** `ResearchInputs(ticker, market, spot, vol_forecast, sentiment, content_excerpts)`, `build_research_prompt(inputs)`, `estimate_cost(model, prompt_tokens, completion_tokens)` match between Task 1 and Task 3's calls; `recent_note`/`insert_note`/`list_notes`/`get_note` match between Task 3's repo and service/router. The `_premium_app` helper in the test file is unused — remove it before committing if ruff flags it (or leave it; it is harmless).
