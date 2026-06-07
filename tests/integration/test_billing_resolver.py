from uuid import uuid4

from sqlalchemy import text


async def test_trialing_subscription_resolves_to_its_tier(admin_engine, app_sessionmaker):
    tenant_id, user_id = uuid4(), uuid4()
    # Seed a user + tenant + membership + a TRIALING pro subscription (admin bypasses RLS).
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (user_id, email) VALUES (:u, :e)"),
            {"u": user_id, "e": "trial@acme.com"})
        await conn.execute(
            text("INSERT INTO tenants (tenant_id, display_name, country_code) VALUES (:t,'acme','US')"),
            {"t": tenant_id})
        await conn.execute(
            text("INSERT INTO memberships (user_id, tenant_id, role) VALUES (:u,:t,'owner')"),
            {"u": user_id, "t": tenant_id})
        await conn.execute(
            text("INSERT INTO subscriptions (subscription_id, tenant_id, tier, status, provider, "
                 "current_period_start, current_period_end) "
                 "VALUES (:s,:t,'pro','trialing','stripe', now(), now()+interval '14 days')"),
            {"s": uuid4(), "t": tenant_id})

    async with app_sessionmaker() as s:
        row = (await s.execute(
            text("SELECT tier FROM auth_resolve_principal(NULL, :e)"),
            {"e": "trial@acme.com"})).first()
    assert row is not None and row.tier == "pro"
