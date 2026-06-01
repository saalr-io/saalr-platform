from datetime import date

from saalr_brokers.alpaca import map_status, occ_symbol


def test_occ_symbol_call_and_put():
    assert occ_symbol("AAPL", date(2025, 6, 20), "CALL", 100.0) == "AAPL250620C00100000"
    assert occ_symbol("AAPL", date(2025, 6, 20), "PUT", 100.0) == "AAPL250620P00100000"


def test_occ_symbol_strike_milli_padding():
    assert occ_symbol("SPY", date(2026, 1, 16), "CALL", 5.5).endswith("C00005500")
    assert occ_symbol("SPY", date(2026, 1, 16), "PUT", 432.5).endswith("P00432500")
    assert occ_symbol("CE", date(2026, 1, 16), "CE", 10) == "CE260116C00010000"  # CE option_type -> call


def test_map_status_known_and_unknown():
    assert map_status("new") == "submitted"
    assert map_status("accepted") == "submitted"
    assert map_status("partially_filled") == "partial"
    assert map_status("filled") == "filled"
    assert map_status("canceled") == "cancelled"
    assert map_status("expired") == "cancelled"
    assert map_status("rejected") == "rejected"
    assert map_status("suspended") == "rejected"
    assert map_status("something_new") == "submitted"  # conservative default


def test_map_status_handles_enum_like():
    class _S:
        value = "FILLED"
    assert map_status(_S()) == "filled"
