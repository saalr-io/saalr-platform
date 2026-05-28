from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base
from saalr_core.ids import new_id


class Tenant(Base):
    __tablename__ = "tenants"
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    clerk_user_id: Mapped[str | None] = mapped_column(Text, unique=True)
    preferred_tz: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    preferred_locale: Mapped[str] = mapped_column(Text, nullable=False, server_default="en-US")


class Membership(Base):
    __tablename__ = "memberships"
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (Index("idx_memberships_tenant", "tenant_id"),)


class ApiKey(Base):
    __tablename__ = "api_keys"
    key_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))