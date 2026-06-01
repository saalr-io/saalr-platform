from decimal import Decimal

import httpx

from saalr_api.main import create_app
from saalr_brokers.alpaca import BrokerError
from saalr_brokers.credentials import CredentialError
from saalr_brokers.types import BrokerOrderResult


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_create_alpaca_account(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp1@x.com"}
            r = await c.post("/v1/broker-accounts",
                             json={"broker": "alpaca", "account_label": "Live-ish",
                                   "credential_ref": "env:ALPACA_PAPER", "is_paper": True}, headers=h)
            assert r.status_code == 200, r.text
            assert r.json()["broker"] == "alpaca"
            assert "credential_ref" not in r.json()  # the credential pointer never leaks in the response


async def test_create_alpaca_account_requires_credential_ref(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp2@x.com"}
            r = await c.post("/v1/broker-accounts",
                             json={"broker": "alpaca", "account_label": "x"}, headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "VALIDATION_MISSING_CREDENTIAL_REF"


class _StubAlpaca:
    def __init__(self, *, balance=Decimal("100000"), result=None, raise_submit=None):
        self._balance = balance
        self._result = result or BrokerOrderResult("alp-1", "submitted")
        self._raise_submit = raise_submit
        self.cancelled = None

    async def get_account_balance(self):
        return self._balance

    async def submit_order(self, order, idempotency_key):
        if self._raise_submit:
            raise self._raise_submit
        return self._result

    async def cancel_order(self, broker_order_id):
        self.cancelled = broker_order_id
        return True


async def _alpaca_account(c, h, ref="env:ALPACA_PAPER"):
    r = await c.post("/v1/broker-accounts",
                     json={"broker": "alpaca", "account_label": "A", "credential_ref": ref,
                           "is_paper": True}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["broker_account_id"]


def _order(acct, **kw):
    base = {"broker_account_id": acct, "symbol": "AAPL", "side": "buy", "qty": 1, "order_type": "market"}
    base.update(kw)
    return base


async def test_alpaca_order_rests_submitted(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.alpaca_adapter_factory = lambda account: _StubAlpaca()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp3@x.com"}
            acct = await _alpaca_account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "a1"})
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "submitted" and r.json()["broker_order_id"] == "alp-1"
            assert (await c.get("/v1/positions", headers=h)).json()["positions"] == []


async def test_alpaca_reject_maps_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.alpaca_adapter_factory = lambda account: _StubAlpaca(
            result=BrokerOrderResult("alp-2", "rejected", "insufficient buying power"))
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp4@x.com"}
            acct = await _alpaca_account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "a2"})
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "BROKER_REJECTED"


async def test_alpaca_bad_credentials_502(app_sessionmaker, admin_engine):
    def _factory(account):
        raise CredentialError("missing env var")

    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.alpaca_adapter_factory = _factory
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp5@x.com"}
            acct = await _alpaca_account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "a3"})
            assert r.status_code == 502
            assert r.json()["detail"]["error"]["code"] == "BROKER_CREDENTIALS_UNAVAILABLE"


async def test_alpaca_broker_error_returns_502_and_persists_no_order(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.alpaca_adapter_factory = lambda account: _StubAlpaca(raise_submit=BrokerError("boom"))
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp6@x.com"}
            acct = await _alpaca_account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "a4"})
            assert r.status_code == 502
            assert r.json()["detail"]["error"]["code"] == "BROKER_UNAVAILABLE"
            # the request-level transaction rolls the pending insert back -> no order persists (retriable)
            assert (await c.get("/v1/orders", headers=h)).json()["orders"] == []
