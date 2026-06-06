import httpx
from sqlalchemy import text
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_sentiment_free_is_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.get("/v1/market/sentiment?ticker=AAPL", headers={"Authorization": "Bearer dev:sg-free@x.com"})
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_NEWS_SENTIMENT_REQUIRES_PRO"


async def test_sentiment_pro_is_200(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:sg-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            async with admin_engine.begin() as conn:
                await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tid})
            r = await c.get("/v1/market/sentiment?ticker=AAPL", headers=h)
            assert r.status_code == 200 and r.json()["ticker"] == "AAPL"
