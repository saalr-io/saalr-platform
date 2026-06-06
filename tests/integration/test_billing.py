from datetime import datetime, timezone
from uuid import uuid4

import httpx  # noqa: F401
from sqlalchemy import text

from saalr_api.billing import repo, service
from saalr_api.billing.provider import StubProvider, make_payment_provider
from saalr_api.billing.reducer import SubscriptionState
from saalr_api.main import create_app
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
    stripe_price_pro_annual = "price_pro_annual"
    stripe_price_premium = "price_premium"
    stripe_price_premium_annual = "price_premium_annual"
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


async def test_dunning_roundtrip_past_due_then_recovers(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine, "dun@acme.com")
    provider = StubProvider()
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        await repo.set_customer_id(s, tenant_id, "cus_dun")
        # promote to active pro directly
        from saalr_api.billing.reducer import SubscriptionState as _S
        from datetime import datetime, timezone
        await repo.upsert_subscription(s, tenant_id, _S(
            tier="pro", status="active", provider="stripe", provider_subscription_id="sub_d",
            current_period_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
            current_period_end=datetime(2026, 7, 1, tzinfo=timezone.utc),
            cancel_at_period_end=False))

    def _evt(eid, etype):
        return {"id": eid, "type": etype, "data": {"object": {"customer": "cus_dun"}}}

    pf_payload, pf_sig = provider.sign(_evt("evt_pf", "invoice.payment_failed"))
    await service.handle_webhook(app_sessionmaker, provider, _price_map(), pf_payload, pf_sig)
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        row = await repo.get_subscription(s, tenant_id)
        assert row is not None and row.status == "past_due"   # still addressable

    pd_payload, pd_sig = provider.sign(_evt("evt_pd", "invoice.paid"))
    await service.handle_webhook(app_sessionmaker, provider, _price_map(), pd_payload, pd_sig)
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        row = await repo.get_subscription(s, tenant_id)
        assert row is not None and row.status == "active" and row.tier == "pro"  # recovered


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _auth(email):
    return {"Authorization": f"Bearer dev:{email}"}


async def test_get_subscription_defaults_to_free():
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.payment_provider = StubProvider()
        async with _client(app) as c:
            await c.post("/auth/dev/login", json={"email": "free@acme.com"})
            r = await c.get("/subscription", headers=_auth("free@acme.com"))
    assert r.status_code == 200
    assert r.json()["tier"] == "free"
    assert r.json()["entitlements"]["live_chains"] is False


async def test_upgrade_returns_checkout_url():
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.payment_provider = StubProvider()
        async with _client(app) as c:
            await c.post("/auth/dev/login", json={"email": "u2@acme.com"})
            r = await c.post("/subscription/upgrade", json={"tier": "pro"},
                             headers=_auth("u2@acme.com"))
    assert r.status_code == 200
    assert r.json()["checkout_url"].startswith("https://stub.stripe/checkout/")


async def test_upgrade_503_when_billing_unconfigured():
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.payment_provider = None  # not configured
        async with _client(app) as c:
            await c.post("/auth/dev/login", json={"email": "u3@acme.com"})
            r = await c.post("/subscription/upgrade", json={"tier": "pro"},
                             headers=_auth("u3@acme.com"))
    assert r.status_code == 503
    assert r.json()["detail"]["error"]["code"] == "FEATURE_UNAVAILABLE"


async def test_webhook_bad_signature_is_400():
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.payment_provider = StubProvider()
        async with _client(app) as c:
            r = await c.post("/webhooks/stripe", content=b'{"id":"e"}',
                             headers={"Stripe-Signature": "wrong"})
    assert r.status_code == 400


async def test_webhook_infra_error_is_not_swallowed_as_400():
    """A DB/infra failure in the handler must NOT become a 400 (Stripe would never retry);
    it propagates as a server error so Stripe redelivers and the idempotency gate replays."""
    import pytest

    import saalr_api.billing.service as billing_service

    app = create_app()
    async with app.router.lifespan_context(app):
        provider = StubProvider()
        app.state.payment_provider = provider
        payload, sig = provider.sign(
            {"id": "evt_boom", "type": "invoice.paid", "data": {"object": {"customer": "cus_z"}}})

        async def _boom(*a, **k):
            raise RuntimeError("db down")

        original = billing_service.handle_webhook
        billing_service.handle_webhook = _boom
        try:
            with pytest.raises(RuntimeError):  # propagates (default ASGI raise_app_exceptions)
                async with _client(app) as c:
                    await c.post("/webhooks/stripe", content=payload,
                                 headers={"Stripe-Signature": sig})
        finally:
            billing_service.handle_webhook = original


async def test_get_subscription_reports_has_customer(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine, "hc@acme.com")
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert (await service.get_subscription(s, tenant_id))["has_customer"] is False
        await repo.set_customer_id(s, tenant_id, "cus_hc")
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert (await service.get_subscription(s, tenant_id))["has_customer"] is True


async def test_upgrade_rejects_bad_interval(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.post("/subscription/upgrade", json={"tier": "pro", "interval": "weekly"},
                             headers={"Authorization": "Bearer dev:bill-iv@x.com"})
            assert r.status_code == 422


async def test_upgrade_annual_accepted():
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.payment_provider = StubProvider()
        async with _client(app) as c:
            await c.post("/auth/dev/login", json={"email": "annual@acme.com"})
            r = await c.post("/subscription/upgrade",
                             json={"tier": "pro", "interval": "annual"},
                             headers=_auth("annual@acme.com"))
    assert r.status_code == 200
    assert r.json()["checkout_url"].startswith("https://stub.stripe/checkout/")
