import httpx
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind


class StubProvider:
    async def get_option_chain(self, ticker, market):
        return RawChain(
            underlying=ticker.upper(), market=market, as_of="2026-05-30T14:30:00+00:00",
            spot=185.0, div_yield=0.005,
            contracts=[
                RawContract("2026-09-19", 180.0, OptionKind.CALL, 9.0, 9.2, 9.1, 100, 500,
                            0.26, 0.58, 0.02, -0.05, 0.11),
            ],
        )


class StubRates:
    source_name = "fred"

    async def get_curve(self):
        return YieldCurve("2026-05-29", [(1 / 12, 0.05), (2.0, 0.045)])


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
                           {"t": tenant_id})


async def _seed_earlier_snapshot(admin_engine, oi: int):
    """Insert one earlier snapshot for OICHG @180 CALL with the given OI."""
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM options_chain_snapshots WHERE underlying='OICHG'"))
        await conn.execute(
            text("INSERT INTO options_chain_snapshots "
                 "(ts, underlying, market, expiry, strike, option_type, open_interest) "
                 "VALUES (:ts,'OICHG','US','2026-09-19',:strike,'CALL',:oi)"),
            {"ts": datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
             "strike": Decimal("180"), "oi": oi},
        )


async def test_chain_reports_oi_change_vs_earlier_snapshot(app_sessionmaker, admin_engine):
    await _seed_earlier_snapshot(admin_engine, oi=450)
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        await app.state.redis.delete("mdq:chain:v1:US:OICHG")
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oichg@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            r = await c.get("/v1/market/chain?ticker=OICHG&expiry=2026-09-19", headers=h)
    assert r.status_code == 200
    body = r.json()
    # current OI 500 - earlier 450 = +50 for every window (only one earlier snapshot)
    contract = body["contracts"][0]
    assert contract["oi_change"]["day"] == 50
    assert contract["oi_change"]["1h"] == 50
    assert body["oi_baselines"]["day"]["ts"].startswith("2026-05-30T10:00")
    assert body["oi_baselines"]["day"]["elapsed_label"].startswith("~")


async def test_chain_oi_change_null_when_no_earlier_snapshot(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM options_chain_snapshots WHERE underlying='OICHG'"))
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        await app.state.redis.delete("mdq:chain:v1:US:OICHG")
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oichg2@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            r = await c.get("/v1/market/chain?ticker=OICHG&expiry=2026-09-19", headers=h)
    body = r.json()
    assert body["contracts"][0]["oi_change"]["day"] is None
    assert body["oi_baselines"]["day"] is None
