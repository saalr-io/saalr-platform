# tests/integration/test_montecarlo.py
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
            px = max(1.0, px * (1 + (0.004 if i % 2 else -0.0035)))
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


async def _make_pro(admin_engine, tid):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tid})


def _future_expiry(days=30):
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _long_call_config(underlying="AAPL"):
    return {
        "underlying": underlying,
        "legs": [{"kind": "option", "option_type": "CALL", "side": "BUY",
                  "strike": 100, "expiry": _future_expiry(30), "qty": 1, "entry_price": 2.5}],
    }


async def test_montecarlo_pro_garch_sigma(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)

            r = await c.post("/v1/strategies/montecarlo", json={"config": _long_call_config()}, headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert 0.0 <= body["pop"] <= 1.0
            assert body["sigma_source"] == "garch"
            assert body["horizon_days"] == 30
            assert sum(body["histogram"]["counts"]) == body["paths"]
            assert "ev" in body and "spot" in body


async def test_montecarlo_sigma_override(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-ovr@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=5)  # too few for GARCH, but spot is fine

            r = await c.post(
                "/v1/strategies/montecarlo",
                json={"config": _long_call_config(), "sigma": 0.3}, headers=h,
            )
            assert r.status_code == 200, r.text
            assert r.json()["sigma_source"] == "override"


async def test_montecarlo_free_tier_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-free@x.com"}
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.post("/v1/strategies/montecarlo", json={"config": _long_call_config()}, headers=h)
            assert r.status_code == 402


async def test_montecarlo_no_option_legs_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-noexp@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            cfg = {"underlying": "AAPL", "legs": [{"kind": "equity", "side": "BUY", "qty": 100}]}
            r = await c.post("/v1/strategies/montecarlo", json={"config": cfg}, headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "VALIDATION_NO_EXPIRY"


async def test_montecarlo_no_bars_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-nobars@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            async with admin_engine.begin() as conn:
                await conn.execute(text("DELETE FROM bars WHERE symbol='ZZZZ'"))
            r = await c.post(
                "/v1/strategies/montecarlo",
                json={"config": _long_call_config("ZZZZ")}, headers=h,
            )
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "INSUFFICIENT_HISTORY"
