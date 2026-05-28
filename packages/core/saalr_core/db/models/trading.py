from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CHAR, Date, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class Strategy(Base):
    __tablename__ = "strategies"
    strategy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    market: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    broker_account_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("broker_accounts.broker_account_id"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    promoted_to_live_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    paused_reason: Mapped[str | None] = mapped_column(Text)


class Backtest(Base):
    __tablename__ = "backtests"
    backtest_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    strategy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("strategies.strategy_id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[dict | None] = mapped_column(JSONB)
    trade_log_uri: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ModelValidationRun(Base):
    __tablename__ = "model_validation_runs"
    validation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    cohort_label: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    metric_summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    report_uri: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class BrokerAccount(Base):
    __tablename__ = "broker_accounts"
    broker_account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    broker: Mapped[str] = mapped_column(Text, nullable=False)
    account_label: Mapped[str] = mapped_column(Text, nullable=False)
    credential_ref: Mapped[str] = mapped_column(Text, nullable=False)
    is_paper: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class Order(Base):
    __tablename__ = "orders"
    order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    strategy_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("strategies.strategy_id"))
    broker_account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("broker_accounts.broker_account_id"), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    option_type: Mapped[str | None] = mapped_column(Text)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    expiry: Mapped[date | None] = mapped_column(Date)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    order_type: Mapped[str] = mapped_column(Text, nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    time_in_force: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    reject_reason_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Execution(Base):
    __tablename__ = "executions"
    execution_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    order_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("orders.order_id"), nullable=False)
    broker_account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("broker_accounts.broker_account_id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 8), server_default="0")
    broker_execution_id: Mapped[str] = mapped_column(Text, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Position(Base):
    __tablename__ = "positions"
    position_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    broker_account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("broker_accounts.broker_account_id"), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    option_type: Mapped[str | None] = mapped_column(Text)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    expiry: Mapped[date | None] = mapped_column(Date)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)