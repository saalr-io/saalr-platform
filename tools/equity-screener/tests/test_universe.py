from equity_screener.universe import parse_ticker_cik_map


def test_parse_ticker_cik_map():
    raw = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft"},
    }
    m = parse_ticker_cik_map(raw)
    assert m["AAPL"] == "0000320193"
    assert m["MSFT"] == "0000789019"
