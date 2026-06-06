import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, n=300):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    px = 100.0
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol = :s"), {"s": symbol})
        for i in range(n):
            step = math.sin(i * 0.3) * 0.01 + (0.0005 if i % 2 else -0.0004)
            px = max(1.0, px * (1 + step))
            ts = start + timedelta(days=i)
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""),
                {"ts": ts, "sym": symbol, "o": Decimal(str(round(px, 4))),
                 "h": Decimal(str(round(px + 1, 4))), "l": Decimal(str(round(px - 1, 4))),
                 "c": Decimal(str(round(px, 4))), "v": 1000},
            )


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tenant_id})


async def test_price_forecast_pro_returns_all_models(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pf-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/price-forecast?ticker=AAPL&horizon=5", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["horizon_days"] == 5 and body["primary_model"] in ("arima", "lstm", "naive")
            names = {m["model"] for m in body["models"]}
            assert names == {"arima", "lstm", "naive"}
            assert all(len(m["path"]) == 5 for m in body["models"])
            again = await c.get("/v1/market/price-forecast?ticker=AAPL&horizon=5", headers=h)
            assert again.json() == body


async def test_price_forecast_free_tier_is_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pf-free@x.com"}
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/price-forecast?ticker=AAPL&horizon=5", headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO"


async def test_price_forecast_insufficient_history_is_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pf-short@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "TINY", n=100)
            r = await c.get("/v1/market/price-forecast?ticker=TINY&horizon=5", headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "INSUFFICIENT_HISTORY"
