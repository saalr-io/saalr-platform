"""add 'paper' to the broker_accounts.broker CHECK

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-01
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE broker_accounts DROP CONSTRAINT IF EXISTS broker_accounts_broker_check;
        ALTER TABLE broker_accounts ADD CONSTRAINT broker_accounts_broker_check
          CHECK (broker IN ('paper', 'alpaca', 'ibkr', 'zerodha', 'angelone'));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE broker_accounts DROP CONSTRAINT IF EXISTS broker_accounts_broker_check;
        ALTER TABLE broker_accounts ADD CONSTRAINT broker_accounts_broker_check
          CHECK (broker IN ('alpaca', 'ibkr', 'zerodha', 'angelone'));
    """)
