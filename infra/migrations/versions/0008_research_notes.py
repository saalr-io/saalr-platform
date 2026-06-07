"""research_notes table for the RA-1 research-note core

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-02
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE research_notes (
          note_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id           UUID NOT NULL REFERENCES users(user_id),
          ticker            TEXT NOT NULL,
          market            CHAR(2) NOT NULL,
          summary           TEXT NOT NULL,
          signals_json      JSONB NOT NULL,
          sources_json      JSONB NOT NULL,
          model             TEXT NOT NULL,
          prompt_tokens     INTEGER NOT NULL,
          completion_tokens INTEGER NOT NULL,
          cost_usd          NUMERIC(12,6) NOT NULL,
          created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX idx_research_notes_lookup
          ON research_notes(tenant_id, ticker, created_at DESC);

        GRANT SELECT, INSERT ON research_notes TO saalr_app;

        ALTER TABLE research_notes ENABLE ROW LEVEL SECURITY;
        ALTER TABLE research_notes FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON research_notes
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON research_notes;")
    op.execute("DROP TABLE IF EXISTS research_notes;")
