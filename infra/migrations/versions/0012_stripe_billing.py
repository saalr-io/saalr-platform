"""stripe billing: tenants.stripe_customer_id, customer->tenant lookup, trialing entitlements

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-03
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenants ADD COLUMN stripe_customer_id text;
        CREATE UNIQUE INDEX idx_tenants_stripe_customer
          ON tenants(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

        -- Webhook resolves tenant from a Stripe customer id BEFORE any tenant context
        -- exists. tenants is FORCE RLS, so this must be SECURITY DEFINER (same posture
        -- as auth_resolve_principal). Owner must BYPASSRLS in prod.
        CREATE OR REPLACE FUNCTION billing_tenant_for_customer(p_customer_id text)
        RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = public AS $func$
          SELECT tenant_id FROM tenants WHERE stripe_customer_id = p_customer_id LIMIT 1;
        $func$;
        GRANT EXECUTE ON FUNCTION billing_tenant_for_customer(text) TO saalr_app;

        -- Trials carry status 'trialing'; the resolver must grant their tier.
        CREATE OR REPLACE FUNCTION auth_resolve_principal(p_clerk_user_id text, p_email citext)
        RETURNS TABLE (user_id uuid, tenant_id uuid, tier text)
        LANGUAGE sql SECURITY DEFINER SET search_path = public AS $func$
          SELECT u.user_id, m.tenant_id, COALESCE(s.tier, 'free')
          FROM users u
          JOIN memberships m ON m.user_id = u.user_id
          LEFT JOIN subscriptions s
            ON s.tenant_id = m.tenant_id AND s.status IN ('active', 'trialing')
          WHERE (p_clerk_user_id IS NOT NULL AND u.clerk_user_id = p_clerk_user_id)
             OR (p_clerk_user_id IS NULL AND u.email = p_email)
          ORDER BY m.created_at
          LIMIT 1;
        $func$;

        -- One entitled row per tenant (active OR trialing).
        DROP INDEX IF EXISTS idx_subscriptions_tenant_active;
        CREATE UNIQUE INDEX idx_subscriptions_tenant_active
          ON subscriptions(tenant_id) WHERE status IN ('active', 'trialing');
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_subscriptions_tenant_active;
        CREATE UNIQUE INDEX idx_subscriptions_tenant_active
          ON subscriptions(tenant_id) WHERE status = 'active';

        CREATE OR REPLACE FUNCTION auth_resolve_principal(p_clerk_user_id text, p_email citext)
        RETURNS TABLE (user_id uuid, tenant_id uuid, tier text)
        LANGUAGE sql SECURITY DEFINER SET search_path = public AS $func$
          SELECT u.user_id, m.tenant_id, COALESCE(s.tier, 'free')
          FROM users u
          JOIN memberships m ON m.user_id = u.user_id
          LEFT JOIN subscriptions s ON s.tenant_id = m.tenant_id AND s.status = 'active'
          WHERE (p_clerk_user_id IS NOT NULL AND u.clerk_user_id = p_clerk_user_id)
             OR (p_clerk_user_id IS NULL AND u.email = p_email)
          ORDER BY m.created_at
          LIMIT 1;
        $func$;

        DROP FUNCTION IF EXISTS billing_tenant_for_customer(text);
        DROP INDEX IF EXISTS idx_tenants_stripe_customer;
        ALTER TABLE tenants DROP COLUMN IF EXISTS stripe_customer_id;
    """)
