import json
import pathlib

from saalr_core.marketdata.massive import parse_results
from saalr_core.pricing.types import OptionKind

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_parse_results_maps_contracts():
    data = json.loads((FIX / "massive_snapshot.json").read_text())
    contracts = parse_results(data["results"])
    assert len(contracts) == 2
    c = contracts[0]
    assert c.kind is OptionKind.CALL
    assert c.strike == 180
    assert c.expiry == "2026-06-21"
    assert c.bid == 7.1 and c.ask == 7.3
    assert c.last == 7.2
    assert c.volume == 1200 and c.open_interest == 3400
    assert c.vendor_iv == 0.262
    assert c.vendor_delta == 0.58
    assert contracts[1].kind is OptionKind.PUT


def test_parse_results_handles_session_field():
    # Massive's unified snapshot uses "session" instead of legacy "day"
    rows = [{
        "details": {"contract_type": "call", "strike_price": 100, "expiration_date": "2026-09-18"},
        "last_quote": {"bid": 1.0, "ask": 1.2},
        "session": {"close": 1.1, "volume": 50},
        "open_interest": 75,
        "implied_volatility": 0.3,
        "greeks": {"delta": 0.5, "gamma": 0.01, "theta": -0.02, "vega": 0.05},
    }]
    contracts = parse_results(rows)
    assert contracts[0].last == 1.1
    assert contracts[0].volume == 50
