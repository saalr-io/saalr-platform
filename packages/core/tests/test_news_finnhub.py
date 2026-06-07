from datetime import datetime, timezone

import httpx
import pytest

from saalr_core.marketdata.news_finnhub import FinnhubNewsProvider, parse_finnhub
from saalr_core.marketdata.provider import ProviderError

ROWS = [
    {"headline": "Apple beats earnings", "summary": "Strong quarter", "datetime": 1749045000,
     "url": "https://ex/1", "source": "Reuters"},
    {"headline": "", "datetime": 1749045000},  # skipped: no title
    {"headline": "No timestamp"},               # skipped: no datetime
]


def test_parse_finnhub_maps_rows():
    out = parse_finnhub(ROWS, ticker="aapl")
    assert len(out) == 1
    h = out[0]
    assert h.title == "Apple beats earnings" and h.source == "Reuters"
    assert h.tickers == ["AAPL"]
    assert h.published_at == datetime.fromtimestamp(1749045000, tz=timezone.utc)


async def test_provider_requires_key():
    with pytest.raises(ProviderError):
        await FinnhubNewsProvider(None).get_news("AAPL")


async def test_provider_fetches_and_parses():
    def handler(req: httpx.Request) -> httpx.Response:
        assert "company-news" in str(req.url)
        return httpx.Response(200, json=ROWS)

    p = FinnhubNewsProvider("k", transport=httpx.MockTransport(handler))
    out = await p.get_news("AAPL")
    assert len(out) == 1 and out[0].title == "Apple beats earnings"
