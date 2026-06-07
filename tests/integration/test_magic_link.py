import os

import httpx
import pytest_asyncio
import redis.asyncio as aioredis

from saalr_api.main import create_app

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture(autouse=True)
async def _flush_magic():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    async for k in r.scan_iter("magiclink:*"):
        await r.delete(k)
    yield
    async for k in r.scan_iter("magiclink:*"):
        await r.delete(k)
    await r.aclose()


async def test_request_then_verify_issues_session_token():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.post("/auth/magic/request", json={"email": "Alice@Acme.com"})
            assert r.status_code == 200
            body = r.json()
            assert body["sent"] is True
            assert "/app/auth/verify?token=" in body["dev_link"]
            token = body["dev_link"].split("token=", 1)[1]

            v = await c.post("/auth/magic/verify", json={"token": token})
            assert v.status_code == 200
            assert v.json()["token"] == "dev:alice@acme.com"


async def test_link_is_single_use():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            token = (
                await c.post("/auth/magic/request", json={"email": "b@x.com"})
            ).json()["dev_link"].split("token=", 1)[1]
            assert (await c.post("/auth/magic/verify", json={"token": token})).status_code == 200
            assert (await c.post("/auth/magic/verify", json={"token": token})).status_code == 410


async def test_garbage_token_is_410():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            assert (await c.post("/auth/magic/verify", json={"token": "nope"})).status_code == 410


async def test_endpoints_404_under_clerk(monkeypatch):
    monkeypatch.setenv("AUTH_PROVIDER", "clerk")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://example.com/.well-known/jwks.json")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            assert (
                await c.post("/auth/magic/request", json={"email": "a@b.com"})
            ).status_code == 404
            assert (await c.post("/auth/magic/verify", json={"token": "x"})).status_code == 404
