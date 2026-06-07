from datetime import datetime, timezone

import httpx

from saalr_core.marketdata.news_rss import RssNewsProvider, parse_rss

YAHOO = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Apple hits record high</title>
<description>&lt;p&gt;Shares &lt;b&gt;jump&lt;/b&gt; today&lt;/p&gt;</description>
<pubDate>Wed, 04 Jun 2026 14:30:00 GMT</pubDate><link>https://ex/1</link></item>
<item><title>No date here</title><link>https://ex/2</link></item>
</channel></rss>"""

GOOGLE = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Apple news from Google</title><description>summary</description>
<pubDate>Thu, 05 Jun 2026 09:00:00 GMT</pubDate><link>https://ex/3</link></item>
</channel></rss>"""


def test_parse_rss_maps_items_and_strips_html():
    out = parse_rss(YAHOO, source="yahoo", ticker="aapl")
    assert len(out) == 1  # the dateless item is skipped
    h = out[0]
    assert h.title == "Apple hits record high"
    assert "jump" in h.description and "<" not in h.description
    assert h.source == "yahoo" and h.tickers == ["AAPL"]
    assert h.published_at == datetime(2026, 6, 4, 14, 30, tzinfo=timezone.utc)


def test_parse_rss_bad_xml_returns_empty():
    assert parse_rss(b"not xml at all", source="yahoo", ticker="x") == []


async def test_provider_falls_back_to_google_when_yahoo_empty():
    def handler(req: httpx.Request) -> httpx.Response:
        body = GOOGLE if "news.google.com" in str(req.url) else b"<rss><channel></channel></rss>"
        return httpx.Response(200, content=body)

    p = RssNewsProvider(transport=httpx.MockTransport(handler))
    out = await p.get_news("AAPL")
    assert len(out) == 1 and out[0].source == "google"
