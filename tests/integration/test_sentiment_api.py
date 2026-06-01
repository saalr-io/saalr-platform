import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tid):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tid})


async def _seed_sentiment(admin_engine, symbol, score=0.6, label="bullish"):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol=:s"), {"s": symbol})
        await conn.execute(
            text(
                """INSERT INTO news_sentiment
                   (sentiment_id, symbol, market, score, label, confident, n_headlines,
                    total_weight, as_of, computed_at)
                   VALUES (gen_random_uuid(), :s, 'US', :sc, :lb, true, 5, 3.2, now(), now())"""
            ),
            {"s": symbol, "sc": score, "lb": label},
        )


async def test_sentiment_pro_has_data(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:sent-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_sentiment(admin_engine, "AAPL", score=0.6, label="bullish")

            r = await c.get("/v1/market/sentiment?ticker=AAPL", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["has_data"] is True and body["label"] == "bullish"
            assert abs(body["score"] - 0.6) < 1e-9 and body["computed_at"] is not None


async def test_sentiment_free_is_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:sent-free@x.com"}
            r = await c.get("/v1/market/sentiment?ticker=AAPL", headers=h)
            assert r.status_code == 402


async def test_sentiment_unknown_is_neutral(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:sent-none@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            async with admin_engine.begin() as conn:
                await conn.execute(text("DELETE FROM news_sentiment WHERE symbol='ZZZZ'"))
            r = await c.get("/v1/market/sentiment?ticker=ZZZZ", headers=h)
            assert r.status_code == 200
            body = r.json()
            assert body["has_data"] is False and body["score"] == 0.0 and body["confident"] is False
