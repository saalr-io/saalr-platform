from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, BigInteger, Date, Numeric, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from saalr_core.db.base import Base


class Bar(Base):
    __tablename__ = "bars"
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    market: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    interval: Mapped[str] = mapped_column(Text, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)


class OptionsChainSnapshot(Base):
    __tablename__ = "options_chain_snapshots"
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    underlying: Mapped[str] = mapped_column(Text, primary_key=True)
    market: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    expiry: Mapped[date] = mapped_column(Date, primary_key=True)
    strike: Mapped[Decimal] = mapped_column(Numeric(18, 8), primary_key=True)
    option_type: Mapped[str] = mapped_column(Text, primary_key=True)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    last: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    open_interest: Mapped[int | None] = mapped_column(BigInteger)
    iv: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    delta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    theta: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    vega: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))