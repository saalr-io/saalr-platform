import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.marketdata.aggregates import BarRow
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind

from datetime import datetime, timedelta, timezone


class StubAgg:
    async def get_daily_bars(self, symbol, start, end, market="US"):
        return [
            BarRow(ts=datetime(2026, 1, 2, tzinfo=timezone.utc), symbol=symbol, market=market,
                   interval="1d", open=1, high=2, low=0.5, close=1.5, volume=10),
            BarRow(ts=datetime(2026, 1, 3, tzinfo=timezone.utc), symbol=symbol, market=market,
                   interval="1d", open=1, high=2, low=0.5, close=1.6, volume=11),
        ]


class StubChainProvider:
    """Returns a new as_of each call so distinct snapshot timestamps accumulate."""

    def __init__(self) -> None:
        self._n = 0

    async def get_option_chain(self, ticker, market):
        self._n += 1
        as_of = (datetime(2026, 5, 30, 14, 30, tzinfo=timezone.utc)
                 + timedelta(hours=self._n)).isoformat()
        return RawChain(
            underlying=ticker.upper(), market=market, as_of=as_of, spot=185.0, div_yield=0.005,
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


async def test_seed_endpoints_404_when_not_dev(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.settings.auth_provider = "clerk"   # simulate non-dev deployment
        async with _client(app) as c:
            rb = await c.post("/v1/dev/seed/bars", json={"ticker": "AAPL", "days": 30})
            rc = await c.post("/v1/dev/seed/chain", json={"ticker": "AAPL"})
    assert rb.status_code == 404
    assert rc.status_code == 404


async def test_seed_bars_backfills(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol='ZZZ'"))
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.aggregates_provider = StubAgg()
        async with _client(app) as c:
            r = await c.post("/v1/dev/seed/bars", json={"ticker": "ZZZ", "days": 30})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "ZZZ"
    assert body["rows_upserted"] == 2
    async with admin_engine.begin() as conn:
        n = (await conn.execute(
            text("SELECT count(*) FROM bars WHERE symbol='ZZZ'"))).scalar_one()
    assert n == 2


async def test_seed_chain_accumulates_snapshots(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM options_chain_snapshots WHERE underlying='ZZZ'"))
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubChainProvider()
        app.state.rate_provider = StubRates()
        await app.state.redis.delete("mdq:chain:v1:US:ZZZ")
        async with _client(app) as c:
            r1 = await c.post("/v1/dev/seed/chain", json={"ticker": "ZZZ"})
            r2 = await c.post("/v1/dev/seed/chain", json={"ticker": "ZZZ"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["total_snapshots"] == 2   # two distinct ts captured
    async with admin_engine.begin() as conn:
        n = (await conn.execute(text(
            "SELECT count(DISTINCT ts) FROM options_chain_snapshots WHERE underlying='ZZZ'"
        ))).scalar_one()
    assert n == 2
