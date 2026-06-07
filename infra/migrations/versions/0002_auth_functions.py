"""auth identity functions (SECURITY DEFINER)

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-28
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PROD REQUIREMENT: these SECURITY DEFINER functions must be owned by a role that
    # BYPASSES RLS (a superuser in local dev, or a dedicated BYPASSRLS role in prod).
    # The owner reads memberships/tenants which are FORCE ROW LEVEL SECURITY; if the
    # owner is a non-BYPASSRLS role, auth_resolve_principal returns 0 rows and every
    # login fails. Pin ownership (ALTER FUNCTION ... OWNER TO <bypassrls_role>) at deploy.
    op.execute("""
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

        CREATE OR REPLACE FUNCTION auth_bootstrap(
            p_user_id uuid, p_tenant_id uuid, p_sub_id uuid,
            p_clerk_user_id text, p_email citext
        )
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $func$
        BEGIN
          -- Scope the GUC to the new tenant so RLS WITH CHECK passes even under FORCE RLS.
          PERFORM set_config('app.current_tenant', p_tenant_id::text, true);
          INSERT INTO users (user_id, email, clerk_user_id)
            VALUES (p_user_id, p_email, p_clerk_user_id);
          INSERT INTO tenants (tenant_id, display_name, country_code)
            VALUES (p_tenant_id, split_part(p_email, '@', 1), 'US');
          INSERT INTO memberships (user_id, tenant_id, role)
            VALUES (p_user_id, p_tenant_id, 'owner');
          INSERT INTO subscriptions (subscription_id, tenant_id, tier, status, provider,
                                     current_period_start, current_period_end)
            VALUES (p_sub_id, p_tenant_id, 'free', 'active', 'manual',
                    now(), now() + interval '100 years');
        END;
        $func$;

        GRANT EXECUTE ON FUNCTION auth_resolve_principal(text, citext) TO saalr_app;
        GRANT EXECUTE ON FUNCTION auth_bootstrap(uuid, uuid, uuid, text, citext) TO saalr_app;
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION IF EXISTS auth_bootstrap(uuid, uuid, uuid, text, citext);
        DROP FUNCTION IF EXISTS auth_resolve_principal(text, citext);
    """)
