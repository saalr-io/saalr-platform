from datetime import datetime, timedelta, timezone

from saalr_core.strategies.promotion import PromotionDecision, evaluate_promotion

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)


def _eval(state="paper", brokers=2, first=NOW - timedelta(days=20), step_up_ok=True):
    return evaluate_promotion(state, brokers, first, NOW, step_up_ok)


def test_all_gates_pass():
    d = _eval()
    assert isinstance(d, PromotionDecision) and d.ok and d.code is None


def test_not_in_paper_fails_first():
    d = _eval(state="backtested")
    assert not d.ok and d.code == "STRATEGY_NOT_IN_PAPER"


def test_entitlement_gate():
    d = _eval(brokers=0)
    assert not d.ok and d.code == "ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO"


def test_no_paper_orders_is_insufficient():
    d = _eval(first=None)
    assert not d.ok and d.code == "STRATEGY_INSUFFICIENT_PAPER_HISTORY"
    assert d.details == {"days_traded": 0, "days_required": 14}


def test_thirteen_days_insufficient():
    d = _eval(first=NOW - timedelta(days=13, hours=23))
    assert not d.ok and d.code == "STRATEGY_INSUFFICIENT_PAPER_HISTORY"
    assert d.details["days_traded"] == 13


def test_exactly_fourteen_days_ok():
    d = _eval(first=NOW - timedelta(days=14))
    assert d.ok and d.code is None


def test_naive_datetimes_rejected():
    import pytest

    naive = datetime(2026, 6, 2, 12, 0)
    with pytest.raises(ValueError):
        evaluate_promotion("paper", 2, None, naive, True)
    with pytest.raises(ValueError):
        evaluate_promotion("paper", 2, naive, NOW, True)


def test_missing_step_up_is_mfa_required():
    d = _eval(step_up_ok=False)
    assert not d.ok and d.code == "AUTH_MFA_REQUIRED"


def test_gate_order_entitlement_before_history():
    # free tier AND no history -> entitlement reported first
    d = evaluate_promotion("paper", 0, None, NOW, False)
    assert d.code == "ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO"
