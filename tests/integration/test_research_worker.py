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
from saalr_core.research.transcript_store import DbTranscriptStore

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


async def _post(c, h, ticker="AAPL"):
    return (await c.post("/research/run", json={"ticker": ticker}, headers=h)).json()["poll_url"]


async def _usage_rows(admin_engine, tid):
    async with admin_engine.begin() as conn:
        return (await conn.execute(
            text("SELECT purpose FROM llm_usage WHERE tenant_id=:t"), {"t": str(tid)})).all()


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
            rows = await _usage_rows(admin_engine, tid)
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
            # Enqueue while still under cap, THEN push spend over the cap so the worker's
            # phase-1 budget guard (not the route pre-check) is what trips this run.
            poll = await _post(c, h)
            async with tenant_session(app.state.sessionmaker, tid) as s:
                await llm_repo.record_usage(s, tenant_id=tid, user_id=uid, provider="openai",
                                            model="gpt-4o-mini", prompt_tokens=1, completion_tokens=1,
                                            cost_usd=Decimal("11"), purpose="seed")
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
            rows = await _usage_rows(admin_engine, tid)
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
