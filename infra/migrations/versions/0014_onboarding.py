"""onboarding progress table + account deletion-request flag

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-07
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE onboarding_progress (
            tenant_id    UUID NOT NULL REFERENCES tenants(tenant_id),
            step         TEXT NOT NULL,
            completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, step)
        );
        ALTER TABLE onboarding_progress ENABLE ROW LEVEL SECURITY;
        ALTER TABLE onboarding_progress FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON onboarding_progress
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
        GRANT SELECT, INSERT, UPDATE, DELETE ON onboarding_progress TO saalr_app;

        ALTER TABLE users ADD COLUMN deletion_requested_at TIMESTAMPTZ;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE users DROP COLUMN IF EXISTS deletion_requested_at;
        DROP POLICY IF EXISTS tenant_isolation ON onboarding_progress;
        DROP TABLE IF EXISTS onboarding_progress;
    """)
