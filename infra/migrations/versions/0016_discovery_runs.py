"""discovery_runs table (tenant-scoped, FORCE RLS)

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-10
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE discovery_runs (
          discovery_id  UUID PRIMARY KEY,
          tenant_id     UUID NOT NULL REFERENCES tenants(tenant_id),
          underlying    TEXT NOT NULL,
          market        CHAR(2) NOT NULL,
          status        TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
          request_json  JSONB NOT NULL,
          result_json   JSONB,
          error_message TEXT,
          as_of         TIMESTAMPTZ,
          started_at    TIMESTAMPTZ,
          completed_at  TIMESTAMPTZ,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_discovery_runs_tenant ON discovery_runs(tenant_id);
    """)
    op.execute("ALTER TABLE discovery_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE discovery_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON discovery_runs "
        "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON discovery_runs")
    op.execute("DROP TABLE IF EXISTS discovery_runs CASCADE")
