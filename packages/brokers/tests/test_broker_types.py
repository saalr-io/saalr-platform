from decimal import Decimal

import pytest

from saalr_brokers.base import BrokerAdapter
from saalr_brokers.types import BrokerFill, BrokerOrder, BrokerOrderResult, BrokerPosition


def test_dataclasses_construct():
    o = BrokerOrder(symbol="AAPL", side="buy", qty=1, order_type="market")
    assert o.time_in_force == "day" and o.limit_price is None
    r = BrokerOrderResult(broker_order_id="x", status="submitted")
    assert r.rejected_reason is None
    f = BrokerFill(broker_order_id="x", broker_execution_id="e", qty=1, price=Decimal("1.5"))
    assert f.commission == Decimal(0)
    p = BrokerPosition("AAPL", 1, Decimal("1"), Decimal("1"), Decimal("0"))
    assert p.qty == 1


def test_broker_adapter_is_abstract():
    with pytest.raises(TypeError):
        BrokerAdapter()  # cannot instantiate an ABC with abstract methods
