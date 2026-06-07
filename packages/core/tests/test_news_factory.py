from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from saalr_core.marketdata.news import RawHeadline
from saalr_core.marketdata.news_factory import CompositeNewsProvider, build_news_provider
from saalr_core.marketdata.news_finnhub import FinnhubNewsProvider
from saalr_core.marketdata.news_rss import RssNewsProvider
from saalr_core.marketdata.provider import ProviderError


def _hl(title: str) -> RawHeadline:
    return RawHeadline(title, "", datetime(2026, 6, 4, tzinfo=timezone.utc), "stub", "http://x", ["AAPL"])


class _Stub:
    def __init__(self, *, items=None, error=False):
        self._items, self._error = items or [], error
    async def get_news(self, ticker, limit=50, published_after=None):
        if self._error:
            raise ProviderError("boom")
        return self._items


@dataclass
class _Settings:
    news_provider: str = "auto"
    finnhub_api_key: str | None = None
    massive_api_key: str | None = None


async def test_composite_returns_first_non_empty():
    c = CompositeNewsProvider([_Stub(items=[]), _Stub(items=[_hl("a")]), _Stub(items=[_hl("b")])])
    out = await c.get_news("AAPL")
    assert [h.title for h in out] == ["a"]


async def test_composite_swallows_error_then_uses_next():
    c = CompositeNewsProvider([_Stub(error=True), _Stub(items=[_hl("ok")])])
    out = await c.get_news("AAPL")
    assert [h.title for h in out] == ["ok"]


async def test_composite_reraises_when_all_error():
    c = CompositeNewsProvider([_Stub(error=True), _Stub(error=True)])
    with pytest.raises(ProviderError):
        await c.get_news("AAPL")


def test_build_auto_uses_finnhub_first_then_rss_when_keyed():
    p = build_news_provider(_Settings(finnhub_api_key="k"))
    assert isinstance(p, CompositeNewsProvider)
    assert isinstance(p._providers[0], FinnhubNewsProvider)
    assert isinstance(p._providers[-1], RssNewsProvider)


def test_build_auto_is_rss_only_without_key():
    p = build_news_provider(_Settings())
    assert isinstance(p, CompositeNewsProvider)
    assert len(p._providers) == 1 and isinstance(p._providers[0], RssNewsProvider)


def test_build_respects_explicit_override():
    assert isinstance(build_news_provider(_Settings(news_provider="rss")), RssNewsProvider)
    assert isinstance(build_news_provider(_Settings(news_provider="finnhub", finnhub_api_key="k")), FinnhubNewsProvider)
