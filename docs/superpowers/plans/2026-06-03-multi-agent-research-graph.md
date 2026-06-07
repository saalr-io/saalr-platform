# RA-3b — Multi-agent research graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace RA-2's single LLM call in the research worker with a hand-rolled 6-role agent graph (Fundamentals/Sentiment/Technical/Risk → Trader → PM), each call metered through RA-3a's gateway (budget-checked + cost-recorded). Worker-logic change only — no migration, no API/schema change.

**Architecture:** Pure prompt builders (`saalr_core/research/agents.py`) + a per-call metering helper (`saalr_core/llm/metered.py`) + a sequential orchestrator (`saalr_core/research/graph.py`). The worker's `run_research_job` phase 2 calls the graph; phase 3 saves the PM synthesis with summed usage and no longer records (the graph metered each call).

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Postgres + RLS, Redis, pytest. Gateway + ledger from RA-3a.

**Spec:** `docs/superpowers/specs/2026-06-03-multi-agent-research-graph-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- DB tests need Postgres on **55432**, Redis on **6379**. Prefix:
  `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <args>`
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore`, `.env`, `uv.lock`, or `tools/`.

---

### Task 1: Agent prompt builders (`saalr_core/research/agents.py`)

Pure `(system, user)` builders for the six roles. No DB, no network.

**Files:**
- Create: `packages/core/saalr_core/research/agents.py`
- Test: `packages/core/tests/test_research_agents.py`

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_research_agents.py`:
```python
from saalr_core.research.agents import (
    ANALYST_ROLES,
    build_analyst_prompt,
    build_pm_prompt,
    build_trader_prompt,
)
from saalr_core.research.note import ResearchInputs


def _inputs(spot=50.0, vol={"primary_model": "garch"}, sentiment={"label": "bullish"}):
    return ResearchInputs("AAPL", "US", spot, vol, sentiment,
                          [("greeks-delta", "Delta", "Delta measures exposure.")])


def test_analyst_roles_are_the_four_expected():
    assert ANALYST_ROLES == ("fundamentals", "sentiment", "technical", "risk")


def test_each_analyst_prompt_has_guardrail_and_signals():
    for role in ANALYST_ROLES:
        system, user = build_analyst_prompt(role, _inputs())
        assert "Do not invent" in system
        assert "AAPL" in user
    # the fundamentals role must explicitly flag the missing financials
    fsys, _ = build_analyst_prompt("fundamentals", _inputs())
    assert "NOT provided" in fsys or "not provided" in fsys


def test_analyst_prompt_annotates_missing_signal():
    _system, user = build_analyst_prompt("technical", _inputs(vol=None))
    assert "unavailable" in user


def test_trader_prompt_includes_all_analyst_memos():
    memos = {"fundamentals": "F-memo", "sentiment": "S-memo",
             "technical": "T-memo", "risk": "R-memo"}
    system, user = build_trader_prompt(_inputs(), memos)
    assert "Do not invent" in system
    for m in ("F-memo", "S-memo", "T-memo", "R-memo"):
        assert m in user


def test_pm_prompt_lists_sections_and_includes_memos():
    memos = {"fundamentals": "F", "sentiment": "S", "technical": "T",
             "risk": "R", "trader": "Thesis-X"}
    system, user = build_pm_prompt(_inputs(), memos)
    for sec in ("Overview", "Volatility", "Sentiment", "Risks", "Summary"):
        assert sec in system
    assert "Thesis-X" in user and "F" in user
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_research_agents.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.research.agents`.

- [ ] **Step 3: Implement**

Create `packages/core/saalr_core/research/agents.py`:
```python
from __future__ import annotations

from saalr_core.research.note import ResearchInputs

ANALYST_ROLES = ("fundamentals", "sentiment", "technical", "risk")

_GUARDRAIL = (
    "Use ONLY the provided signals and memos. When a signal is unavailable, say so explicitly. "
    "Do not invent data, prices, or recommendations; this is educational analysis, not advice."
)

_ANALYST_SYSTEMS = {
    "fundamentals": (
        "You are the Fundamentals analyst on a Saalr research team. Detailed financial statements "
        "(revenue, earnings, ratios) are NOT provided to you — do NOT invent any. Explicitly state "
        "that fundamentals data is unavailable, then give a brief qualitative note on what a reader "
        "should research. " + _GUARDRAIL
    ),
    "sentiment": (
        "You are the Sentiment analyst on a Saalr research team. From the sentiment signal and any "
        "concept excerpts, summarize the market mood in 2-4 sentences. " + _GUARDRAIL
    ),
    "technical": (
        "You are the Technical analyst on a Saalr research team. From the spot price and the GARCH "
        "volatility forecast, comment on the price and volatility regime in 2-4 sentences. " + _GUARDRAIL
    ),
    "risk": (
        "You are the Risk analyst on a Saalr research team. From the volatility forecast and the "
        "other signals, describe the key risks and sources of uncertainty in 2-4 sentences. " + _GUARDRAIL
    ),
}

_TRADER_SYSTEM = (
    "You are the Trader on a Saalr research team. Given the analyst memos, articulate a concise "
    "educational thesis in 2-4 sentences. Note where the analysts disagree. This is not advice. "
    + _GUARDRAIL
)

_PM_SYSTEM = (
    "You are the Portfolio Manager on a Saalr research team. Synthesize the analyst memos and the "
    "trader's thesis into a concise markdown research note with these sections: Overview, "
    "Volatility, Sentiment, Risks, Summary. " + _GUARDRAIL
)


def _signals_block(inputs: ResearchInputs) -> str:
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
    return "\n".join(lines)


def _memo_block(memos: dict[str, str], roles) -> str:
    return "\n\n".join(f"## {role.capitalize()} memo\n{memos[role]}"
                       for role in roles if role in memos)


def build_analyst_prompt(role: str, inputs: ResearchInputs) -> tuple[str, str]:
    """(system, user) for one analyst role, grounded in the composed signals."""
    return _ANALYST_SYSTEMS[role], _signals_block(inputs)


def build_trader_prompt(inputs: ResearchInputs, memos: dict[str, str]) -> tuple[str, str]:
    user = _signals_block(inputs) + "\n\nAnalyst memos:\n\n" + _memo_block(memos, ANALYST_ROLES)
    return _TRADER_SYSTEM, user


def build_pm_prompt(inputs: ResearchInputs, memos: dict[str, str]) -> tuple[str, str]:
    user = (_signals_block(inputs) + "\n\nTeam memos:\n\n"
            + _memo_block(memos, (*ANALYST_ROLES, "trader")))
    return _PM_SYSTEM, user
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_research_agents.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/research/agents.py packages/core/tests/test_research_agents.py
git add packages/core/saalr_core/research/agents.py packages/core/tests/test_research_agents.py
git commit -m "feat(research): multi-agent prompt builders (6 roles)"
```

---

### Task 2: `metered_complete` + `run_agent_graph`

**Files:**
- Create: `packages/core/saalr_core/llm/metered.py`
- Create: `packages/core/saalr_core/research/graph.py`
- Test: `tests/integration/test_agent_graph.py`

DB on 55432. Tested with a stub gateway (keyless), in the default gate (no worker package import).

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_agent_graph.py`:
```python
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo
from saalr_core.llm.cost import BudgetExceeded
from saalr_core.llm.gateway import ChatGateway
from saalr_core.llm.metered import metered_complete
from saalr_core.rag.chat import StubChatProvider
from saalr_core.research.graph import run_agent_graph
from saalr_core.research.note import ResearchInputs

_EXPECTED_PURPOSES = {f"research_agent:{r}" for r in
                      ("fundamentals", "sentiment", "technical", "risk", "trader", "pm")}


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _me(c, h):
    body = (await c.get("/me", headers=h)).json()
    return UUID(body["tenant"]["id"]), UUID(body["user"]["id"])


async def test_run_agent_graph_makes_six_metered_calls(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            tid, uid = await _me(c, {"Authorization": "Bearer dev:graph1@x.com"})
            inputs = ResearchInputs("AAPL", "US", 50.0, None, None, [])
            note_id = uuid4()
            res = await run_agent_graph(
                app.state.sessionmaker, tid, uid, inputs=inputs,
                gateway=ChatGateway([StubChatProvider()]), cap=Decimal("10"), note_id=note_id)
            assert res.note_markdown
            assert res.model == "stub-chat" and res.provider == "stub"
            assert res.prompt_tokens > 0
            async with admin_engine.begin() as conn:
                rows = (await conn.execute(
                    text("SELECT purpose, note_id FROM llm_usage WHERE tenant_id=:t"),
                    {"t": str(tid)})).all()
            assert {r.purpose for r in rows} == _EXPECTED_PURPOSES
            assert all(str(r.note_id) == str(note_id) for r in rows)


async def test_metered_complete_raises_when_over_budget(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            tid, uid = await _me(c, {"Authorization": "Bearer dev:graph2@x.com"})
            async with tenant_session(app.state.sessionmaker, tid) as s:
                await llm_repo.record_usage(s, tenant_id=tid, user_id=uid, provider="x",
                                            model="gpt-4o-mini", prompt_tokens=1, completion_tokens=1,
                                            cost_usd=Decimal("11"), purpose="seed")
            with pytest.raises(BudgetExceeded):
                await metered_complete(
                    app.state.sessionmaker, tid, uid, gateway=ChatGateway([StubChatProvider()]),
                    cap=Decimal("10"), purpose="test", note_id=uuid4(), system="s", user="u")
```

- [ ] **Step 2: Run to verify it fails**

Run (DB env prefix): `uv run pytest tests/integration/test_agent_graph.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.llm.metered`.

- [ ] **Step 3: Implement `metered_complete`**

Create `packages/core/saalr_core/llm/metered.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo
from saalr_core.llm.cost import BudgetExceeded, budget_exceeded, estimate_cost, month_start
from saalr_core.rag.chat import ChatResult


async def metered_complete(sessionmaker, tenant_id, user_id, *, gateway, cap, purpose, note_id,
                           system, user) -> tuple[ChatResult, Decimal]:
    """One budget-gated, cost-recorded gateway call. Two short transactions around the LLM
    call (budget read, then record) so no DB session is held across the slow call.

    Raises BudgetExceeded if month-to-date spend has reached the cap; propagates the gateway's
    ChatError if every provider fails."""
    async with tenant_session(sessionmaker, tenant_id) as s:
        spent = await llm_repo.month_to_date_cost(
            s, tenant_id, month_start(datetime.now(timezone.utc)))
    if budget_exceeded(spent, cap):
        raise BudgetExceeded(f"month-to-date {spent} >= cap {cap}")

    result = await gateway.complete(system, user)

    model = result.model or gateway.model_name
    provider = result.provider or getattr(gateway, "name", "unknown")
    cost = estimate_cost(model, result.prompt_tokens, result.completion_tokens)
    async with tenant_session(sessionmaker, tenant_id) as s:
        await llm_repo.record_usage(
            s, tenant_id=tenant_id, user_id=user_id, provider=provider, model=model,
            prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
            cost_usd=cost, purpose=purpose, note_id=note_id)
    return result, cost
```

- [ ] **Step 4: Implement `run_agent_graph`**

Create `packages/core/saalr_core/research/graph.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from saalr_core.llm.metered import metered_complete
from saalr_core.research.agents import (
    ANALYST_ROLES,
    build_analyst_prompt,
    build_pm_prompt,
    build_trader_prompt,
)


@dataclass(frozen=True)
class AgentGraphResult:
    note_markdown: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    model: str
    provider: str


async def run_agent_graph(sessionmaker, tenant_id, user_id, *, inputs, gateway, cap,
                          note_id) -> AgentGraphResult:
    """Run the 4 analysts -> Trader -> PM sequentially, each a metered gateway call.
    Returns the PM synthesis + summed usage (model/provider from the PM call)."""
    memos: dict[str, str] = {}
    totals = {"p": 0, "c": 0, "cost": Decimal(0)}

    async def _call(purpose: str, system: str, user: str):
        result, cost = await metered_complete(
            sessionmaker, tenant_id, user_id, gateway=gateway, cap=cap,
            purpose=purpose, note_id=note_id, system=system, user=user)
        totals["p"] += result.prompt_tokens
        totals["c"] += result.completion_tokens
        totals["cost"] += cost
        return result

    for role in ANALYST_ROLES:
        system, user = build_analyst_prompt(role, inputs)
        memos[role] = (await _call(f"research_agent:{role}", system, user)).text

    system, user = build_trader_prompt(inputs, memos)
    memos["trader"] = (await _call("research_agent:trader", system, user)).text

    system, user = build_pm_prompt(inputs, memos)
    pm = await _call("research_agent:pm", system, user)

    return AgentGraphResult(
        note_markdown=pm.text, prompt_tokens=totals["p"], completion_tokens=totals["c"],
        cost_usd=totals["cost"], model=pm.model or gateway.model_name,
        provider=pm.provider or getattr(gateway, "name", "unknown"))
```

- [ ] **Step 5: Run to verify it passes**

Run (DB env prefix): `uv run pytest tests/integration/test_agent_graph.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/llm/metered.py packages/core/saalr_core/research/graph.py tests/integration/test_agent_graph.py
git add packages/core/saalr_core/llm/metered.py packages/core/saalr_core/research/graph.py tests/integration/test_agent_graph.py
git commit -m "feat(research): metered_complete + run_agent_graph orchestrator"
```

---

### Task 3: Worker integration — graph replaces the single call

Swap the single `build_research_prompt → chat.complete` in `run_research_job` phase 2 for the graph; phase 3 saves the synthesis and no longer records (the graph metered each call).

**Files:**
- Modify: `apps/research-agent/research_agent/service.py`
- Test: `tests/integration/test_research_worker.py` (rewrite)

> **Worker-test invocation:** run via `--package saalr-research-agent`:
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
from saalr_core.rag.chat import ChatError, ChatResult, StubChatProvider
from saalr_core.rag.embeddings import HashEmbeddingProvider

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_CAP = Decimal("10")
_EXPECTED_PURPOSES = {f"research_agent:{r}" for r in
                      ("fundamentals", "sentiment", "technical", "risk", "trader", "pm")}


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


class _CostlyChat:
    """Each call costs ~$0.15 (gpt-4o-mini rate on 1M prompt tokens) so a low cap trips mid-graph."""
    name = "costly"
    model_name = "gpt-4o-mini"

    async def complete(self, system, user):
        return ChatResult("memo", prompt_tokens=1_000_000, completion_tokens=0)


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


async def _usage_count(admin_engine, tid):
    async with admin_engine.begin() as conn:
        rows = (await conn.execute(
            text("SELECT purpose FROM llm_usage WHERE tenant_id=:t"), {"t": str(tid)})).all()
    return rows


async def test_e2e_six_agents_succeed_and_record(app_sessionmaker, admin_engine):
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
            assert done["summary"] and done["model"] == "stub-chat"
            rows = await _usage_count(admin_engine, tid)
            assert {r.purpose for r in rows} == _EXPECTED_PURPOSES


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
            assert (await c.get(poll, headers=h)).json()["status"] == "succeeded"


async def test_e2e_budget_exceeded_at_start_fails(app_sessionmaker, admin_engine):
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
                                            cost_usd=Decimal("11"), purpose="seed")
            poll = await _post(c, h)
            await _run_worker_once(chat=ChatGateway([StubChatProvider()]))
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "failed"
            assert done["error"]["code"] == "RESEARCH_BUDGET_EXCEEDED"


async def test_e2e_budget_tips_mid_graph(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw4@x.com"}
            tid, _ = await _me(c, h)
            await _tier(admin_engine, str(tid), "premium")
            poll = await _post(c, h)
            # cap $0.10; each _CostlyChat call records $0.15 -> the 2nd call's pre-check trips
            await _run_worker_once(chat=ChatGateway([_CostlyChat()]), cap=Decimal("0.10"))
            done = (await c.get(poll, headers=h)).json()
            assert done["status"] == "failed"
            assert done["error"]["code"] == "RESEARCH_BUDGET_EXCEEDED"
            rows = await _usage_count(admin_engine, tid)
            assert len(rows) == 1  # only the first (fundamentals) call recorded before the trip


async def test_e2e_graceful_degradation(app_sessionmaker, admin_engine):
    await _clean_stream()
    await _seed_bars(admin_engine, "AAPL", n=40)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rw5@x.com"}
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
            h = {"Authorization": "Bearer dev:rw6@x.com"}
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
            h = {"Authorization": "Bearer dev:rw7@x.com"}
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
Expected: FAIL — the single-call worker records 1 usage row (`purpose="research_note"`), not 6 `research_agent:*` rows; the mid-graph test fails too.

- [ ] **Step 3: Wire the graph into `service.py`**

In `apps/research-agent/research_agent/service.py`:
- Update the import block: drop `build_research_prompt` and `estimate_cost` (no longer used here — the graph computes cost), keep `ResearchInputs`, and add the graph import. The block becomes:
```python
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo
from saalr_core.llm.cost import BudgetExceeded, budget_exceeded, month_start
from saalr_core.marketdata.bars import load_closes
from saalr_core.rag.chat import ChatError
from saalr_core.rag.embeddings import EmbeddingError
from saalr_core.rag.qa import retrieve_context
from saalr_core.research import repo
from saalr_core.research.graph import run_agent_graph
from saalr_core.research.note import ResearchInputs
from saalr_core.sentiment.repo import latest_sentiment
from saalr_ml.forecast import vol_forecast
```
(`llm_repo` stays — phase 1's budget check uses `month_to_date_cost`; `estimate_cost` and `build_research_prompt` are removed.)
- Leave `log`, `NoPriceData`, `gather_inputs`, and phase 1 of `run_research_job` EXACTLY as they are.
- Replace phase 2 (the `try:` block that does `gather_inputs` → `build_research_prompt` → `chat_provider.complete`) with:
```python
    # Phase 2 — compute: gather signals, then run the multi-agent graph (each call metered).
    try:
        async with tenant_session(sessionmaker, tenant_id) as session:
            inputs = await gather_inputs(
                session, embedding_provider=embedding_provider, catalog=catalog,
                ticker=ticker, market=market)
        if chat_provider is None:
            raise ChatError("no chat provider configured")
        graph = await run_agent_graph(
            sessionmaker, tenant_id, user_id, inputs=inputs, gateway=chat_provider,
            cap=cap, note_id=note_id)
    except NoPriceData as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_NO_PRICE_DATA", exc)
    except BudgetExceeded as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_BUDGET_EXCEEDED", exc)
    except (ChatError, EmbeddingError) as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_LLM_UNAVAILABLE", exc)
    except Exception as exc:  # noqa: BLE001
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_GENERATION_FAILED", exc)
```
- Replace phase 3 (the success persist + `record_usage`) with the graph-aware version (NO `record_usage` — the graph metered every call):
```python
    # Phase 3 — persist the synthesis with summed usage (the graph already recorded each call).
    signals = {"spot": inputs.spot, "vol_forecast": inputs.vol_forecast, "sentiment": inputs.sentiment}
    sources = [{"slug": slug, "title": title} for slug, title, _c in inputs.content_excerpts]
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_succeeded(
            session, note_id, summary=graph.note_markdown, signals=signals, sources=sources,
            model=graph.model, prompt_tokens=graph.prompt_tokens,
            completion_tokens=graph.completion_tokens, cost_usd=graph.cost_usd)
    return {"status": "succeeded"}
```
- Leave `_fail` EXACTLY as it is.

- [ ] **Step 4: Run the e2e suite**

Run (DB+Redis env prefix): `uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q`
Expected: PASS (7 passed). If a test fails, read the polled JSON + worker logs; do NOT weaken assertions.

- [ ] **Step 5: Lint + commit**
```bash
uvx ruff check apps/research-agent/research_agent/service.py tests/integration/test_research_worker.py
git add apps/research-agent/research_agent/service.py tests/integration/test_research_worker.py
git commit -m "feat(research): worker runs the 6-agent graph (RA-3b)"
```

---

### Task 4: Runbook update

**Files:**
- Modify: `docs/runbooks/research-agent.md`

- [ ] **Step 1: Add the multi-agent section**

Append to `docs/runbooks/research-agent.md`:
```markdown

## Multi-agent graph (RA-3b)

Each research run executes a hand-rolled 6-role graph (sequential): the analysts
**Fundamentals → Sentiment → Technical → Risk**, then the **Trader** (thesis),
then the **Portfolio Manager** (synthesis). The PM's markdown becomes the note's
`summary`; the analyst/trader memos are transient (transcript persistence is
RA-3c). Fundamentals has no financials wired into the platform, so its prompt
explicitly states the gap and forbids inventing figures.

Every run makes **6 metered gateway calls** — one `llm_usage` row each, with
`purpose="research_agent:<role>"`, all linked to the run's `note_id`. The note's
`prompt_tokens`/`completion_tokens`/`cost_usd` are the sums across the six calls;
`model` is the PM call's model.

The budget is checked **before every call** (not just at run start), so a run can
fail `RESEARCH_BUDGET_EXCEEDED` partway through with the already-completed calls'
cost recorded. (At-least-once redelivery of a crashed run re-runs the graph and
may double-count `llm_usage` rows — an accepted over-count, dedup deferred.)
```

- [ ] **Step 2: Commit**
```bash
git add docs/runbooks/research-agent.md
git commit -m "docs(research): runbook — multi-agent graph (RA-3b)"
```

---

## Final verification (after all tasks)

- [ ] **Pure/unit:** `uv run pytest packages/core/tests/test_research_agents.py packages/core/tests/test_research_note.py -q` — green.
- [ ] **Graph integration:** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run pytest tests/integration/test_agent_graph.py -q` — green (2 passed).
- [ ] **Worker e2e:** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run --package saalr-research-agent pytest tests/integration/test_research_worker.py -q` — green (7 passed).
- [ ] **Regression:** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run pytest tests/integration/test_research.py tests/integration/test_llm_usage.py tests/integration/test_schema_matches_models.py tests/integration/test_rag_ask.py -q` — green (API/schema/RAG-2 unchanged).
- [ ] **Isolation:** `uv sync && uv run python -c "import importlib.util as u; print('openai', bool(u.find_spec('openai')), 'anthropic', bool(u.find_spec('anthropic')))"` — `openai False anthropic False`.
- [ ] **Lint:** `uvx ruff check packages/core/saalr_core/research packages/core/saalr_core/llm apps/research-agent/research_agent` — clean.
- [ ] **Final code-review subagent** over the whole RA-3b diff.

## Self-review notes
- **Spec coverage:** 6-role graph + honest Fundamentals (T1 agents); per-call `metered_complete` + sequential `run_agent_graph` (T2); worker phase-2 graph swap + phase-3 no-record (T3); no migration / no API change (nothing touches migrations, router, schemas, or main.py); runbook (T4). All spec sections map to a task.
- **Signature consistency:** `metered_complete(sessionmaker, tenant_id, user_id, *, gateway, cap, purpose, note_id, system, user) -> (ChatResult, Decimal)` (T2) is called identically by `run_agent_graph` (T2) and the test (T2). `run_agent_graph(sessionmaker, tenant_id, user_id, *, inputs, gateway, cap, note_id) -> AgentGraphResult` (T2) ↔ the worker call (T3) ↔ the graph test (T2). `build_analyst_prompt(role, inputs)`, `build_trader_prompt(inputs, memos)`, `build_pm_prompt(inputs, memos)` (T1) ↔ the graph (T2). `ANALYST_ROLES` is the single source of the four analyst names + the six `research_agent:*` purposes.
- **Deliberate choices flagged for the reviewer:** phase 3 no longer records usage (the graph's `metered_complete` did, per call) — the note's roll-up cost = sum of its `llm_usage` rows; `model`/`provider` come from the PM call; the mid-graph budget trip records partial cost (intended); `gather_inputs`'s RAG query embedding stays unmetered (one tiny embed); sequential execution (parallel deferred); at-least-once duplicate-ledger on crash-retry is accepted + documented.
- **No-regression:** the API/router/schema/migrations are untouched, so RA-3a's `test_research.py` (9), `test_llm_usage.py`, `test_schema_matches_models.py`, and RAG-2's `test_rag_ask.py` pass unchanged. The `StubChatProvider` cost is 0, so a successful multi-agent note has `cost_usd == 0` and six zero-cost ledger rows — tests assert the row set, not a non-zero cost.
