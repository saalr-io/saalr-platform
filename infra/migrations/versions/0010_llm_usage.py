"""llm_usage per-tenant LLM cost ledger (RA-3a)

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-03
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE llm_usage (
          usage_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id           UUID NOT NULL REFERENCES users(user_id),
          provider          TEXT NOT NULL,
          model             TEXT NOT NULL,
          prompt_tokens     INTEGER NOT NULL,
          completion_tokens INTEGER NOT NULL,
          cost_usd          NUMERIC(12,6) NOT NULL,
          purpose           TEXT NOT NULL,
          note_id           UUID,
          created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX idx_llm_usage_tenant_created ON llm_usage(tenant_id, created_at DESC);

        GRANT SELECT, INSERT ON llm_usage TO saalr_app;

        ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;
        ALTER TABLE llm_usage FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON llm_usage
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON llm_usage;")
    op.execute("DROP TABLE IF EXISTS llm_usage;")
