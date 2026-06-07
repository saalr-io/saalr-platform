from datetime import datetime
from uuid import UUID

from sqlalchemy import Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base


class ConfigKV(Base):
    __tablename__ = "config_kv"
    scope: Mapped[str] = mapped_column(Text, primary_key=True)
    scope_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))