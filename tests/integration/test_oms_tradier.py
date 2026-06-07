import httpx
from decimal import Decimal

from saalr_api.main import create_app
from saalr_brokers.types import BrokerOrderResult


class StubTradier:
    async def get_account_balance(self):
        return Decimal("100000")

    async def submit_order(self, order, idempotency_key):
        return BrokerOrderResult("T-1", "submitted")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_create_tradier_account_and_place_routes_to_tradier(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.adapter_factories = {"tradier": lambda account: StubTradier()}
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:tradier@x.com"}
            acct = (await c.post("/v1/broker-accounts",
                                 json={"broker": "tradier", "account_label": "T"}, headers=h)).json()
            assert acct["broker"] == "tradier"
            r = await c.post("/v1/orders", json={
                "broker_account_id": acct["broker_account_id"], "symbol": "AAPL",
                "side": "buy", "qty": 1, "order_type": "market"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "submitted"
    assert body["broker_order_id"] == "T-1"


async def test_unknown_broker_rejected_at_create(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:tradier2@x.com"}
            r = await c.post("/v1/broker-accounts",
                             json={"broker": "webull", "account_label": "W"}, headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "BROKER_NOT_SUPPORTED"
