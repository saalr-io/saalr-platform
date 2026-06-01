from saalr_core.marketdata.news import parse_news

_RESULTS = [
    {"title": "Acme beats earnings", "description": "Strong quarter.",
     "published_utc": "2024-03-01T13:30:00Z", "publisher": {"name": "Reuters"},
     "article_url": "http://x/1", "tickers": ["ACME"]},
    {"description": "no title", "published_utc": "2024-03-01T14:00:00Z"},   # skipped: no title
    {"title": "No timestamp", "publisher": {"name": "AP"}},                  # skipped: no published_utc
]


def test_parse_news_maps_fields_and_skips_malformed():
    rows = parse_news(_RESULTS)
    assert len(rows) == 1
    h = rows[0]
    assert h.title == "Acme beats earnings"
    assert h.description == "Strong quarter."
    assert h.source == "Reuters" and h.url == "http://x/1"
    assert h.tickers == ["ACME"]
    assert h.published_at.tzinfo is not None
    assert h.published_at.year == 2024 and h.published_at.month == 3 and h.published_at.hour == 13


def test_parse_news_handles_missing_optionals():
    rows = parse_news([{"title": "t", "published_utc": "2024-03-01T00:00:00Z"}])
    assert len(rows) == 1
    assert rows[0].description == "" and rows[0].source == "" and rows[0].tickers == []
