from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import httpx

from saalr_api.main import create_app
from saalr_brokers.types import BrokerOrderResult
from saalr_core.db.session import tenant_session
from saalr_core.oms import repo as core_repo
from saalr_core.oms.reconcile import reconcile_account

NOW = datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class _StubAlpaca:
    """Submits as 'submitted'; get_orders returns whatever rows the test sets."""
    def __init__(self):
        self.rows = []

    async def get_account_balance(self):
        return Decimal("100000")

    async def submit_order(self, order, idempotency_key):
        return BrokerOrderResult("brk-1", "submitted")

    async def get_orders(self, since=None):
        return self.rows


def _row(status, filled_qty, avg, broker_order_id="brk-1"):
    return {"broker_order_id": broker_order_id, "status": status, "symbol": "AAPL",
            "qty": 10, "side": "buy", "filled_qty": filled_qty,
            "filled_avg_price": Decimal(str(avg)) if avg is not None else None,
            "client_order_id": None}


async def _seed_submitted_order(app, h, key):
    """Create an alpaca account + a resting 'submitted' order via the API; return (account_id, order_id, tenant_id)."""
    stub = _StubAlpaca()
    app.state.alpaca_adapter_factory = lambda account: stub
    async with _client(app) as c:
        acct = (await c.post("/v1/broker-accounts",
                json={"broker": "alpaca", "account_label": "A", "credential_ref": "env:ALPACA_PAPER",
                      "is_paper": True}, headers=h)).json()["broker_account_id"]
        r = await c.post("/v1/orders",
                         json={"broker_account_id": acct, "symbol": "AAPL", "side": "buy",
                               "qty": 10, "order_type": "market"}, headers={**h, "Idempotency-Key": key})
        assert r.json()["status"] == "submitted"
        order_id = r.json()["order_id"]
        tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
    return acct, order_id, tid


async def test_reconcile_fills_and_builds_position(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        h = {"Authorization": "Bearer dev:rec1@x.com"}
        acct, order_id, tid = await _seed_submitted_order(app, h, "r1")
        stub = _StubAlpaca()
        stub.rows = [_row("filled", 10, "50.00")]
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, UUID(acct))
            summary = await reconcile_account(s, stub, account, now=NOW)
        assert summary["filled"] == 1
        async with _client(app) as c:
            o = (await c.get(f"/v1/orders/{order_id}", headers=h)).json()
            assert o["status"] == "filled"
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert len(pos) == 1 and pos[0]["qty"] == 10 and Decimal(pos[0]["avg_entry_price"]) == Decimal("50")


async def test_reconcile_is_idempotent_on_repoll(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        h = {"Authorization": "Bearer dev:rec2@x.com"}
        acct, order_id, tid = await _seed_submitted_order(app, h, "r2")
        stub = _StubAlpaca()
        stub.rows = [_row("filled", 10, "50.00")]
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, UUID(acct))
            await reconcile_account(s, stub, account, now=NOW)
        # second pass: order is now terminal/local-closed -> no new executions, position unchanged
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, UUID(acct))
            summary2 = await reconcile_account(s, stub, account, now=NOW)
        assert summary2["matched"] == 0  # no open orders left
        async with _client(app) as c:
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert pos[0]["qty"] == 10  # still 10, not 20


async def test_reconcile_partial_then_full(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        h = {"Authorization": "Bearer dev:rec3@x.com"}
        acct, order_id, tid = await _seed_submitted_order(app, h, "r3")
        stub = _StubAlpaca()
        stub.rows = [_row("partial", 4, "50.00")]
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, UUID(acct))
            s1 = await reconcile_account(s, stub, account, now=NOW)
        assert s1["partial"] == 1
        stub.rows = [_row("filled", 10, "50.00")]
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, UUID(acct))
            s2 = await reconcile_account(s, stub, account, now=NOW)
        assert s2["filled"] == 1
        async with _client(app) as c:
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert pos[0]["qty"] == 10  # 4 + 6
            assert (await c.get(f"/v1/orders/{order_id}", headers=h)).json()["status"] == "filled"


async def test_reconcile_partial_repoll_same_level_is_noop(app_sessionmaker, admin_engine):
    # A still-open partial re-polled at the SAME filled_qty must not double-record the fill:
    # delta == 0 skips the execution insert, the order stays partial, the position is unchanged.
    app = create_app()
    async with app.router.lifespan_context(app):
        h = {"Authorization": "Bearer dev:rec4@x.com"}
        acct, order_id, tid = await _seed_submitted_order(app, h, "r4")
        stub = _StubAlpaca()
        stub.rows = [_row("partial", 4, "50.00")]
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, UUID(acct))
            await reconcile_account(s, stub, account, now=NOW)
        # second pass, identical rows: order is still partial (open), no new fill
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, UUID(acct))
            s2 = await reconcile_account(s, stub, account, now=NOW)
        assert s2["matched"] == 1 and s2["partial"] == 0  # matched, but no new fill recorded
        async with _client(app) as c:
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert pos[0]["qty"] == 4  # still 4, not 8
            # first pass already advanced submitted -> partial; second pass leaves it there
            assert (await c.get(f"/v1/orders/{order_id}", headers=h)).json()["status"] == "partial"
