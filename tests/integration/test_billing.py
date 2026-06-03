from datetime import datetime, timezone
from uuid import uuid4

import httpx  # noqa: F401
from sqlalchemy import text

from saalr_api.billing import repo
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
