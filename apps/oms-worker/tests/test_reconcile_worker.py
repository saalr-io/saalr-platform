from datetime import datetime, timezone
from decimal import Decimal

import httpx

from saalr_api.main import create_app
from saalr_brokers.types import BrokerOrderResult
from oms_worker.reconcile import run_reconcile


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class _StubAlpaca:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def get_account_balance(self):
        return Decimal("100000")

    async def submit_order(self, order, idempotency_key):
        return BrokerOrderResult("brk-w1", "submitted")

    async def get_orders(self, since=None):
        return self.rows


async def test_run_reconcile_once_fills_open_order(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        stub = _StubAlpaca()
        app.state.alpaca_adapter_factory = lambda account: stub
        h = {"Authorization": "Bearer dev:wrk1@x.com"}
        async with _client(app) as c:
            acct = (await c.post("/v1/broker-accounts",
                    json={"broker": "alpaca", "account_label": "A", "credential_ref": "env:ALPACA_PAPER",
                          "is_paper": True}, headers=h)).json()["broker_account_id"]
            r = await c.post("/v1/orders",
                             json={"broker_account_id": acct, "symbol": "AAPL", "side": "buy",
                                   "qty": 10, "order_type": "market"},
                             headers={**h, "Idempotency-Key": "w1"})
            assert r.json()["status"] == "submitted"
            order_id = r.json()["order_id"]

        stub.rows = [{"broker_order_id": "brk-w1", "status": "filled", "symbol": "AAPL", "qty": 10,
                      "side": "buy", "filled_qty": 10, "filled_avg_price": Decimal("50.00"),
                      "client_order_id": None}]
        await run_reconcile(app.state.sessionmaker, admin_engine,
                            adapter_factory=lambda account: stub, once=True,
                            now=datetime(2026, 6, 1, 16, 0, tzinfo=timezone.utc))

        async with _client(app) as c:
            assert (await c.get(f"/v1/orders/{order_id}", headers=h)).json()["status"] == "filled"
