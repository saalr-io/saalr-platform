from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from saalr_brokers.tradier import TradierAdapter
from saalr_brokers.types import BrokerOrder


def _adapter(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                               base_url="https://sandbox.tradier.com/v1")
    return TradierAdapter("tok", "VA123", is_paper=True, client=client)


@pytest.mark.asyncio
async def test_submit_order_success():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"order": {"id": 42, "status": "ok"}})

    res = await _adapter(handler).submit_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=1, order_type="market"), "idem-9")
    assert res.broker_order_id == "42" and res.status == "submitted"
    assert "/accounts/VA123/orders" in seen["url"]
    assert "class=equity" in seen["body"] and "tag=idem-9" in seen["body"]


@pytest.mark.asyncio
async def test_submit_order_rejected():
    def handler(req):
        return httpx.Response(400, json={"errors": {"error": ["insufficient buying power"]}})

    res = await _adapter(handler).submit_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=1, order_type="market"), "idem-10")
    assert res.status == "rejected"
    assert "insufficient" in (res.rejected_reason or "")


@pytest.mark.asyncio
async def test_cancel_order():
    def handler(req):
        assert req.method == "DELETE"
        return httpx.Response(200, json={"order": {"id": 42, "status": "ok"}})

    assert await _adapter(handler).cancel_order("42") is True


@pytest.mark.asyncio
async def test_get_orders_and_balance():
    def handler(req):
        if req.url.path.endswith("/orders"):
            return httpx.Response(200, json={"orders": {"order": {
                "id": 1, "status": "filled", "symbol": "AAPL", "quantity": 1, "side": "buy",
                "exec_quantity": 1, "avg_fill_price": 10.0, "tag": "t1"}}})
        return httpx.Response(200, json={"balances": {"total_cash": 1000.0}})

    a = _adapter(handler)
    orders = await a.get_orders()
    assert orders[0]["broker_order_id"] == "1" and orders[0]["status"] == "filled"
    assert await a.get_account_balance() == Decimal("1000.0")
