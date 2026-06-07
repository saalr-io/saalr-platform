from __future__ import annotations

from datetime import date
from decimal import Decimal

from saalr_brokers.tradier import (
    build_order_form, map_status, parse_balance, parse_orders, parse_positions,
)
from saalr_brokers.types import BrokerOrder


def test_build_order_form_equity_limit():
    o = BrokerOrder(symbol="AAPL", side="buy", qty=3, order_type="limit",
                    limit_price=Decimal("100.50"), time_in_force="day")
    f = build_order_form(o, "idem-1")
    assert f == {
        "class": "equity", "symbol": "AAPL", "side": "buy", "quantity": "3",
        "type": "limit", "duration": "day", "price": "100.50", "tag": "idem-1",
    }


def test_build_order_form_option_open_side_and_occ():
    o = BrokerOrder(symbol="AAPL", side="sell", qty=1, order_type="market",
                    option_type="CALL", strike=Decimal("180"), expiry=date(2026, 9, 18),
                    time_in_force="day")
    f = build_order_form(o, "idem-2")
    assert f["class"] == "option"
    assert f["symbol"] == "AAPL"
    assert f["option_symbol"] == "AAPL260918C00180000"
    assert f["side"] == "sell_to_open"          # sell -> sell_to_open (open-only)
    assert f["type"] == "market" and f["duration"] == "day"
    assert "price" not in f                       # market has no price


def test_map_status():
    assert map_status("filled") == "filled"
    assert map_status("partially_filled") == "partial"
    assert map_status("canceled") == "cancelled"
    assert map_status("rejected") == "rejected"
    assert map_status("open") == "submitted"
    assert map_status("ok") == "submitted"
    assert map_status("something-new") == "submitted"


def test_parse_orders_single_object_and_tag():
    body = {"orders": {"order": {
        "id": 123, "status": "filled", "symbol": "AAPL", "quantity": 3, "side": "buy",
        "exec_quantity": 3, "avg_fill_price": 100.5, "tag": "idem-1"}}}
    rows = parse_orders(body)
    assert rows == [{
        "broker_order_id": "123", "status": "filled", "symbol": "AAPL", "qty": 3,
        "side": "buy", "filled_qty": 3, "filled_avg_price": Decimal("100.5"),
        "client_order_id": "idem-1",
    }]


def test_parse_orders_empty():
    assert parse_orders({"orders": "null"}) == []


def test_parse_positions():
    body = {"positions": {"position": {"symbol": "AAPL", "quantity": 2, "cost_basis": 200.0}}}
    ps = parse_positions(body)
    assert ps[0].symbol == "AAPL" and ps[0].qty == 2
    assert ps[0].avg_price == Decimal("100")
    assert ps[0].market_value == Decimal("200.0") and ps[0].unrealized_pnl == Decimal(0)


def test_parse_balance_prefers_option_buying_power():
    assert parse_balance({"balances": {"option_buying_power": 5000.0, "total_cash": 1000.0}}) == Decimal("5000.0")
    assert parse_balance({"balances": {"total_cash": 1000.0}}) == Decimal("1000.0")
