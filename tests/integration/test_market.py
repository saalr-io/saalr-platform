import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind


class StubProvider:
    def __init__(self):
        self.calls = 0

    async def get_option_chain(self, ticker, market):
        self.calls += 1
        return RawChain(
            underlying=ticker.upper(), market=market, as_of="2026-05-30T14:30:00+00:00",
            spot=185.0, div_yield=0.005,
            contracts=[
                RawContract("2026-09-19", 180.0, OptionKind.CALL, 9.0, 9.2, 9.1, 100, 500,
                            0.26, 0.58, 0.02, -0.05, 0.11),
                RawContract("2026-09-19", 180.0, OptionKind.PUT, 5.0, 5.2, 5.1, 80, 400,
                            0.27, -0.42, 0.02, -0.04, 0.11),
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
        await conn.execute(
            text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
            {"t": tenant_id},
        )


async def test_iv_surface_requires_pro(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            r = await c.get("/v1/market/iv-surface?ticker=AAPL",
                            headers={"Authorization": "Bearer dev:free@x.com"})
    assert r.status_code == 402
    assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO"


async def test_iv_surface_shape_for_pro(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            r = await c.get("/v1/market/iv-surface?ticker=AAPL", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["spot"] == 185.0
    assert body["data_provider"] == "massive"
    assert body["model"] == "bsm"
    exp = body["expiries"][0]
    assert exp["expiry"] == "2026-09-19"
    strike = exp["strikes"][0]
    assert strike["strike"] == 180.0
    assert strike["iv_call"] is not None and strike["iv_put"] is not None


async def test_chain_persists_and_caches(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE options_chain_snapshots"))
    app = create_app()
    async with app.router.lifespan_context(app):
        stub = StubProvider()
        app.state.market_provider = stub
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pro2@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await app.state.redis.delete("mdq:chain:US:AAPL")
            r1 = await c.get("/v1/market/chain?ticker=AAPL", headers=h)
            r2 = await c.get("/v1/market/chain?ticker=AAPL", headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert stub.calls == 1  # second call served from cache
    rows = r1.json()["contracts"]
    assert rows[0]["ours"]["iv"] is not None
    assert "vendor" in rows[0]
    async with admin_engine.begin() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM options_chain_snapshots"))).scalar_one()
    assert n == 2


async def test_unknown_ticker_404(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pro3@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            r = await c.get("/v1/market/iv-surface?ticker=123", headers=h)
    assert r.status_code == 404
