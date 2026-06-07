import json
import pathlib
from datetime import date

from saalr_core.marketdata.massive import _chain_query_params, parse_results
from saalr_core.pricing.types import OptionKind

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_chain_query_params_bounds_strikes_and_expiry():
    # SPY-sized chains are unusable unbisected: window strikes to ATM +-20% and cap the
    # expiry horizon so the provider returns a few hundred contracts, not tens of thousands.
    p = _chain_query_params("k", spot=600.0, atm_band=0.20, expiry_horizon_days=90, today=date(2026, 6, 5))
    assert p["strike_price.gte"] == 480.0
    assert p["strike_price.lte"] == 720.0
    assert p["expiration_date.gte"] == "2026-06-06"  # tomorrow — skip 0DTE/expired
    assert p["expiration_date.lte"] == "2026-09-03"
    assert p["limit"] == 250
    assert p["apiKey"] == "k"
    assert p["sort"] == "expiration_date" and p["order"] == "asc"


def test_chain_query_params_skips_strike_window_without_a_spot():
    # market closed / no trade -> can't ATM-bound, but the expiry bounds still apply
    p = _chain_query_params("k", spot=0.0, atm_band=0.20, expiry_horizon_days=90, today=date(2026, 6, 5))
    assert "strike_price.gte" not in p and "strike_price.lte" not in p
    assert p["expiration_date.gte"] == "2026-06-06"
    assert p["expiration_date.lte"] == "2026-09-03"


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
