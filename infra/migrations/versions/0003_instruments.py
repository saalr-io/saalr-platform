"""instruments table for market-data ingestion

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-30
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE instruments (
          symbol      TEXT NOT NULL,
          market      CHAR(2) NOT NULL,
          name        TEXT,
          is_active   BOOLEAN NOT NULL DEFAULT true,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (symbol, market)
        );

        -- The worker only SELECTs/upserts; it never TRUNCATEs (tests truncate via the admin role).
        GRANT SELECT, INSERT, UPDATE ON instruments TO saalr_app;
        GRANT SELECT, INSERT, UPDATE ON bars TO saalr_app;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS instruments;")
