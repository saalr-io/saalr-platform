"""marketing audience: opt-in, unsubscribe token, audience view

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-06
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users ADD COLUMN marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE users ADD COLUMN unsubscribe_token UUID NOT NULL DEFAULT gen_random_uuid();
        CREATE UNIQUE INDEX idx_users_unsubscribe_token ON users(unsubscribe_token);

        CREATE VIEW marketing_audience AS
          SELECT u.email,
                 u.email_verified_at,
                 u.created_at,
                 u.marketing_opt_in,
                 u.unsubscribe_token,
                 COALESCE(s.tier, 'free') AS tier,
                 EXISTS (SELECT 1 FROM strategies st   WHERE st.tenant_id = m.tenant_id) AS has_strategy,
                 EXISTS (SELECT 1 FROM orders o        WHERE o.tenant_id  = m.tenant_id) AS has_traded,
                 EXISTS (SELECT 1 FROM backtests b     WHERE b.tenant_id  = m.tenant_id) AS has_backtest,
                 EXISTS (SELECT 1 FROM user_progress p WHERE p.tenant_id  = m.tenant_id) AS has_progress
          FROM users u
          JOIN memberships m ON m.user_id = u.user_id
          LEFT JOIN subscriptions s ON s.tenant_id = m.tenant_id AND s.status IN ('active','trialing');
        GRANT SELECT ON marketing_audience TO saalr_app;
    """)


def downgrade() -> None:
    op.execute("""
        DROP VIEW IF EXISTS marketing_audience;
        DROP INDEX IF EXISTS idx_users_unsubscribe_token;
        ALTER TABLE users DROP COLUMN IF EXISTS unsubscribe_token;
        ALTER TABLE users DROP COLUMN IF EXISTS marketing_opt_in;
    """)
