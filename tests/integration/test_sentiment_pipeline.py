from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from saalr_core.marketdata.news import RawHeadline
from saalr_core.sentiment import pipeline, repo
from saalr_core.sentiment.types import Label, ScoredHeadline

_NOW = datetime(2025, 1, 10, tzinfo=timezone.utc)


class _StubProvider:
    def __init__(self, heads):
        self._heads = heads
        self.calls = []

    async def get_news(self, symbol, limit=50, published_after=None):
        self.calls.append((symbol, published_after))
        return self._heads


class _StubScorer:
    def score_headlines(self, headlines):
        return [ScoredHeadline(h.published_at, 0.8, 0.9, Label.BULLISH, h.title) for h in headlines]


async def test_refresh_persists_and_latest_reads(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol='AAPL'"))
    heads = [RawHeadline("Acme beats", "", _NOW - timedelta(hours=2), "R", "u", ["AAPL"])]
    provider = _StubProvider(heads)
    async with app_sessionmaker() as s, s.begin():
        agg = await pipeline.refresh_symbol(s, provider, _StubScorer(), "AAPL", "US", _NOW)
    assert agg["confident"] is True and agg["score"] > 0
    # the provider was asked for news after (as_of - lookback)
    assert provider.calls[0][1] == _NOW - timedelta(hours=168)

    async with app_sessionmaker() as s:
        latest = await repo.latest_sentiment(s, "AAPL", "US")
    assert latest is not None and latest["score"] > 0 and latest["label"] == "bullish"


async def test_latest_is_none_when_empty(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM news_sentiment WHERE symbol='NONE'"))
    async with app_sessionmaker() as s:
        assert await repo.latest_sentiment(s, "NONE", "US") is None
