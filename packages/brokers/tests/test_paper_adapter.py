from decimal import Decimal

from saalr_brokers.paper import PaperBrokerAdapter
from saalr_brokers.types import BrokerOrder


def _mark(price):
    return lambda order: Decimal(str(price))


def _eq(symbol="AAPL", side="buy", qty=10, order_type="market", **kw):
    return BrokerOrder(symbol=symbol, side=side, qty=qty, order_type=order_type, **kw)


async def test_market_buy_fills_at_mark_and_moves_cash_and_position():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    res = await a.submit_order(_eq(qty=10), "k1")
    assert res.status == "submitted"
    assert await a.get_account_balance() == Decimal("100000") - Decimal("50") * 10  # equity mult 1
    pos = await a.get_positions()
    assert len(pos) == 1 and pos[0].qty == 10 and pos[0].avg_price == Decimal("50")
    orders = await a.get_orders()
    assert orders[0]["status"] == "filled" and orders[0]["fill_price"] == Decimal("50")


async def test_option_fill_uses_100_multiplier():
    a = PaperBrokerAdapter(Decimal("100000"), _mark("2.50"))
    await a.submit_order(_eq(symbol="AAPL", qty=1, option_type="CALL", strike=Decimal("100")), "k1")
    assert await a.get_account_balance() == Decimal("100000") - Decimal("2.50") * 1 * 100


async def test_marketable_limit_fills_at_limit_not_mark():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    await a.submit_order(_eq(order_type="limit", side="buy", limit_price=Decimal("52")), "k1")  # mark 50 <= 52
    orders = await a.get_orders()
    assert orders[0]["status"] == "filled" and orders[0]["fill_price"] == Decimal("52")


async def test_non_marketable_limit_day_rests_open():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    res = await a.submit_order(_eq(order_type="limit", side="buy", limit_price=Decimal("48")), "k1")  # 50 > 48
    assert res.status == "submitted"
    orders = await a.get_orders()
    assert orders[0]["status"] == "open"
    assert await a.get_positions() == []


async def test_non_marketable_ioc_is_cancelled():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    await a.submit_order(_eq(order_type="limit", side="buy", limit_price=Decimal("48"), time_in_force="ioc"), "k1")
    assert (await a.get_orders())[0]["status"] == "cancelled"


async def test_stop_buy_triggers_when_mark_crosses():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    await a.submit_order(_eq(order_type="stop", side="buy", stop_price=Decimal("49")), "k1")  # 50 >= 49 -> trigger
    assert (await a.get_orders())[0]["status"] == "filled"


async def test_cancel_open_then_filled():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    r = await a.submit_order(_eq(order_type="limit", side="buy", limit_price=Decimal("48")), "k1")  # open
    assert await a.cancel_order(r.broker_order_id) is True
    assert (await a.get_orders())[0]["status"] == "cancelled"
    r2 = await a.submit_order(_eq(qty=1), "k2")  # filled
    assert await a.cancel_order(r2.broker_order_id) is False


async def test_idempotent_submit_does_not_double_fill():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    r1 = await a.submit_order(_eq(qty=10), "same")
    r2 = await a.submit_order(_eq(qty=10), "same")
    assert r1 == r2
    assert await a.get_account_balance() == Decimal("100000") - Decimal("500")  # only one fill
    assert (await a.get_positions())[0].qty == 10


async def test_buy_then_partial_sell_nets_position_and_cash():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    await a.submit_order(_eq(side="buy", qty=10), "k1")
    await a.submit_order(_eq(side="sell", qty=4), "k2")
    pos = await a.get_positions()
    assert pos[0].qty == 6 and pos[0].avg_price == Decimal("50")
    assert await a.get_account_balance() == Decimal("100000") - Decimal("500") + Decimal("200")
