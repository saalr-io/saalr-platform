"""news_sentiment table for FinBERT sentiment aggregates

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-01
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE news_sentiment (
          sentiment_id  UUID PRIMARY KEY,
          symbol        TEXT NOT NULL,
          market        CHAR(2) NOT NULL,
          score         DOUBLE PRECISION NOT NULL,
          label         TEXT NOT NULL,
          confident     BOOLEAN NOT NULL,
          n_headlines   INTEGER NOT NULL,
          total_weight  DOUBLE PRECISION NOT NULL,
          as_of         TIMESTAMPTZ NOT NULL,
          computed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX idx_news_sentiment_symbol
          ON news_sentiment(symbol, market, computed_at DESC);

        -- non-RLS shared market data; the worker INSERTs, the API SELECTs
        GRANT SELECT, INSERT ON news_sentiment TO saalr_app;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS news_sentiment;")
