"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_SCOPED = [
    "tenants", "memberships", "api_keys", "subscriptions", "billing_events",
    "strategies", "backtests", "broker_accounts", "orders", "executions",
    "positions", "audit_log",
]


def upgrade() -> None:
    bind = op.get_bind()
    # TimescaleDB isn't available on AWS RDS for PostgreSQL. When it's absent,
    # bars / options_chain_snapshots are created as plain tables (queries stay
    # correct; only the time-partitioning optimization is absent). Where it IS
    # available (local/dev Timescale), they become hypertables (see below).
    has_timescale = (
        bind.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'")
        ).scalar()
        is not None
    )

    if has_timescale:
        op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.execute("""
        CREATE TABLE tenants (
          tenant_id    UUID PRIMARY KEY,
          display_name TEXT NOT NULL,
          country_code CHAR(2) NOT NULL,
          created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          status       TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active','suspended','closed'))
        );

        CREATE TABLE users (
          user_id           UUID PRIMARY KEY,
          email             CITEXT UNIQUE NOT NULL,
          email_verified_at TIMESTAMPTZ,
          created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          clerk_user_id     TEXT UNIQUE,
          preferred_tz      TEXT NOT NULL DEFAULT 'UTC',
          preferred_locale  TEXT NOT NULL DEFAULT 'en-US'
        );

        CREATE TABLE memberships (
          user_id    UUID NOT NULL REFERENCES users(user_id),
          tenant_id  UUID NOT NULL REFERENCES tenants(tenant_id),
          role       TEXT NOT NULL CHECK (role IN ('owner','admin','member')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (user_id, tenant_id)
        );
        CREATE INDEX idx_memberships_tenant ON memberships(tenant_id);

        CREATE TABLE api_keys (
          key_id       UUID PRIMARY KEY,
          tenant_id    UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id      UUID NOT NULL REFERENCES users(user_id),
          key_hash     TEXT NOT NULL,
          key_prefix   TEXT NOT NULL,
          label        TEXT,
          scopes       TEXT[] NOT NULL,
          created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          last_used_at TIMESTAMPTZ,
          revoked_at   TIMESTAMPTZ
        );
        CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id) WHERE revoked_at IS NULL;

        CREATE TABLE subscriptions (
          subscription_id          UUID PRIMARY KEY,
          tenant_id                UUID NOT NULL REFERENCES tenants(tenant_id),
          tier                     TEXT NOT NULL CHECK (tier IN ('free','pro','premium')),
          status                   TEXT NOT NULL CHECK (status IN ('active','past_due','cancelled','trialing')),
          provider                 TEXT NOT NULL CHECK (provider IN ('stripe','razorpay','manual')),
          provider_subscription_id TEXT,
          current_period_start     TIMESTAMPTZ NOT NULL,
          current_period_end       TIMESTAMPTZ NOT NULL,
          cancel_at_period_end     BOOLEAN NOT NULL DEFAULT FALSE,
          created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX idx_subscriptions_tenant_active
          ON subscriptions(tenant_id) WHERE status = 'active';

        CREATE TABLE billing_events (
          event_id          UUID PRIMARY KEY,
          tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
          subscription_id   UUID REFERENCES subscriptions(subscription_id),
          event_type        TEXT NOT NULL,
          amount            NUMERIC(18,8),
          currency          CHAR(3),
          provider_event_id TEXT UNIQUE,
          raw_event         JSONB NOT NULL,
          received_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE broker_accounts (
          broker_account_id  UUID PRIMARY KEY,
          tenant_id          UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id            UUID NOT NULL REFERENCES users(user_id),
          broker             TEXT NOT NULL CHECK (broker IN ('alpaca','ibkr','zerodha','angelone')),
          account_label      TEXT NOT NULL,
          credential_ref     TEXT NOT NULL,
          is_paper           BOOLEAN NOT NULL,
          status             TEXT NOT NULL CHECK (status IN ('active','disconnected','revoked')),
          last_reconciled_at TIMESTAMPTZ,
          created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE strategies (
          strategy_id         UUID PRIMARY KEY,
          tenant_id           UUID NOT NULL REFERENCES tenants(tenant_id),
          user_id             UUID NOT NULL REFERENCES users(user_id),
          name                TEXT NOT NULL,
          description         TEXT,
          state               TEXT NOT NULL CHECK (state IN ('draft','backtested','paper','live','paused','archived')),
          config_json         JSONB NOT NULL,
          market              CHAR(2) NOT NULL,
          broker_account_id   UUID REFERENCES broker_accounts(broker_account_id),
          created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          promoted_to_live_at TIMESTAMPTZ,
          paused_at           TIMESTAMPTZ,
          paused_reason       TEXT
        );
        CREATE INDEX idx_strategies_tenant ON strategies(tenant_id);
        CREATE INDEX idx_strategies_state ON strategies(state) WHERE state IN ('paper','live');

        CREATE TABLE backtests (
          backtest_id     UUID PRIMARY KEY,
          tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
          strategy_id     UUID NOT NULL REFERENCES strategies(strategy_id),
          start_date      DATE NOT NULL,
          end_date        DATE NOT NULL,
          status          TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
          metrics_json    JSONB,
          trade_log_uri   TEXT,
          config_snapshot JSONB NOT NULL,
          error_message   TEXT,
          started_at      TIMESTAMPTZ,
          completed_at    TIMESTAMPTZ,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE model_validation_runs (
          validation_id       UUID PRIMARY KEY,
          model_name          TEXT NOT NULL,
          market              CHAR(2) NOT NULL,
          cohort_label        TEXT NOT NULL,
          baseline_name       TEXT NOT NULL,
          status              TEXT NOT NULL CHECK (status IN ('running','passed','failed')),
          metric_summary_json JSONB NOT NULL,
          report_uri          TEXT,
          started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          completed_at        TIMESTAMPTZ
        );
        CREATE INDEX idx_validation_model_market
          ON model_validation_runs(model_name, market, started_at DESC);

        CREATE TABLE orders (
          order_id           UUID PRIMARY KEY,
          tenant_id          UUID NOT NULL REFERENCES tenants(tenant_id),
          strategy_id        UUID REFERENCES strategies(strategy_id),
          broker_account_id  UUID NOT NULL REFERENCES broker_accounts(broker_account_id),
          symbol             TEXT NOT NULL,
          option_type        TEXT CHECK (option_type IN ('CE','PE','CALL','PUT', NULL)),
          strike             NUMERIC(18,8),
          expiry             DATE,
          side               TEXT NOT NULL CHECK (side IN ('buy','sell')),
          qty                INTEGER NOT NULL CHECK (qty > 0),
          order_type         TEXT NOT NULL CHECK (order_type IN ('market','limit','stop','stop_limit')),
          limit_price        NUMERIC(18,8),
          stop_price         NUMERIC(18,8),
          time_in_force      TEXT NOT NULL CHECK (time_in_force IN ('day','gtc','ioc','fok')),
          status             TEXT NOT NULL CHECK (status IN ('pending','submitted','partial','filled','cancelled','rejected')),
          broker_order_id    TEXT,
          idempotency_key    TEXT,
          reject_reason_code TEXT,
          created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          submitted_at       TIMESTAMPTZ,
          filled_at          TIMESTAMPTZ
        );
        CREATE UNIQUE INDEX idx_orders_idempotency
          ON orders(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
        CREATE INDEX idx_orders_tenant_status ON orders(tenant_id, status);

        CREATE TABLE executions (
          execution_id        UUID PRIMARY KEY,
          tenant_id           UUID NOT NULL REFERENCES tenants(tenant_id),
          order_id            UUID NOT NULL REFERENCES orders(order_id),
          broker_account_id   UUID NOT NULL REFERENCES broker_accounts(broker_account_id),
          qty                 INTEGER NOT NULL,
          price               NUMERIC(18,8) NOT NULL,
          commission          NUMERIC(18,8) DEFAULT 0,
          broker_execution_id TEXT NOT NULL,
          executed_at         TIMESTAMPTZ NOT NULL
        );
        CREATE UNIQUE INDEX idx_executions_broker_id
          ON executions(broker_account_id, broker_execution_id);

        CREATE TABLE positions (
          position_id       UUID PRIMARY KEY,
          tenant_id         UUID NOT NULL REFERENCES tenants(tenant_id),
          broker_account_id UUID NOT NULL REFERENCES broker_accounts(broker_account_id),
          symbol            TEXT NOT NULL,
          option_type       TEXT,
          strike            NUMERIC(18,8),
          expiry            DATE,
          qty               INTEGER NOT NULL,
          avg_entry_price   NUMERIC(18,8) NOT NULL,
          opened_at         TIMESTAMPTZ NOT NULL,
          last_updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_positions_tenant ON positions(tenant_id);

        CREATE TABLE audit_log (
          audit_id     UUID PRIMARY KEY,
          tenant_id    UUID NOT NULL,
          user_id      UUID,
          action       TEXT NOT NULL,
          target_type  TEXT,
          target_id    UUID,
          before_state JSONB,
          after_state  JSONB,
          request_id   TEXT NOT NULL,
          trace_id     TEXT,
          ip_address   INET,
          user_agent   TEXT,
          occurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX idx_audit_tenant_time ON audit_log(tenant_id, occurred_at DESC);
        CREATE INDEX idx_audit_target ON audit_log(target_type, target_id) WHERE target_id IS NOT NULL;

        CREATE TABLE config_kv (
          scope      TEXT NOT NULL,
          scope_id   UUID,
          key        TEXT NOT NULL,
          value      JSONB NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_by UUID,
          PRIMARY KEY (scope, scope_id, key)
        );

        CREATE TABLE bars (
          ts       TIMESTAMPTZ NOT NULL,
          symbol   TEXT NOT NULL,
          market   CHAR(2) NOT NULL,
          interval TEXT NOT NULL,
          open     NUMERIC(18,8) NOT NULL,
          high     NUMERIC(18,8) NOT NULL,
          low      NUMERIC(18,8) NOT NULL,
          close    NUMERIC(18,8) NOT NULL,
          volume   BIGINT NOT NULL,
          PRIMARY KEY (symbol, market, interval, ts)
        );

        CREATE TABLE options_chain_snapshots (
          ts            TIMESTAMPTZ NOT NULL,
          underlying    TEXT NOT NULL,
          market        CHAR(2) NOT NULL,
          expiry        DATE NOT NULL,
          strike        NUMERIC(18,8) NOT NULL,
          option_type   TEXT NOT NULL CHECK (option_type IN ('CE','PE','CALL','PUT')),
          bid           NUMERIC(18,8),
          ask           NUMERIC(18,8),
          last          NUMERIC(18,8),
          volume        BIGINT,
          open_interest BIGINT,
          iv            NUMERIC(10,6),
          delta         NUMERIC(10,6),
          gamma         NUMERIC(10,6),
          theta         NUMERIC(10,6),
          vega          NUMERIC(10,6),
          PRIMARY KEY (underlying, market, expiry, strike, option_type, ts)
        );
    """)

    # Promote the time-series tables to hypertables only where TimescaleDB exists.
    if has_timescale:
        op.execute("SELECT create_hypertable('bars', 'ts', chunk_time_interval => INTERVAL '1 day')")
        op.execute(
            "SELECT create_hypertable('options_chain_snapshots', 'ts', chunk_time_interval => INTERVAL '1 day')"
        )

    # Non-superuser application role + grants.
    op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'saalr_app') THEN
            CREATE ROLE saalr_app LOGIN PASSWORD 'saalr_app';
          END IF;
        END $$;

        GRANT USAGE ON SCHEMA public TO saalr_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO saalr_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
          GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO saalr_app;
    """)

    # FORCE row-level security + tenant-isolation policy on every tenant-scoped table.
    for t in TENANT_SCOPED:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} "
            "USING (tenant_id = current_setting('app.current_tenant', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)"
        )


def downgrade() -> None:
    for t in TENANT_SCOPED:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")

    op.execute("""
        DROP TABLE IF EXISTS options_chain_snapshots, bars, config_kv, audit_log,
          positions, executions, orders, model_validation_runs, backtests,
          strategies, broker_accounts, billing_events, subscriptions, api_keys,
          memberships, users, tenants CASCADE;
    """)
    # Note: the saalr_app role is cluster-global and intentionally left in place.