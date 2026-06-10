import os

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text

from saalr_api.main import create_app

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tid):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tid})


async def test_free_tier_gets_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:disc-free@x.com"}
            r = await c.post(
                "/v1/discovery",
                json={"underlying": "AAPL", "market": "US", "dte_min": 0, "dte_max": 60},
                headers=h,
            )
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO"


async def test_pro_creates_queued_run_and_polls(app_sessionmaker, admin_engine):
    r0 = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r0.delete("saalr:disc:jobs:v1")
    await r0.aclose()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:disc-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            r = await c.post(
                "/v1/discovery",
                json={"underlying": "AAPL", "market": "US", "dte_min": 0, "dte_max": 60, "top_n": 5},
                headers=h,
            )
            assert r.status_code == 202, r.text
            body = r.json()
            assert body["status"] == "queued"
            assert body["poll_url"] == f"/v1/discovery/{body['discovery_id']}"
            poll = await c.get(body["poll_url"], headers=h)
            assert poll.status_code == 200
            assert poll.json()["status"] in ("queued", "running", "succeeded")


async def test_idempotency_key_dedupes(app_sessionmaker, admin_engine):
    r0 = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r0.delete("saalr:disc:jobs:v1")
    await r0.aclose()
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:disc-idem@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            headers = {**h, "Idempotency-Key": "disc-abc-123"}
            body = {"underlying": "AAPL", "market": "US", "dte_min": 0, "dte_max": 60}
            a = await c.post("/v1/discovery", json=body, headers=headers)
            b = await c.post("/v1/discovery", json=body, headers=headers)
            assert a.status_code == 202 and b.status_code == 202
            assert a.json()["discovery_id"] == b.json()["discovery_id"]
