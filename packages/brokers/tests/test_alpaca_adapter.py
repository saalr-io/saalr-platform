from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

pytest.importorskip("alpaca")  # the whole file is skipped unless the alpaca extra is installed

from alpaca.trading.requests import (  # noqa: E402
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)

from saalr_brokers.alpaca import AlpacaAdapter  # noqa: E402
from saalr_brokers.types import BrokerOrder  # noqa: E402


class _Order:
    def __init__(self, **kw):
        self.id = kw.get("id", "al-1")
        self.status = kw.get("status", "accepted")
        self.qty = kw.get("qty", "10")
        self.filled_qty = kw.get("filled_qty", "0")
        self.filled_avg_price = kw.get("filled_avg_price")
        self.side = kw.get("side", "buy")
        self.symbol = kw.get("symbol", "AAPL")
        self.client_order_id = kw.get("client_order_id")
        self.rejected_reason = kw.get("rejected_reason")


class _Position:
    symbol, qty, avg_entry_price, market_value, unrealized_pl = "AAPL", "10", "50", "500", "0"


class _Account:
    buying_power = "100000"


class _StubClient:
    def __init__(self, order=None, orders=None):
        self._order = order or _Order()
        self._orders = orders if orders is not None else [self._order]
        self.last_req = None
        self.cancelled = None
        self.orders_req = None

    def submit_order(self, req):
        self.last_req = req
        return self._order

    def cancel_order_by_id(self, oid):
        self.cancelled = oid

    def get_orders(self, req=None):
        self.orders_req = req
        return self._orders

    def get_all_positions(self):
        return [_Position()]

    def get_account(self):
        return _Account()


def _adapter(stub):
    return AlpacaAdapter("k", "s", is_paper=True, client=stub)


def _eq(**kw):
    base = dict(symbol="AAPL", side="buy", qty=10, order_type="market")
    base.update(kw)
    return BrokerOrder(**base)


async def test_submit_market_equity_maps_request_and_idempotency():
    stub = _StubClient(_Order(id="al-9", status="accepted"))
    res = await _adapter(stub).submit_order(_eq(), "idem-1")
    assert isinstance(stub.last_req, MarketOrderRequest)
    assert stub.last_req.symbol == "AAPL" and int(stub.last_req.qty) == 10
    assert stub.last_req.client_order_id == "idem-1"
    assert res.broker_order_id == "al-9" and res.status == "submitted"


async def test_submit_limit_stop_stoplimit_request_types():
    stub = _StubClient()
    a = _adapter(stub)
    await a.submit_order(_eq(order_type="limit", limit_price=Decimal("52")), "k")
    assert isinstance(stub.last_req, LimitOrderRequest) and float(stub.last_req.limit_price) == 52.0
    await a.submit_order(_eq(order_type="stop", stop_price=Decimal("49")), "k2")
    assert isinstance(stub.last_req, StopOrderRequest) and float(stub.last_req.stop_price) == 49.0
    await a.submit_order(_eq(order_type="stop_limit", limit_price=Decimal("52"), stop_price=Decimal("49")), "k3")
    assert isinstance(stub.last_req, StopLimitOrderRequest)


async def test_submit_option_uses_occ_symbol():
    stub = _StubClient()
    await _adapter(stub).submit_order(
        _eq(option_type="CALL", strike=Decimal("100"), expiry=date(2025, 6, 20)), "k"
    )
    assert stub.last_req.symbol == "AAPL250620C00100000"


async def test_rejected_status_maps_to_rejected():
    stub = _StubClient(_Order(status="rejected", rejected_reason="insufficient buying power"))
    res = await _adapter(stub).submit_order(_eq(), "k")
    assert res.status == "rejected" and res.rejected_reason == "insufficient buying power"


async def test_get_orders_normalizes_and_maps_status():
    stub = _StubClient(orders=[_Order(id="al-2", status="filled", filled_qty="10", filled_avg_price="50.25")])
    rows = await _adapter(stub).get_orders()
    assert rows[0]["broker_order_id"] == "al-2" and rows[0]["status"] == "filled"
    assert rows[0]["filled_avg_price"] == Decimal("50.25") and rows[0]["filled_qty"] == 10


async def test_get_orders_passes_since_and_all_status():
    from alpaca.trading.enums import QueryOrderStatus

    stub = _StubClient(orders=[])
    since = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    await _adapter(stub).get_orders(since)
    # reconciliation needs status=ALL (closed orders too) + incremental after=since
    assert stub.orders_req.status == QueryOrderStatus.ALL
    assert stub.orders_req.after == since


async def test_get_positions_and_balance():
    a = _adapter(_StubClient())
    pos = await a.get_positions()
    assert pos[0].symbol == "AAPL" and pos[0].qty == 10 and pos[0].avg_price == Decimal("50")
    assert await a.get_account_balance() == Decimal("100000")


async def test_cancel_and_stream():
    stub = _StubClient()
    a = _adapter(stub)
    assert await a.cancel_order("al-1") is True and stub.cancelled == "al-1"
    with pytest.raises(NotImplementedError):
        async for _ in a.stream_executions():
            pass


@pytest.mark.skipif(
    not (os.environ.get("ALPACA_PAPER_KEY") and os.environ.get("ALPACA_PAPER_SECRET")),
    reason="set ALPACA_PAPER_KEY/ALPACA_PAPER_SECRET to run the live Alpaca paper smoke",
)
async def test_alpaca_paper_live_smoke():
    a = AlpacaAdapter(os.environ["ALPACA_PAPER_KEY"], os.environ["ALPACA_PAPER_SECRET"], is_paper=True)
    bal = await a.get_account_balance()
    assert isinstance(bal, Decimal) and bal >= 0
