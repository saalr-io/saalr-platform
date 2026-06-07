from decimal import Decimal

from saalr_core.oms.risk import estimate_cost, run_gates
from saalr_core.oms.types import OrderRequest, RiskContext


def _o(**kw):
    base = dict(side="buy", qty=10, order_type="market", symbol="AAPL")
    base.update(kw)
    return OrderRequest(**base)


def _ctx(**kw):
    base = dict(account_active=True, strategy_state="paper",
               available_balance=Decimal("100000"), estimated_cost=Decimal("500"),
               recent_order_count=0, rate_limit=None)
    base.update(kw)
    return RiskContext(**base)


def test_clean_order_passes():
    assert run_gates(_o(), _ctx()).ok is True


def test_invalid_quantity():
    d = run_gates(_o(qty=0), _ctx())
    assert d.ok is False and d.code == "RISK_INVALID_QUANTITY"


def test_limit_without_price():
    d = run_gates(_o(order_type="limit"), _ctx())
    assert d.code == "RISK_MISSING_LIMIT_PRICE"


def test_stop_without_price():
    d = run_gates(_o(order_type="stop"), _ctx())
    assert d.code == "RISK_MISSING_STOP_PRICE"


def test_inactive_account():
    assert run_gates(_o(), _ctx(account_active=False)).code == "RISK_ACCOUNT_INACTIVE"


def test_strategy_not_executable():
    assert run_gates(_o(), _ctx(strategy_state="draft")).code == "RISK_STRATEGY_NOT_EXECUTABLE"
    # no attached strategy is fine
    assert run_gates(_o(), _ctx(strategy_state=None)).ok is True


def test_insufficient_buying_power():
    d = run_gates(_o(), _ctx(estimated_cost=Decimal("200000")))
    assert d.code == "RISK_INSUFFICIENT_BUYING_POWER"
    # a sell does not consume cash
    assert run_gates(_o(side="sell"), _ctx(estimated_cost=Decimal("200000"))).ok is True


def test_rate_limit():
    assert run_gates(_o(), _ctx(recent_order_count=10, rate_limit=10)).code == "RISK_RATE_LIMIT_EXCEEDED"
    assert run_gates(_o(), _ctx(recent_order_count=9, rate_limit=10)).ok is True


def test_first_failure_wins_structural_before_buying_power():
    # qty=0 AND cost>balance -> structural reported first
    d = run_gates(_o(qty=0), _ctx(estimated_cost=Decimal("999999")))
    assert d.code == "RISK_INVALID_QUANTITY"


def test_estimate_cost_option_vs_equity():
    assert estimate_cost(_o(option_type="CALL", qty=1), Decimal("2.5")) == Decimal("250.0")
    assert estimate_cost(_o(qty=10), Decimal("50")) == Decimal("500")
