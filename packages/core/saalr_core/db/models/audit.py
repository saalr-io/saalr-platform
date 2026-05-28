from datetime import datetime
from uuid import UUID

from sqlalchemy import Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class AuditLog(Base):
    __tablename__ = "audit_log"
    audit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    before_state: Mapped[dict | None] = mapped_column(JSONB)
    after_state: Mapped[dict | None] = mapped_column(JSONB)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)