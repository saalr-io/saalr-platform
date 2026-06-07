from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.sentiment import repo
from saalr_core.sentiment.aggregate import aggregate_sentiment


async def refresh_symbol(
    session: AsyncSession,
    provider,
    scorer,
    symbol: str,
    market: str,
    as_of: datetime,
    lookback_hours: int = 168,
) -> dict:
    """Fetch recent news, score it (injected SentimentScorer), aggregate, and persist.
    Torch-free: `provider` and `scorer` are protocols, so tests inject stubs."""
    headlines = await provider.get_news(
        symbol, published_after=as_of - timedelta(hours=lookback_hours)
    )
    scored = scorer.score_headlines(headlines)
    agg = aggregate_sentiment(scored, as_of)
    await repo.save_sentiment(session, symbol, market, agg)
    return agg
