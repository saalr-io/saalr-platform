import os
from decimal import Decimal
from uuid import UUID

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo
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
