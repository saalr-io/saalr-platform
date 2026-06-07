"""add 'tradier' to the broker_accounts.broker CHECK

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-08
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE broker_accounts DROP CONSTRAINT IF EXISTS broker_accounts_broker_check;
        ALTER TABLE broker_accounts ADD CONSTRAINT broker_accounts_broker_check
          CHECK (broker IN ('paper', 'alpaca', 'tradier', 'ibkr', 'zerodha', 'angelone'));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE broker_accounts DROP CONSTRAINT IF EXISTS broker_accounts_broker_check;
        ALTER TABLE broker_accounts ADD CONSTRAINT broker_accounts_broker_check
          CHECK (broker IN ('paper', 'alpaca', 'ibkr', 'zerodha', 'angelone'));
    """)
