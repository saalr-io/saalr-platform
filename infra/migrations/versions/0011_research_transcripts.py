"""research_transcripts — per-note multi-agent transcript (RA-3c)

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-03
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE research_transcripts (
          transcript_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
          note_id         UUID NOT NULL UNIQUE REFERENCES research_notes(note_id),
          transcript_json JSONB NOT NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        GRANT SELECT, INSERT ON research_transcripts TO saalr_app;

        ALTER TABLE research_transcripts ENABLE ROW LEVEL SECURITY;
        ALTER TABLE research_transcripts FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON research_transcripts
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON research_transcripts;")
    op.execute("DROP TABLE IF EXISTS research_transcripts;")
