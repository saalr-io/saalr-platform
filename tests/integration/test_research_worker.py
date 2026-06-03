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
