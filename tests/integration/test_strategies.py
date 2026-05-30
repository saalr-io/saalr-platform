import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind


class StubProvider:
    async def get_option_chain(self, ticker, market):
        return RawChain(
            underlying=ticker.upper(), market=market, as_of="2026-05-30T14:30:00+00:00",
            spot=100.0, div_yield=0.0,
            contracts=[
                RawContract("2026-12-18", 100.0, OptionKind.CALL, 5.9, 6.1, 6.0, 10, 50,
                            0.25, 0.55, 0.02, -0.05, 0.11),
                RawContract("2026-12-18", 110.0, OptionKind.CALL, 1.9, 2.1, 2.0, 10, 50,
                            0.24, 0.30, 0.02, -0.04, 0.10),
            ],
        )


class StubRates:
    source_name = "fred"

    async def get_curve(self):
        return YieldCurve("2026-05-29", [(1 / 12, 0.04), (2.0, 0.045)])


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
                           {"t": tenant_id})


_OPTION = {"kind": "option", "option_type": "CALL", "side": "BUY", "strike": 100,
           "expiry": "2026-12-18", "qty": 1, "entry_price": 6.0}


async def test_crud_lifecycle_and_rls(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:s1@x.com"}
            body = {"name": "My Spread", "config": {"underlying": "AAPL", "legs": [_OPTION]}}
            r = await c.post("/v1/strategies", json=body, headers=h)
            assert r.status_code == 200
            sid = r.json()["strategy_id"]
            assert r.json()["state"] == "draft"

            assert (await c.get(f"/v1/strategies/{sid}", headers=h)).status_code == 200
            lst = (await c.get("/v1/strategies", headers=h)).json()
            assert any(s["strategy_id"] == sid for s in lst["strategies"])

            ok = await c.post(f"/v1/strategies/{sid}/transition",
                              json={"target_state": "backtested"}, headers=h)
            assert ok.status_code == 200 and ok.json()["state"] == "backtested"
            bad = await c.post(f"/v1/strategies/{sid}/transition",
                               json={"target_state": "live"}, headers=h)
            assert bad.status_code == 409
            assert bad.json()["detail"]["error"]["code"] == "STRATEGY_ILLEGAL_TRANSITION"

            patch = await c.patch(f"/v1/strategies/{sid}", json={"name": "x"}, headers=h)
            assert patch.status_code == 409

            other = await c.get(f"/v1/strategies/{sid}",
                                headers={"Authorization": "Bearer dev:s2@x.com"})
            assert other.status_code == 404


async def test_templates_list_and_build(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:s3@x.com"}
            t = (await c.get("/v1/strategies/templates", headers=h)).json()
            assert any(x["key"] == "iron_condor" for x in t["templates"])
            b = await c.post("/v1/strategies/templates/bull_call_spread/build",
                             json={"underlying": "AAPL", "expiry": "2026-12-18",
                                   "atm_strike": 100, "width": 10}, headers=h)
            assert b.status_code == 200 and len(b.json()["legs"]) == 2


async def test_analyze_pure_free_and_live_gating(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:s4@x.com"}
            cfg = {"config": {"underlying": "AAPL", "legs": [_OPTION]}, "live": False}
            pure = await c.post("/v1/strategies/analyze", json=cfg, headers=h)
            assert pure.status_code == 200
            assert pure.json()["unbounded_profit"] is True
            assert "net_greeks" not in pure.json()

            live_free = await c.post("/v1/strategies/analyze",
                                     json={**cfg, "live": True}, headers=h)
            assert live_free.status_code == 402

            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            live = await c.post("/v1/strategies/analyze",
                                json={**cfg, "live": True, "target_date": "2026-09-18"}, headers=h)
            assert live.status_code == 200
            body = live.json()
            assert "net_greeks" in body and "probability_of_profit" in body
            assert "target_date_curve" in body


async def test_invalid_config_422(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:s5@x.com"}
            r = await c.post("/v1/strategies", json={"name": "x",
                             "config": {"underlying": "AAPL", "legs": []}}, headers=h)
            assert r.status_code == 422
