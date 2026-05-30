import json
import pathlib
from datetime import datetime, timezone

from saalr_core.marketdata.aggregates import parse_aggregates

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_parse_aggregates_maps_bars():
    data = json.loads((FIX / "massive_aggs.json").read_text())
    rows = parse_aggregates(data["results"], "AAPL", "US")
    assert len(rows) == 2
    r = rows[0]
    assert r.symbol == "AAPL" and r.market == "US" and r.interval == "1d"
    assert r.ts == datetime(2024, 12, 31, 0, 0, tzinfo=timezone.utc)
    assert r.open == 250.0 and r.high == 255.5 and r.low == 249.2 and r.close == 254.1
    assert r.volume == 41000000


def test_parse_aggregates_empty():
    assert parse_aggregates([], "AAPL", "US") == []
