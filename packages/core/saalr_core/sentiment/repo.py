from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.market_data import Instrument, NewsSentiment
from saalr_core.ids import new_id


async def save_sentiment(session: AsyncSession, symbol: str, market: str, agg: dict) -> None:
    as_of = datetime.fromisoformat(agg["as_of"])
    if as_of.tzinfo is None:  # the as_of=TIMESTAMPTZ column rejects naive datetimes (asyncpg)
        as_of = as_of.replace(tzinfo=timezone.utc)
    session.add(
        NewsSentiment(
            sentiment_id=new_id(),
            symbol=symbol,
            market=market,
            score=float(agg["score"]),
            label=agg["label"],
            confident=bool(agg["confident"]),
            n_headlines=int(agg["n_headlines"]),
            total_weight=float(agg["total_weight"]),
            as_of=as_of,
        )
    )
    await session.flush()


async def latest_sentiment(session: AsyncSession, symbol: str, market: str) -> dict | None:
    row = (
        await session.execute(
            select(NewsSentiment)
            .where(NewsSentiment.symbol == symbol, NewsSentiment.market == market)
            .order_by(NewsSentiment.computed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "symbol": row.symbol,
        "market": row.market,
        "score": row.score,
        "label": row.label,
        "confident": row.confident,
        "n_headlines": row.n_headlines,
        "as_of": row.as_of,
        "computed_at": row.computed_at,
    }


async def list_active_instruments(session: AsyncSession, market: str | None = None) -> list[tuple[str, str]]:
    stmt = select(Instrument.symbol, Instrument.market).where(Instrument.is_active.is_(True))
    if market is not None:
        stmt = stmt.where(Instrument.market == market)
    rows = (await session.execute(stmt.order_by(Instrument.symbol))).all()
    return [(r.symbol, r.market) for r in rows]
