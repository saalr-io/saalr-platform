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
        vol = 0.01
        for i in range(n):
            vol = 0.9 * vol + 0.1 * (0.01 + 0.02 * (i % 7 == 0))
            step = math.sin(i * 0.3) * vol + (0.0008 if i % 2 else -0.0003)
            px = max(1.0, px * (1 + step))
            ts = start + timedelta(days=i)
            await conn.execute(
                text(
                    """INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                       VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""
                ),
                {"ts": ts, "sym": symbol, "o": Decimal(str(round(px, 4))),
                 "h": Decimal(str(round(px + 1, 4))), "l": Decimal(str(round(px - 1, 4))),
                 "c": Decimal(str(round(px, 4))), "v": 1000},
            )


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tenant_id}
        )


async def test_regime_free_tier_base_only(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rg-free@x.com"}
            await c.get("/me", headers=h)
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/regime?ticker=AAPL", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ticker"] == "AAPL"
            assert body["regime"]["premium_available"] is False
            assert body["regime"]["premium"] is None
            assert body["regime"]["direction"]["label"] in (
                "strong_bullish", "bullish", "neutral", "bearish", "strong_bearish")
            assert len(body["recommendations"]) == 21
            assert "·" in body["regime"]["headline"]


async def test_regime_pro_tier_has_premium_layer(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rg-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "MSFT", n=300)
            r = await c.get("/v1/market/regime?ticker=MSFT", headers=h)
            assert r.status_code == 200, r.text
            prem = r.json()["regime"]["premium"]
            assert prem is not None
            assert "vol_trend" in prem and "sentiment" in prem
            assert prem["vol_trend"]["available"] is True  # 300 bars >= 250


async def test_regime_insufficient_history_is_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rg-thin@x.com"}
            await c.get("/me", headers=h)
            await _seed_bars(admin_engine, "TINY", n=40)  # < 60
            r = await c.get("/v1/market/regime?ticker=TINY", headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "INSUFFICIENT_HISTORY"


async def test_regime_non_alpha_ticker_is_404(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rg-bad@x.com"}
            await c.get("/me", headers=h)
            r = await c.get("/v1/market/regime?ticker=123", headers=h)
            assert r.status_code == 404
