from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, n=40, px=100.0):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol=:s"), {"s": symbol})
        for i in range(n):
            ts = start + timedelta(days=i)
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:s,'US','1d',:c,:c,:c,:c,1000)"""),
                {"ts": ts, "s": symbol, "c": Decimal(str(px))},
            )


async def _account(c, h):
    r = await c.post("/v1/broker-accounts", json={"account_label": "Paper"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["broker_account_id"]


def _order(acct, **kw):
    base = {"broker_account_id": acct, "symbol": "AAPL", "side": "buy", "qty": 10, "order_type": "market"}
    base.update(kw)
    return base


async def test_market_buy_fills_and_persists(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms1@x.com"}
            acct = await _account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "k1"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "filled" and body["broker_order_id"]
            # a position appears
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert len(pos) == 1 and pos[0]["qty"] == 10 and Decimal(pos[0]["avg_entry_price"]) == Decimal("50")


async def test_idempotent_order(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms2@x.com"}
            acct = await _account(c, h)
            hk = {**h, "Idempotency-Key": "dup"}
            r1 = await c.post("/v1/orders", json=_order(acct), headers=hk)
            r2 = await c.post("/v1/orders", json=_order(acct), headers=hk)
            assert r1.json()["order_id"] == r2.json()["order_id"]
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert pos[0]["qty"] == 10  # not 20 — one fill


async def test_insufficient_buying_power_rejected(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms3@x.com"}
            acct = await _account(c, h)
            r = await c.post("/v1/orders", json=_order(acct, qty=100000),
                             headers={**h, "Idempotency-Key": "k"})
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "RISK_INSUFFICIENT_BUYING_POWER"


async def test_no_market_data_rejected(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms4@x.com"}
            acct = await _account(c, h)
            async with admin_engine.begin() as conn:
                await conn.execute(text("DELETE FROM bars WHERE symbol='ZZZZ'"))
            r = await c.post("/v1/orders", json=_order(acct, symbol="ZZZZ"),
                             headers={**h, "Idempotency-Key": "k"})
            assert r.status_code == 422 and r.json()["detail"]["error"]["code"] == "RISK_NO_MARKET_DATA"


async def test_non_marketable_limit_rests_and_cancels(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms5@x.com"}
            acct = await _account(c, h)
            r = await c.post("/v1/orders",
                             json=_order(acct, order_type="limit", limit_price="48"),
                             headers={**h, "Idempotency-Key": "k"})
            assert r.json()["status"] == "submitted"  # 50 > 48 buy limit -> rests
            oid = r.json()["order_id"]
            assert (await c.get("/v1/positions", headers=h)).json()["positions"] == []
            cancel = await c.post(f"/v1/orders/{oid}/cancel", headers=h)
            assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled"
            # cancelling again -> 409
            assert (await c.post(f"/v1/orders/{oid}/cancel", headers=h)).status_code == 409


async def test_rls_isolation(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            ha = {"Authorization": "Bearer dev:oms-a@x.com"}
            hb = {"Authorization": "Bearer dev:oms-b@x.com"}
            acct = await _account(c, ha)
            r = await c.post("/v1/orders", json=_order(acct), headers={**ha, "Idempotency-Key": "k"})
            oid = r.json()["order_id"]
            assert (await c.get(f"/v1/orders/{oid}", headers=hb)).status_code == 404
            assert (await c.get("/v1/positions", headers=hb)).json()["positions"] == []


async def test_audit_row_written(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms6@x.com"}
            acct = await _account(c, h)
            await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "k"})
    async with admin_engine.begin() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM audit_log WHERE action='order.filled'"))).scalar_one()
    assert n >= 1
