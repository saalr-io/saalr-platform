"""research_notes async lifecycle: status + error_message, nullable result cols, UPDATE grant

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-02
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE research_notes
          ADD COLUMN status TEXT NOT NULL DEFAULT 'succeeded'
            CHECK (status IN ('queued','running','succeeded','failed')),
          ADD COLUMN error_message TEXT,
          ALTER COLUMN summary           DROP NOT NULL,
          ALTER COLUMN signals_json      DROP NOT NULL,
          ALTER COLUMN sources_json      DROP NOT NULL,
          ALTER COLUMN model             DROP NOT NULL,
          ALTER COLUMN prompt_tokens     DROP NOT NULL,
          ALTER COLUMN completion_tokens DROP NOT NULL,
          ALTER COLUMN cost_usd          DROP NOT NULL;

        GRANT UPDATE ON research_notes TO saalr_app;

        CREATE INDEX idx_research_notes_tenant_created
          ON research_notes(tenant_id, created_at DESC);
    """)


def downgrade() -> None:
    # One-way nullability relaxation: NOT NULL is not re-added (rows with nulls may exist).
    op.execute("""
        DROP INDEX IF EXISTS idx_research_notes_tenant_created;
        REVOKE UPDATE ON research_notes FROM saalr_app;
        ALTER TABLE research_notes
          DROP COLUMN IF EXISTS error_message,
          DROP COLUMN IF EXISTS status;
    """)
