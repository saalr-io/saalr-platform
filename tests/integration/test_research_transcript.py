import os
from decimal import Decimal
from uuid import uuid4

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
