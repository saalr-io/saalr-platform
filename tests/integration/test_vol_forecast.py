import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, n=300):
    # a deterministic pseudo-random walk with mild volatility clustering
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    px = 100.0
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol = :s"), {"s": symbol})
        vol = 0.01
        for i in range(n):
            vol = 0.9 * vol + 0.1 * (0.01 + 0.02 * (i % 7 == 0))
            step = math.sin(i * 0.3) * vol + (0.0005 if i % 2 else -0.0004)
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


async def test_vol_forecast_pro_returns_both_models_and_persists_validation(app_sessionmaker, admin_engine):
    email = "vf-pro@x.com"
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": f"Bearer dev:{email}"}
            # a /me call bootstraps the tenant + subscription and returns the tenant id
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)

            r = await c.get("/v1/market/vol-forecast?ticker=AAPL&horizon=10", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ticker"] == "AAPL" and body["horizon_days"] == 10
            assert body["primary_model"] in ("garch", "hv21", "har")
            assert len(body["primary_forecast"]) == 10
            assert body["validation"]["holdout_days"] >= 1
            assert len(body["alternative_models"]) == 2

    # a model_validation_runs row was written
    async with admin_engine.begin() as conn:
        n = (await conn.execute(
            text("SELECT count(*) FROM model_validation_runs WHERE model_name='garch'")
        )).scalar_one()
    assert n >= 1


async def test_vol_forecast_free_tier_is_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:vf-free@x.com"}
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/vol-forecast?ticker=AAPL&horizon=10", headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO"


async def test_vol_forecast_insufficient_history_is_422(app_sessionmaker, admin_engine):
    email = "vf-short@x.com"
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": f"Bearer dev:{email}"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "TINY", n=100)  # < 250
            r = await c.get("/v1/market/vol-forecast?ticker=TINY&horizon=10", headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "INSUFFICIENT_HISTORY"


async def test_vol_forecast_includes_har(app_sessionmaker, admin_engine):
    email = "vf-har@x.com"
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": f"Bearer dev:{email}"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/vol-forecast?ticker=AAPL&horizon=10", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            names = {body["primary_model"], *[a["model"] for a in body["alternative_models"]]}
            assert names == {"garch", "hv21", "har"}
            assert "har_mae" in body["validation"]
            assert len(body["alternative_models"]) == 2
