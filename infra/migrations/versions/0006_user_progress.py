"""user_progress table for OptionsAcademy progress tracking

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-02
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE user_progress (
          progress_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id    UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id      UUID NOT NULL REFERENCES users(user_id),
          module_slug  TEXT NOT NULL,
          status       TEXT NOT NULL CHECK (status IN ('in_progress','completed')),
          started_at   TIMESTAMPTZ NOT NULL,
          completed_at TIMESTAMPTZ,
          updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, user_id, module_slug)
        );

        CREATE INDEX idx_user_progress_user ON user_progress(tenant_id, user_id);

        GRANT SELECT, INSERT, UPDATE ON user_progress TO saalr_app;

        ALTER TABLE user_progress ENABLE ROW LEVEL SECURITY;
        ALTER TABLE user_progress FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON user_progress
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON user_progress;")
    op.execute("DROP TABLE IF EXISTS user_progress;")
