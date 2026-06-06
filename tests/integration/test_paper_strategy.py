from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, px=50.0, n=40):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol=:s"), {"s": symbol})
        for i in range(n):
            ts = start + timedelta(days=i)
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""),
                {"ts": ts, "sym": symbol, "o": Decimal(str(px)), "h": Decimal(str(px + 1)),
                 "l": Decimal(str(px - 1)), "c": Decimal(str(px)), "v": 1000},
            )


async def _account(c, h):
    r = await c.post("/v1/broker-accounts", json={"account_label": "Practice"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["broker_account_id"]


async def test_place_strategy_skips_cash_and_fills_equity(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ps-1@x.com"}
            acct = await _account(c, h)
            body = {
                "broker_account_id": acct, "underlying": "AAPL",
                "legs": [
                    {"kind": "equity", "side": "BUY", "qty": 1},
                    {"kind": "cash", "amount": "5000"},
                ],
            }
            r = await c.post("/v1/orders/strategy", json=body, headers={**h, "Idempotency-Key": "ps1"})
            assert r.status_code == 200, r.text
            out = r.json()
            assert len(out["results"]) == 2
            kinds = {res["kind"]: res["status"] for res in out["results"]}
            assert kinds["cash"] == "skipped"
            assert kinds["equity"] == "filled"
            assert out["placed"] == 1 and out["rejected"] == 0


async def test_place_strategy_reports_a_rejected_leg(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ps-2@x.com"}
            acct = await _account(c, h)
            # leg 0 fills; leg 1 is ~$5M against the ~$100k paper balance -> rejected.
            body = {
                "broker_account_id": acct, "underlying": "AAPL",
                "legs": [
                    {"kind": "equity", "side": "BUY", "qty": 1},
                    {"kind": "equity", "side": "BUY", "qty": 100000},
                ],
            }
            r = await c.post("/v1/orders/strategy", json=body, headers={**h, "Idempotency-Key": "ps2"})
            assert r.status_code == 200, r.text
            out = r.json()
            assert out["placed"] == 1 and out["rejected"] == 1
            rej = [res for res in out["results"] if res["status"] == "rejected"][0]
            assert rej["reject_code"] == "RISK_INSUFFICIENT_BUYING_POWER"
