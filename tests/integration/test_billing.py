from datetime import datetime, timezone
from uuid import uuid4

import httpx  # noqa: F401
from sqlalchemy import text

from saalr_api.billing import repo, service
from saalr_api.billing.provider import StubProvider, make_payment_provider
from saalr_api.billing.reducer import SubscriptionState
from saalr_core.db.session import tenant_session


async def _seed_free_tenant(admin_engine, email="b@acme.com"):
    tenant_id, user_id = uuid4(), uuid4()
    async with admin_engine.begin() as conn:
        await conn.execute(text("INSERT INTO users (user_id, email) VALUES (:u,:e)"),
                           {"u": user_id, "e": email})
        await conn.execute(text(
            "INSERT INTO tenants (tenant_id, display_name, country_code) VALUES (:t,'acme','US')"),
            {"t": tenant_id})
        await conn.execute(text(
            "INSERT INTO memberships (user_id, tenant_id, role) VALUES (:u,:t,'owner')"),
            {"u": user_id, "t": tenant_id})
        await conn.execute(text(
            "INSERT INTO subscriptions (subscription_id, tenant_id, tier, status, provider, "
            "current_period_start, current_period_end) "
            "VALUES (:s,:t,'free','active','manual', now(), now()+interval '100 years')"),
            {"s": uuid4(), "t": tenant_id})
    return tenant_id


async def test_get_and_set_customer_id(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine)
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert await repo.get_customer_id(s, tenant_id) is None
        await repo.set_customer_id(s, tenant_id, "cus_X")
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert await repo.get_customer_id(s, tenant_id) == "cus_X"


async def test_upsert_subscription_updates_in_place(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine)
    state = SubscriptionState(
        tier="pro", status="trialing", provider="stripe", provider_subscription_id="sub_1",
        current_period_start=datetime(2026, 6, 3, tzinfo=timezone.utc),
        current_period_end=datetime(2026, 7, 3, tzinfo=timezone.utc),
        cancel_at_period_end=False)
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        await repo.upsert_subscription(s, tenant_id, state)
        row = await repo.get_subscription(s, tenant_id)
        assert row.tier == "pro" and row.status == "trialing"
    async with admin_engine.begin() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM subscriptions WHERE tenant_id=:t"),
                                {"t": tenant_id})).scalar()
    assert n == 1


async def test_record_billing_event_is_idempotent(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine)
    event = {"id": "evt_1", "type": "invoice.paid", "data": {"object": {"amount_paid": 0}}}
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        first = await repo.record_billing_event(s, tenant_id, event)
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        second = await repo.record_billing_event(s, tenant_id, event)
    assert first is True and second is False


async def test_stub_provider_checkout_includes_metadata_and_trial():
    p = StubProvider()
    url = await p.create_checkout_session(customer_id="cus_1", price_id="price_pro",
                                          tenant_id="t1", trial_days=14,
                                          success_url="s", cancel_url="c")
    assert url.startswith("https://stub.stripe/checkout/")
    assert p.last_checkout["metadata"]["tenant_id"] == "t1"
    assert p.last_checkout["trial_days"] == 14


def test_stub_verify_webhook_roundtrips_signed_payload():
    p = StubProvider()
    payload, sig = p.sign({"id": "evt_1", "type": "invoice.paid"})
    event = p.verify_webhook(payload=payload, sig_header=sig)
    assert event["id"] == "evt_1"


def test_make_payment_provider_none_without_key():
    class S:  # minimal settings stand-in
        stripe_secret_key = None
    assert make_payment_provider(S()) is None


def _price_map():
    return {"price_pro": "pro", "price_premium": "premium"}


class _Settings:
    stripe_price_pro = "price_pro"
    stripe_price_premium = "price_premium"
    billing_success_url = "http://x/success"
    billing_cancel_url = "http://x/cancel"


async def test_start_upgrade_pro_sets_trial_and_persists_customer(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine, "up@acme.com")
    provider = StubProvider()
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        out = await service.start_upgrade(s, provider, _Settings(), tenant_id, "up@acme.com", "pro")
    assert out["checkout_url"].startswith("https://stub.stripe/checkout/")
    assert provider.last_checkout["trial_days"] == 14            # trial on Pro
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert await repo.get_customer_id(s, tenant_id) == f"cus_{tenant_id}"


async def test_start_upgrade_premium_has_no_trial(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine, "pm@acme.com")
    provider = StubProvider()
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        await service.start_upgrade(s, provider, _Settings(), tenant_id, "pm@acme.com", "premium")
    assert provider.last_checkout["trial_days"] == 0


async def test_handle_webhook_flips_tier_and_is_idempotent(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine, "wh@acme.com")
    provider = StubProvider()
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        await repo.set_customer_id(s, tenant_id, "cus_wh")
    provider._subs["sub_1"] = {
        "id": "sub_1", "status": "trialing",
        "items": {"data": [{"price": {"id": "price_pro"}}]},
        "current_period_start": 1, "current_period_end": 2, "cancel_at_period_end": False}
    event = {"id": "evt_42", "type": "checkout.session.completed",
             "data": {"object": {"customer": "cus_wh", "subscription": "sub_1",
                                 "metadata": {"tenant_id": str(tenant_id)}}}}
    payload, sig = provider.sign(event)

    res1 = await service.handle_webhook(app_sessionmaker, provider, _price_map(), payload, sig)
    res2 = await service.handle_webhook(app_sessionmaker, provider, _price_map(), payload, sig)
    assert res1["received"] and res2["received"]
    async with app_sessionmaker() as s:
        tier = (await s.execute(text("SELECT tier FROM auth_resolve_principal(NULL, :e)"),
                                {"e": "wh@acme.com"})).first().tier
    assert tier == "pro"


async def test_handle_webhook_unknown_tenant_raises(app_sessionmaker):
    provider = StubProvider()
    event = {"id": "evt_x", "type": "invoice.paid", "data": {"object": {"customer": "cus_none"}}}
    payload, sig = provider.sign(event)
    try:
        await service.handle_webhook(app_sessionmaker, provider, _price_map(), payload, sig)
        assert False, "expected UnknownTenant"
    except service.UnknownTenantError:
        pass
