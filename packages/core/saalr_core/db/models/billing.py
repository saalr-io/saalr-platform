from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class Subscription(Base):
    __tablename__ = "subscriptions"
    subscription_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(Text)
    current_period_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class BillingEvent(Base):
    __tablename__ = "billing_events"
    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    subscription_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("subscriptions.subscription_id"))
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    provider_event_id: Mapped[str | None] = mapped_column(Text, unique=True)
    raw_event: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)