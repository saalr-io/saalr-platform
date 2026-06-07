from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    usage_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    note_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
