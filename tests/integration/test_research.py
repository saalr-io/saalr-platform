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
        # news_sentiment is a shared (non-RLS) table the conftest does not truncate; clear any
        # stale row for this symbol so "no sentiment seeded" scenarios start from a clean slate.
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol=:s"), {"s": symbol})
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
