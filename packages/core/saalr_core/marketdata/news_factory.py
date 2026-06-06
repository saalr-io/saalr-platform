from __future__ import annotations

from datetime import datetime

from .news import MassiveNewsProvider, RawHeadline
from .news_finnhub import FinnhubNewsProvider
from .news_rss import RssNewsProvider
from .provider import ProviderError


class CompositeNewsProvider:
    """Try providers in order; return the first non-empty result. Swallow ProviderError until the
    last; re-raise only if EVERY provider errored (none returned anything)."""

    def __init__(self, providers: list) -> None:
        self._providers = providers

    async def get_news(
        self, ticker: str, limit: int = 50, published_after: datetime | None = None
    ) -> list[RawHeadline]:
        last_err: ProviderError | None = None
        returned = False
        for p in self._providers:
            try:
                items = await p.get_news(ticker, limit=limit, published_after=published_after)
            except ProviderError as exc:
                last_err = exc
                continue
            returned = True
            if items:
                return items
        if not returned and last_err is not None:
            raise last_err
        return []


def build_news_provider(settings):
    """Select the news provider from settings. 'auto' = Finnhub (if keyed) then RSS fallback."""
    mode = getattr(settings, "news_provider", "auto") or "auto"
    if mode == "massive":
        return MassiveNewsProvider(settings.massive_api_key)
    if mode == "finnhub":
        return FinnhubNewsProvider(settings.finnhub_api_key)
    if mode == "rss":
        return RssNewsProvider()
    providers: list = []
    if getattr(settings, "finnhub_api_key", None):
        providers.append(FinnhubNewsProvider(settings.finnhub_api_key))
    providers.append(RssNewsProvider())
    return CompositeNewsProvider(providers)
