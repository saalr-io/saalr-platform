# RA-3a — LLM gateway + cost ledger + budgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A provider-agnostic chat gateway (OpenAI → Anthropic ordered fallback), a per-tenant `llm_usage` cost ledger, and a hard per-tenant monthly budget cap — so RA-2's worker gains fallback + cost control, and RA-3b's multi-agent graph has a metered substrate.

**Architecture:** New `saalr_core/llm/` package (gateway, cost+budget pure helpers, ledger repo). The base chat types stay in `saalr_core/rag/chat.py`; the gateway wraps them. `llm_usage` is a new RLS tenant table (migration 0010). Budget is enforced fail-fast at API enqueue and authoritatively in the worker (phase-1 check, phase-3 record), preserving RA-2's 3-phase worker shape.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Postgres + RLS, Redis, pytest. `openai` + `anthropic` are optional extras (only the worker env installs them).

**Spec:** `docs/superpowers/specs/2026-06-03-llm-gateway-budgets-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- DB tests need Postgres on **55432**, Redis on **6379**. Prefix:
  `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <args>`
- Error shape: `HTTPException(status, {"error": {"code", "message"}})` → `resp.json()["detail"]["error"]["code"]`. No global exception handler.
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore`, `.env`, `uv.lock` (except the diff-verified `uv sync` workspace change in Task 4), or `tools/`.

---

### Task 1: `llm/cost.py` — cost rates + budget helpers (pure)

Move the canonical `estimate_cost` + rate table into `saalr_core/llm/cost.py` (extended with Anthropic), add the pure budget helpers, and re-export `estimate_cost` from `research/note.py`.

**Files:**
- Create: `packages/core/saalr_core/llm/__init__.py` (empty)
- Create: `packages/core/saalr_core/llm/cost.py`
- Modify: `packages/core/saalr_core/research/note.py`
- Test: `packages/core/tests/test_llm_cost.py`
- Test (existing, must still pass): `packages/core/tests/test_research_note.py`

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_llm_cost.py`:
```python
from datetime import datetime, timezone
from decimal import Decimal

from saalr_core.llm.cost import (
    BudgetExceeded,
    budget_exceeded,
    estimate_cost,
    month_start,
    monthly_cap,
)


def test_estimate_cost_rates():
    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == Decimal("0.750000")
    assert estimate_cost("claude-3-5-haiku-latest", 1_000_000, 1_000_000) == Decimal("4.800000")
    assert estimate_cost("stub-chat", 1000, 1000) == Decimal("0.000000")
    assert estimate_cost("unknown", 1000, 1000) == Decimal("0.000000")


def test_budget_exceeded_boundary():
    assert budget_exceeded(Decimal("10"), Decimal("10")) is True   # spent == cap -> over
    assert budget_exceeded(Decimal("9.99"), Decimal("10")) is False
    assert issubclass(BudgetExceeded, Exception)


def test_month_start_zeroes_day_and_time():
    ms = month_start(datetime(2026, 6, 17, 13, 45, 9, 123, tzinfo=timezone.utc))
    assert ms == datetime(2026, 6, 1, 0, 0, 0, 0, tzinfo=timezone.utc)


def test_monthly_cap_reads_settings():
    class _S:
        llm_monthly_budget_usd = 10.0
    assert monthly_cap(_S()) == Decimal("10.0")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_llm_cost.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.llm.cost`.

- [ ] **Step 3: Implement**

Create `packages/core/saalr_core/llm/__init__.py` (EMPTY file).

Create `packages/core/saalr_core/llm/cost.py`:
```python
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

# USD per 1,000,000 tokens (prompt, completion). Estimates; the real bill is the source of truth.
_RATES: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "claude-3-5-haiku-latest": (Decimal("0.80"), Decimal("4.00")),
    "stub-chat": (Decimal(0), Decimal(0)),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Estimated USD cost for a completion. Unknown model -> 0. Quantized to 6 dp."""
    rate_p, rate_c = _RATES.get(model, (Decimal(0), Decimal(0)))
    cost = (Decimal(prompt_tokens) / Decimal(1_000_000) * rate_p
            + Decimal(completion_tokens) / Decimal(1_000_000) * rate_c)
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


class BudgetExceeded(Exception):
    """A tenant's month-to-date LLM spend has reached the monthly cap."""


def month_start(now: datetime) -> datetime:
    """First instant of `now`'s calendar month (preserves tzinfo)."""
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def monthly_cap(settings) -> Decimal:
    return Decimal(str(settings.llm_monthly_budget_usd))


def budget_exceeded(spent: Decimal, cap: Decimal) -> bool:
    return spent >= cap
```

- [ ] **Step 4: Re-export from `research/note.py`**

In `packages/core/saalr_core/research/note.py`: delete the `_RATES` table and the `estimate_cost` function, delete the now-unused `from decimal import ROUND_HALF_UP, Decimal` line, and add a re-export import near the top (after `from dataclasses import dataclass`):
```python
from saalr_core.llm.cost import estimate_cost  # noqa: F401  (canonical home is llm.cost)
```
Leave `ResearchInputs`, `_SYSTEM`, and `build_research_prompt` exactly as they are. (They don't use `Decimal`.)

- [ ] **Step 5: Run both tests**

Run: `uv run pytest packages/core/tests/test_llm_cost.py packages/core/tests/test_research_note.py -q`
Expected: PASS (the existing `test_estimate_cost_rate_math` in `test_research_note.py` still passes via the re-export).

- [ ] **Step 6: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/llm packages/core/saalr_core/research/note.py packages/core/tests/test_llm_cost.py
git add packages/core/saalr_core/llm/__init__.py packages/core/saalr_core/llm/cost.py packages/core/saalr_core/research/note.py packages/core/tests/test_llm_cost.py
git commit -m "feat(llm): cost rate table + budget helpers in saalr_core.llm.cost"
```

---

### Task 2: ChatGateway + Anthropic provider + config (pure/stub)

**Files:**
- Modify: `packages/core/saalr_core/rag/chat.py` (ChatResult fields + provider `name`s)
- Create: `packages/core/saalr_core/llm/gateway.py`
- Modify: `packages/core/saalr_core/config.py`
- Modify: `packages/core/pyproject.toml` (anthropic extra)
- Test: `packages/core/tests/test_llm_gateway.py`

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_llm_gateway.py`:
```python
import pytest

from saalr_core.llm.gateway import ChatGateway
from saalr_core.rag.chat import ChatError, ChatResult, StubChatProvider


class _Fail:
    name = "fail"
    model_name = "fail-model"

    async def complete(self, system, user):
        raise ChatError("down")


async def test_single_provider_stamps_provider_and_model():
    g = ChatGateway([StubChatProvider()])
    r = await g.complete("sys", "user")
    assert r.provider == "stub" and r.model == "stub-chat"
    assert r.text


async def test_falls_through_to_next_on_chat_error():
    g = ChatGateway([_Fail(), StubChatProvider()])
    r = await g.complete("sys", "user")
    assert r.provider == "stub"  # the stub won after the first failed


async def test_all_providers_exhausted_raises():
    g = ChatGateway([_Fail(), _Fail()])
    with pytest.raises(ChatError):
        await g.complete("sys", "user")


def test_empty_gateway_rejected():
    with pytest.raises(ValueError):
        ChatGateway([])
```
(These are async; the core test suite runs under `asyncio_mode = "auto"`.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_llm_gateway.py -q`
Expected: FAIL (`saalr_core.llm.gateway` missing / `ChatResult` has no `provider`).

- [ ] **Step 3: Extend `rag/chat.py`**

In `packages/core/saalr_core/rag/chat.py`:
- Change the `ChatResult` dataclass to add two optional fields:
```python
@dataclass(frozen=True)
class ChatResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    provider: str | None = None
    model: str | None = None
```
- Add `name = "stub"` as a class attribute on `StubChatProvider` (next to `model_name = "stub-chat"`).
- Add `name = "openai"` as a class attribute on `OpenAIChatProvider` (inside the class body, e.g. right after the docstring, before `__init__`).
- Add `name: str` to the `ChatProvider` Protocol (after `model_name: str`).

- [ ] **Step 4: Create the gateway**

Create `packages/core/saalr_core/llm/gateway.py`:
```python
from __future__ import annotations

from dataclasses import replace

from saalr_core.rag.chat import ChatError, ChatProvider, ChatResult, OpenAIChatProvider


class AnthropicChatProvider:
    """Anthropic chat. `anthropic` is imported lazily, so importing this module needs no SDK."""

    name = "anthropic"

    def __init__(self, api_key: str, model_name: str = "claude-3-5-haiku-latest",
                 max_tokens: int = 1024) -> None:
        self._api_key = api_key
        self.model_name = model_name
        self._max_tokens = max_tokens
        self._client = None  # lazily built once

    async def complete(self, system: str, user: str) -> ChatResult:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ChatError("anthropic not installed (pip install anthropic)") from exc
        if self._client is None:
            self._client = AsyncAnthropic(api_key=self._api_key)
        try:
            resp = await self._client.messages.create(
                model=self.model_name, max_tokens=self._max_tokens,
                system=system, messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            # Keep the message generic so a provider response body never leaks (incl. the key).
            raise ChatError(f"anthropic chat failed ({type(exc).__name__})") from exc
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        )
        usage = resp.usage
        return ChatResult(
            text,
            usage.input_tokens if usage else 0,
            usage.output_tokens if usage else 0,
        )


class ChatGateway:
    """Ordered fallback over chat providers. Implements the ChatProvider Protocol so it is a
    drop-in wherever a single provider is expected. Tries each provider in turn; on ChatError it
    falls to the next; the first success is returned stamped with the winning provider + model."""

    name = "gateway"

    def __init__(self, providers: list[ChatProvider]) -> None:
        if not providers:
            raise ValueError("ChatGateway requires at least one provider")
        self.providers = providers

    @property
    def model_name(self) -> str:
        return self.providers[0].model_name  # nominal/primary

    async def complete(self, system: str, user: str) -> ChatResult:
        errors: list[str] = []
        for p in self.providers:
            try:
                result = await p.complete(system, user)
            except ChatError as exc:
                errors.append(f"{getattr(p, 'name', '?')}: {exc}")
                continue
            return replace(result, provider=getattr(p, "name", None), model=p.model_name)
        raise ChatError("all providers exhausted: " + "; ".join(errors))


def make_chat_gateway(settings) -> ChatGateway | None:
    """Assemble [OpenAI, Anthropic] in order from whatever keys are configured, else None."""
    providers: list[ChatProvider] = []
    if settings.openai_api_key:
        providers.append(OpenAIChatProvider(settings.openai_api_key, settings.chat_model))
    if settings.anthropic_api_key:
        providers.append(AnthropicChatProvider(settings.anthropic_api_key, settings.anthropic_model))
    if not providers:
        return None
    return ChatGateway(providers)
```

- [ ] **Step 5: Config + extra**

In `packages/core/saalr_core/config.py`, in the `Settings` class after the existing `chat_model` line, add:
```python
    # LLM gateway + budgets (RA-3a)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-haiku-latest"
    llm_monthly_budget_usd: float = 10.0
```

In `packages/core/pyproject.toml`, extend the optional-dependencies:
```toml
[project.optional-dependencies]
openai = ["openai>=1.40"]
anthropic = ["anthropic>=0.40"]
```

- [ ] **Step 6: Run the test + a config smoke**

Run: `uv run pytest packages/core/tests/test_llm_gateway.py -q`
Expected: PASS (4 passed).
Run (config loads with the new fields): `uv run python -c "from saalr_core.config import get_settings; s=get_settings(); print(s.anthropic_model, s.llm_monthly_budget_usd)"`
Expected: prints `claude-3-5-haiku-latest 10.0` (or your `.env` overrides). No error.
Run (RAG-2 regression — `ChatResult`/StubChatProvider still satisfy `/content/ask`): `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_rag_ask.py -q`
Expected: PASS (the new optional `ChatResult` fields are backward compatible).

- [ ] **Step 7: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/llm/gateway.py packages/core/saalr_core/rag/chat.py packages/core/saalr_core/config.py packages/core/tests/test_llm_gateway.py
git add packages/core/saalr_core/llm/gateway.py packages/core/saalr_core/rag/chat.py packages/core/saalr_core/config.py packages/core/pyproject.toml packages/core/tests/test_llm_gateway.py
git commit -m "feat(llm): ChatGateway fallback + AnthropicChatProvider + config"
```

---

### Task 3: `llm_usage` ledger — migration 0010 + model + repo

**Files:**
- Create: `infra/migrations/versions/0010_llm_usage.py`
- Create: `packages/core/saalr_core/db/models/llm.py`
- Modify: `packages/core/saalr_core/db/models/__init__.py`
- Create: `packages/core/saalr_core/llm/repo.py`
- Test: `tests/integration/test_llm_usage.py`
- Test (existing, must pass): `tests/integration/test_schema_matches_models.py`

DB on 55432. `llm_usage` is an RLS tenant table mirroring `research_notes`'s policy idiom.

- [ ] **Step 1: Write the migration**

Create `infra/migrations/versions/0010_llm_usage.py`:
```python
"""llm_usage per-tenant LLM cost ledger (RA-3a)

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-03
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE llm_usage (
          usage_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id           UUID NOT NULL REFERENCES users(user_id),
          provider          TEXT NOT NULL,
          model             TEXT NOT NULL,
          prompt_tokens     INTEGER NOT NULL,
          completion_tokens INTEGER NOT NULL,
          cost_usd          NUMERIC(12,6) NOT NULL,
          purpose           TEXT NOT NULL,
          note_id           UUID,
          created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX idx_llm_usage_tenant_created ON llm_usage(tenant_id, created_at DESC);

        GRANT SELECT, INSERT ON llm_usage TO saalr_app;

        ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;
        ALTER TABLE llm_usage FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON llm_usage
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON llm_usage;")
    op.execute("DROP TABLE IF EXISTS llm_usage;")
```
CONFIRM before writing: the current head is `0009` (find the file whose `revision = "0009"`; nothing should have `down_revision = "0009"` yet). If not, STOP and report BLOCKED.

- [ ] **Step 2: Write the model**

Create `packages/core/saalr_core/db/models/llm.py`:
```python
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    usage_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    note_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Register the model**

In `packages/core/saalr_core/db/models/__init__.py`, add `llm` to the import (alphabetical), so the line becomes:
```python
from . import audit, billing, config, content, llm, market_data, research, tenancy, trading  # noqa: F401
```

- [ ] **Step 4: Write the repo**

Create `packages/core/saalr_core/llm/repo.py`:
```python
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from saalr_core.db.models.llm import LlmUsage
from saalr_core.ids import new_id


async def record_usage(session, *, tenant_id, user_id, provider, model, prompt_tokens,
                       completion_tokens, cost_usd, purpose, note_id=None) -> None:
    session.add(LlmUsage(
        usage_id=new_id(), tenant_id=tenant_id, user_id=user_id, provider=provider, model=model,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cost_usd=cost_usd,
        purpose=purpose, note_id=note_id,
    ))
    await session.flush()


async def month_to_date_cost(session, tenant_id, since) -> Decimal:
    total = (await session.execute(
        select(func.coalesce(func.sum(LlmUsage.cost_usd), 0)).where(
            LlmUsage.tenant_id == tenant_id, LlmUsage.created_at >= since)
    )).scalar_one()
    return Decimal(total)
```

- [ ] **Step 5: Write the failing integration test**

Create `tests/integration/test_llm_usage.py`:
```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import httpx

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _me(c, h):
    body = (await c.get("/me", headers=h)).json()
    return UUID(body["tenant"]["id"]), UUID(body["user"]["id"])


async def test_record_and_month_to_date_sum(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:llm1@x.com"}
            tid, uid = await _me(c, h)
            async with tenant_session(app.state.sessionmaker, tid) as s:
                await llm_repo.record_usage(s, tenant_id=tid, user_id=uid, provider="stub",
                                            model="stub-chat", prompt_tokens=10, completion_tokens=5,
                                            cost_usd=Decimal("0.30"), purpose="research_note")
                await llm_repo.record_usage(s, tenant_id=tid, user_id=uid, provider="openai",
                                            model="gpt-4o-mini", prompt_tokens=10, completion_tokens=5,
                                            cost_usd=Decimal("0.45"), purpose="research_note")
            now = datetime.now(timezone.utc)
            async with tenant_session(app.state.sessionmaker, tid) as s:
                mtd = await llm_repo.month_to_date_cost(s, tid, now - timedelta(days=400))
                assert mtd == Decimal("0.750000")
                future = await llm_repo.month_to_date_cost(s, tid, now + timedelta(days=1))
                assert future == Decimal("0")
```

- [ ] **Step 6: Apply migration + run tests**

Run (DB env prefix): `uv run alembic upgrade head`
Expected: applies `0010`, no error.
Run (DB env prefix): `uv run pytest tests/integration/test_schema_matches_models.py tests/integration/test_llm_usage.py -q`
Expected: PASS. (`llm_usage` columns match the model.)
Run: `uv run python -c "import saalr_core.db.models; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('mappers OK')"`
Expected: `mappers OK`.

- [ ] **Step 7: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/db/models/llm.py packages/core/saalr_core/llm/repo.py tests/integration/test_llm_usage.py
git add infra/migrations/versions/0010_llm_usage.py packages/core/saalr_core/db/models/llm.py packages/core/saalr_core/db/models/__init__.py packages/core/saalr_core/llm/repo.py tests/integration/test_llm_usage.py
git commit -m "feat(llm): llm_usage cost ledger (migration 0010) + repo"
```

---

### Task 4: Worker — budget check + cost recording + gateway

Thread the budget cap + ledger into the research-agent worker, and build the gateway (OpenAI+Anthropic) instead of a single provider.

**Files:**
- Modify: `apps/research-agent/research_agent/service.py`
- Modify: `apps/research-agent/research_agent/consumer.py`
- Modify: `apps/research-agent/research_agent/cli.py`
- Modify: `apps/research-agent/pyproject.toml`
- Test: `tests/integration/test_research_worker.py` (rewrite)

> **Worker-test invocation:** as in RA-2, run via `--package saalr-research-agent` (installs openai + anthropic into the env; the default gate ignores this file):
> `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q`

- [ ] **Step 1: Rewrite the e2e tests**

Replace `tests/integration/test_research_worker.py` ENTIRELY with:
```python
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text

from research_agent.consumer import run_consumer
from saalr_api.main import create_app
from saalr_content.loader import load_catalog
from saalr_core.db.session import create_engine, create_sessionmaker, tenant_session
from saalr_core.llm import repo as llm_repo
from saalr_core.llm.gateway import ChatGateway
from saalr_core.rag.chat import ChatError, StubChatProvider
from saalr_core.rag.embeddings import HashEmbeddingProvider

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_CAP = Decimal("10")


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


async def _seed_bars(admin_engine, symbol, n=40, base=50.0):
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


class _FailChat:
    name = "fail"
    model_name = "fail-model"

    async def complete(self, system, user):
        raise ChatError("boom")


async def _run_worker_once(*, chat, cap=_CAP):
    engine = create_engine(os.environ["APP_DATABASE_URL"])
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await run_consumer(redis, create_sessionmaker(engine), "test-research",
                           chat_provider=chat, embedding_provider=HashEmbeddingProvider(),
                           catalog=load_catalog(), cap=cap, block_ms=1000, count=10, once=True)
    finally:
        await redis.aclose()
        await engine.dispose()


async def _post(c, h, ticker="AAPL"):
    return (await c.post("/research/run", json={"ticker": ticker}, headers=h)).json()["poll_url"]


async def test_e2e_succeeds_and_records_usage(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw1@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            poll = await _post(c, h)
            await _run_worker_once(chat=ChatGateway([StubChatProvider()]))
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "succeeded", done
            assert done["model"] == "stub-chat"
            # a usage row was recorded, stamped with the gateway-resolved provider + model
            async with admin_engine.begin() as conn:
                row = (await conn.execute(
                    text("SELECT provider, model, purpose FROM llm_usage WHERE tenant_id=:t"),
                    {"t": str(tid)})).first()
            assert row is not None
            assert row.provider == "stub" and row.model == "stub-chat"
            assert row.purpose == "research_note"


async def test_e2e_fallback_to_second_provider(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw2@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            poll = await _post(c, h)
            await _run_worker_once(chat=ChatGateway([_FailChat(), StubChatProvider()]))
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "succeeded"
            assert done["model"] == "stub-chat"


async def test_e2e_budget_exceeded_fails(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw3@x.com"}
            tid, uid = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            async with tenant_session(app.state.sessionmaker, tid) as s:
                await llm_repo.record_usage(s, tenant_id=tid, user_id=uid, provider="openai",
                                            model="gpt-4o-mini", prompt_tokens=1, completion_tokens=1,
                                            cost_usd=Decimal("11"), purpose="research_note")
            poll = await _post(c, h)
            await _run_worker_once(chat=ChatGateway([StubChatProvider()]))
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "failed"
            assert done["error"]["code"] == "RESEARCH_BUDGET_EXCEEDED"


async def test_e2e_graceful_degradation(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw4@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            poll = await _post(c, h)
            await _run_worker_once(chat=ChatGateway([StubChatProvider()]))
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "succeeded"
            assert done["signals"]["vol_forecast"] is None
            assert done["signals"]["sentiment"] is None


async def test_e2e_no_bars_failed(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw5@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            poll = await _post(c, h, ticker="ZZZZ")
            await _run_worker_once(chat=ChatGateway([StubChatProvider()]))
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "failed"
            assert done["error"]["code"] == "RESEARCH_NO_PRICE_DATA"


async def test_e2e_all_providers_down_failed(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw6@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            poll = await _post(c, h)
            await _run_worker_once(chat=ChatGateway([_FailChat()]))
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "failed"
            assert done["error"]["code"] == "RESEARCH_LLM_UNAVAILABLE"
```

- [ ] **Step 2: Run to verify it fails**

Run (DB+Redis env prefix): `uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q`
Expected: FAIL — `run_consumer` got an unexpected `cap` kwarg (and budget/usage not wired).

- [ ] **Step 3: Update the worker pyproject**

In `apps/research-agent/pyproject.toml`, change the core dep to include the anthropic extra:
```toml
dependencies = [
  "saalr-core[openai,anthropic]",
  "saalr-ml",
  "saalr-content",
  "sqlalchemy>=2.0",
  "asyncpg>=0.29",
]
```
(Leave the rest of the file unchanged.)

- [ ] **Step 4: Thread budget + ledger into `service.py`**

In `apps/research-agent/research_agent/service.py`:
- Update the imports block to add datetime + the llm helpers, and pull `estimate_cost` from `llm.cost` (keep `ResearchInputs`, `build_research_prompt` from `research.note`):
```python
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo
from saalr_core.llm.cost import BudgetExceeded, budget_exceeded, estimate_cost, month_start
from saalr_core.marketdata.bars import load_closes
from saalr_core.rag.chat import ChatError
from saalr_core.rag.embeddings import EmbeddingError
from saalr_core.rag.qa import retrieve_context
from saalr_core.research import repo
from saalr_core.research.note import ResearchInputs, build_research_prompt
from saalr_core.sentiment.repo import latest_sentiment
from saalr_ml.forecast import vol_forecast
```
- `gather_inputs` is UNCHANGED.
- Replace `run_research_job` with the cap-aware version:
```python
async def run_research_job(sessionmaker, tenant_id: UUID, note_id: UUID, *,
                           chat_provider, embedding_provider, catalog, cap: Decimal) -> dict:
    """Generate the note for a queued run. 3 phases, each isolating its failure mode.

    A re-delivered job whose row is already succeeded/failed is a no-op (idempotent)."""
    # Phase 1 — load + budget check + mark running.
    try:
        async with tenant_session(sessionmaker, tenant_id) as session:
            note = await repo.get_note(session, note_id)
            if note is None:
                return {"status": "missing"}
            if note.status in ("succeeded", "failed"):
                return {"status": note.status}
            spent = await llm_repo.month_to_date_cost(
                session, tenant_id, month_start(datetime.now(timezone.utc)))
            if budget_exceeded(spent, cap):
                raise BudgetExceeded(f"month-to-date {spent} >= cap {cap}")
            ticker, market, user_id = note.ticker, note.market, note.user_id
            await repo.mark_running(session, note_id)
    except BudgetExceeded as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_BUDGET_EXCEEDED", exc)
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

    # Phase 3 — persist success + record the LLM cost (one transaction).
    signals = {"spot": inputs.spot, "vol_forecast": inputs.vol_forecast, "sentiment": inputs.sentiment}
    sources = [{"slug": slug, "title": title} for slug, title, _c in inputs.content_excerpts]
    model = result.model or chat_provider.model_name
    provider = result.provider or getattr(chat_provider, "name", "unknown")
    cost = estimate_cost(model, result.prompt_tokens, result.completion_tokens)
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_succeeded(
            session, note_id, summary=result.text, signals=signals, sources=sources,
            model=model, prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens, cost_usd=cost)
        await llm_repo.record_usage(
            session, tenant_id=tenant_id, user_id=user_id, provider=provider, model=model,
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
            cost_usd=cost, purpose="research_note", note_id=note_id)
    return {"status": "succeeded"}
```
- `_fail` is UNCHANGED.

- [ ] **Step 5: Thread `cap` through `consumer.py`**

In `apps/research-agent/research_agent/consumer.py`, add `cap` to both functions:
```python
async def _process(redis, sessionmaker, job, *, chat_provider, embedding_provider, catalog, cap) -> None:
    try:
        await run_research_job(
            sessionmaker, job.tenant_id, job.note_id,
            chat_provider=chat_provider, embedding_provider=embedding_provider,
            catalog=catalog, cap=cap)
    except Exception:  # noqa: BLE001 - poison guard: run_research_job persists failures itself
        log.exception("research job %s failed unexpectedly", job.note_id)
    finally:
        await ack(redis, job.msg_id)


async def run_consumer(redis, sessionmaker, consumer: str, *, chat_provider, embedding_provider,
                       catalog, cap, block_ms: int = 5000, count: int = 10, once: bool = False,
                       claim_min_idle_ms: int = 60_000) -> None:
    await ensure_group(redis)
    for job in await claim_stale(redis, consumer, claim_min_idle_ms, count):
        await _process(redis, sessionmaker, job, chat_provider=chat_provider,
                       embedding_provider=embedding_provider, catalog=catalog, cap=cap)
    while True:
        for job in await consume_batch(redis, consumer, block_ms, count):
            await _process(redis, sessionmaker, job, chat_provider=chat_provider,
                           embedding_provider=embedding_provider, catalog=catalog, cap=cap)
        if once:
            return
```

- [ ] **Step 6: Build the gateway + cap in `cli.py`**

In `apps/research-agent/research_agent/cli.py`, update `_cmd_consume` to use the gateway + cap (replace the lazy imports + the `run_consumer` call):
```python
async def _cmd_consume(args) -> None:
    # lazy imports keep build_parser light
    from saalr_content.loader import load_catalog
    from saalr_core.llm.cost import monthly_cap
    from saalr_core.llm.gateway import make_chat_gateway
    from saalr_core.rag.embeddings import make_embedding_provider

    from .consumer import run_consumer

    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    consumer = args.consumer or f"research-{socket.gethostname()}"
    try:
        await run_consumer(
            redis, create_sessionmaker(engine), consumer,
            chat_provider=make_chat_gateway(settings),
            embedding_provider=make_embedding_provider(settings),
            catalog=load_catalog(),
            cap=monthly_cap(settings),
            block_ms=args.block_ms, count=args.count, once=args.once,
        )
    finally:
        await redis.aclose()
        await engine.dispose()
```

- [ ] **Step 7: Run the e2e suite**

Run (DB+Redis env prefix): `uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q`
Expected: PASS (6 passed). If a test fails, read the polled JSON + worker logs; do NOT weaken assertions.

- [ ] **Step 8: Lint + commit**
```bash
uvx ruff check apps/research-agent/research_agent tests/integration/test_research_worker.py
git add apps/research-agent/pyproject.toml apps/research-agent/research_agent tests/integration/test_research_worker.py
git diff uv.lock | head -40   # the --package run added anthropic to the lock; diff-verify additive-only
git add uv.lock   # only if the diff is additive (anthropic + saalr-research-agent deps)
git commit -m "feat(research): worker budget guard + LLM cost recording via gateway (RA-3a)"
```

- [ ] **Step 9: Restore the lean env + isolation check**

Run: `uv sync`
Then: `uv run python -c "import importlib.util as u; print('openai', bool(u.find_spec('openai')), 'anthropic', bool(u.find_spec('anthropic')))"`
Expected: `openai False anthropic False` (the default env has neither; only `--package saalr-research-agent` pulls them in).

---

### Task 5: API budget pre-check

Add the fail-fast budget check to the enqueue path.

**Files:**
- Modify: `apps/api/saalr_api/research/service.py`
- Modify: `apps/api/saalr_api/research/router.py`
- Modify: `apps/api/saalr_api/main.py`
- Modify: `tests/integration/conftest.py` (truncate `llm_usage`)
- Modify: `tests/integration/test_research.py` (add the 402 test)

- [ ] **Step 1: Write the failing test**

Append this test to `tests/integration/test_research.py` (it already imports `os`, `Decimal`, `UUID`, `tenant_session`, `rrepo`, `_client`, `_tier`, `_me`, `_clean_stream`; add the `llm_repo` import at the top of the file: `from saalr_core.llm import repo as llm_repo`):
```python
async def test_budget_pre_check_402(app_sessionmaker, admin_engine):
    await _clean_stream()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rar-budget@x.com"}
            tid, uid = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            async with tenant_session(app.state.sessionmaker, tid) as s:
                await llm_repo.record_usage(s, tenant_id=tid, user_id=uid, provider="openai",
                                            model="gpt-4o-mini", prompt_tokens=1, completion_tokens=1,
                                            cost_usd=Decimal("11"), purpose="research_note")
            r = await c.post("/research/run", json={"ticker": "AAPL"}, headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "RESEARCH_BUDGET_EXCEEDED"
```

- [ ] **Step 2: Run to verify it fails**

Run (DB+Redis env prefix): `uv run pytest tests/integration/test_research.py::test_budget_pre_check_402 -q`
Expected: FAIL — currently returns 202 (no budget check yet).

- [ ] **Step 3: Add the budget pre-check to the service**

In `apps/api/saalr_api/research/service.py`:
- Add imports at the top (next to the existing `from datetime import datetime, timedelta, timezone`):
```python
from decimal import Decimal

from saalr_core.llm import repo as llm_repo
from saalr_core.llm.cost import budget_exceeded, month_start
```
- Change the `run_research` signature to accept `cap` and add the check after the daily rate-limit guard, before the row is created:
```python
async def run_research(session, principal, redis, sessionmaker, cap: Decimal, ticker: str,
                       market: str, refresh: bool) -> dict:
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

    spent = await llm_repo.month_to_date_cost(
        session, principal.tenant_id, month_start(datetime.now(timezone.utc)))
    if budget_exceeded(spent, cap):
        raise HTTPException(402, {"error": {"code": "RESEARCH_BUDGET_EXCEEDED",
                                            "message": "monthly research budget reached"}})

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
(The rest of `service.py` — `_out`, `_accepted`, `_utc_midnight`, the module constants — is unchanged.)

- [ ] **Step 4: Pass the cap from the router**

In `apps/api/saalr_api/research/router.py`:
- Add the budget code to `_ERROR_MESSAGES`:
```python
_ERROR_MESSAGES = {
    "RESEARCH_NO_PRICE_DATA": "no price data for ticker",
    "RESEARCH_LLM_UNAVAILABLE": "the research assistant is temporarily unavailable",
    "RESEARCH_GENERATION_FAILED": "research generation failed",
    "RESEARCH_BUDGET_EXCEEDED": "monthly research budget reached",
}
```
- In the `run` handler, pass the cap from app.state into the service call:
```python
    result = await service.run_research(
        session, principal, request.app.state.redis, request.app.state.sessionmaker,
        request.app.state.llm_budget_cap, ticker, body.market, body.refresh)
```

- [ ] **Step 5: Set the cap on `app.state`**

In `apps/api/saalr_api/main.py`:
- Add the import next to the other `saalr_core` imports:
```python
from saalr_core.llm.cost import monthly_cap
```
- In the lifespan, after `app.state.chat_provider = make_chat_provider(settings)`:
```python
        app.state.llm_budget_cap = monthly_cap(settings)
```

- [ ] **Step 6: Truncate `llm_usage` between tests**

In `tests/integration/conftest.py`, add `"llm_usage"` to `TENANT_TABLES` (just before `"research_notes"`).

- [ ] **Step 7: Run the new test + RA-2 regression**

Run (DB+Redis env prefix): `uv run pytest tests/integration/test_research.py -q`
Expected: PASS (9 passed — the 8 RA-2 tests still pass with 0 seeded spend, plus the new 402 test).

- [ ] **Step 8: Lint + commit**
```bash
uvx ruff check apps/api/saalr_api/research/service.py apps/api/saalr_api/research/router.py apps/api/saalr_api/main.py tests/integration/test_research.py tests/integration/conftest.py
git add apps/api/saalr_api/research/service.py apps/api/saalr_api/research/router.py apps/api/saalr_api/main.py tests/integration/conftest.py tests/integration/test_research.py
git commit -m "feat(research): fail-fast monthly budget pre-check at enqueue (RA-3a)"
```

---

### Task 6: Runbook update

**Files:**
- Modify: `docs/runbooks/research-agent.md`

- [ ] **Step 1: Add the providers & budget section**

Append to `docs/runbooks/research-agent.md`:
```markdown

## Providers & budget (RA-3a)

The worker generates via a **ChatGateway** with ordered fallback: OpenAI →
Anthropic. `make_chat_gateway(settings)` includes a provider only if its key is
set, so with just `OPENAI_API_KEY` the gateway is OpenAI-only; add
`ANTHROPIC_API_KEY` (+ `ANTHROPIC_MODEL`, default `claude-3-5-haiku-latest`) to
enable fallback. If no provider is configured the run fails
`RESEARCH_LLM_UNAVAILABLE`.

Every successful call is recorded to the per-tenant `llm_usage` ledger
(provider, model, tokens, `cost_usd`, `purpose`, `note_id`). The note's
`cost_usd` is the roll-up for its run; `llm_usage` is the per-call ledger that
budgets + the cost dashboard sum.

**Monthly budget cap** (`LLM_MONTHLY_BUDGET_USD`, default $10/tenant): before a
run, month-to-date `llm_usage` for the tenant is summed (UTC calendar month). At
or over the cap, the run is rejected — fail-fast `402 RESEARCH_BUDGET_EXCEEDED`
at the API, and authoritatively in the worker (phase-1 check →
`RESEARCH_BUDGET_EXCEEDED`). The cap is uniform across tenants for now
(per-tenant overrides + operator alerts deferred).
```

- [ ] **Step 2: Commit**
```bash
git add docs/runbooks/research-agent.md
git commit -m "docs(research): runbook — providers & budget (RA-3a)"
```

---

## Final verification (after all tasks)

- [ ] **Pure/unit:** `uv run pytest packages/core/tests/test_llm_cost.py packages/core/tests/test_llm_gateway.py packages/core/tests/test_research_note.py -q` — green.
- [ ] **DB API gate:** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run pytest tests/integration/test_research.py tests/integration/test_llm_usage.py tests/integration/test_schema_matches_models.py tests/integration/test_rag_ask.py -q` — green.
- [ ] **Worker e2e:** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q` — green (6 passed).
- [ ] **Isolation:** `uv sync && uv run python -c "import importlib.util as u; print('openai', bool(u.find_spec('openai')), 'anthropic', bool(u.find_spec('anthropic')))"` — `openai False anthropic False`.
- [ ] **Lint:** `uvx ruff check packages/core/saalr_core/llm packages/core/saalr_core/rag/chat.py apps/research-agent/research_agent apps/api/saalr_api/research` — clean.
- [ ] **Final code-review subagent** over the whole RA-3a diff.

## Self-review notes
- **Spec coverage:** gateway + fallback (T2); Anthropic adapter + config + extra (T2); `estimate_cost` canonical move + anthropic rates (T1); `llm_usage` ledger + migration 0010 + repo (T3); hard budget cap — worker phase-1 + API fail-fast (T4/T5); `ChatResult` provider/model + provider `name`s (T2); runbook (T6). All spec sections map to a task.
- **Signature consistency:** `run_research_job(..., chat_provider, embedding_provider, catalog, cap)` (T4 service) ↔ `_process`/`run_consumer(..., cap)` (T4 consumer) ↔ `_run_worker_once(..., cap)` (T4 test) ↔ `cli` builds `cap=monthly_cap(settings)`. `run_research(session, principal, redis, sessionmaker, cap, ticker, market, refresh)` (T5 service) ↔ the router call passing `request.app.state.llm_budget_cap` (T5 router) ↔ `app.state.llm_budget_cap = monthly_cap(settings)` (T5 main). `record_usage`/`month_to_date_cost` defined once (T3) and used by T4 worker + T5 service + T4/T5 tests.
- **Deliberate choices flagged for the reviewer:** `estimate_cost` re-exported from `research.note` (keeps RA-1's pure test + any importer working); the worker records cost using the gateway-stamped `result.provider`/`result.model` (the actual winning provider, not the gateway's nominal `model_name`); budget enforced both fail-fast (API) and authoritatively (worker phase-1) — both summing the same ledger; the cap is uniform (per-tenant override deferred); claude-3-5-haiku rates are estimates (real bill is source of truth).
- **No-regression:** RA-2's 8 `test_research.py` tests pass unchanged (seeded spend 0 < $10 cap); RAG-2's `/content/ask` unaffected by the optional `ChatResult` fields (T2 runs `test_rag_ask.py` as a guard).
