from datetime import datetime, timezone

from saalr_api.billing.reducer import SubscriptionState, apply_subscription_event, _FAR_FUTURE

PRICE_TO_TIER = {"price_pro": "pro", "price_premium": "premium"}

FREE = SubscriptionState(
    tier="free", status="active", provider="manual",
    provider_subscription_id=None,
    current_period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    current_period_end=datetime(2126, 1, 1, tzinfo=timezone.utc),
    cancel_at_period_end=False,
)


def _ts(y=2026, m=6, d=3):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


def test_checkout_completed_pro_with_trial_is_trialing_pro():
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "customer": "cus_1", "subscription": "sub_1",
            "metadata": {"tenant_id": "t1"},
            "line_items": None,
        }},
    }
    sub = {
        "id": "sub_1", "status": "trialing",
        "items": {"data": [{"price": {"id": "price_pro"}}]},
        "current_period_start": _ts(), "current_period_end": _ts(m=7),
        "cancel_at_period_end": False,
    }
    out = apply_subscription_event(FREE, event, PRICE_TO_TIER, subscription=sub)
    assert out.tier == "pro"
    assert out.status == "trialing"
    assert out.provider == "stripe"
    assert out.provider_subscription_id == "sub_1"


def test_subscription_updated_refreshes_status_and_tier():
    cur = SubscriptionState(**{**FREE.__dict__, "tier": "pro", "status": "trialing",
                               "provider": "stripe", "provider_subscription_id": "sub_1"})
    event = {"type": "customer.subscription.updated", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "active",
        "items": {"data": [{"price": {"id": "price_premium"}}]},
        "current_period_start": _ts(), "current_period_end": _ts(m=7),
        "cancel_at_period_end": True,
    }}}
    out = apply_subscription_event(cur, event, PRICE_TO_TIER)
    assert out.tier == "premium"
    assert out.status == "active"
    assert out.cancel_at_period_end is True


def test_subscription_deleted_reverts_to_free():
    cur = SubscriptionState(**{**FREE.__dict__, "tier": "pro", "status": "active",
                               "provider": "stripe", "provider_subscription_id": "sub_1"})
    event = {"type": "customer.subscription.deleted", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "canceled"}}}
    out = apply_subscription_event(cur, event, PRICE_TO_TIER)
    assert out.tier == "free"
    assert out.status == "active"
    assert out.provider == "manual"
    assert out.provider_subscription_id is None
    assert out.current_period_end == _FAR_FUTURE


def test_invoice_payment_failed_is_past_due():
    cur = SubscriptionState(**{**FREE.__dict__, "tier": "pro", "status": "active"})
    event = {"type": "invoice.payment_failed", "data": {"object": {"customer": "cus_1"}}}
    out = apply_subscription_event(cur, event, PRICE_TO_TIER)
    assert out.status == "past_due"
    assert out.tier == "pro"  # tier unchanged; entitlements only key off active/trialing


def test_invoice_paid_is_active():
    cur = SubscriptionState(**{**FREE.__dict__, "tier": "pro", "status": "past_due"})
    event = {"type": "invoice.paid", "data": {"object": {"customer": "cus_1"}}}
    out = apply_subscription_event(cur, event, PRICE_TO_TIER)
    assert out.status == "active"


def test_unknown_event_is_noop():
    event = {"type": "customer.updated", "data": {"object": {"customer": "cus_1"}}}
    out = apply_subscription_event(FREE, event, PRICE_TO_TIER)
    assert out == FREE
