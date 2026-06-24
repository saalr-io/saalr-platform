from saalr_core.discovery.types import Quote, CleanContract, CleanChain
from saalr_core.strategies.types import OptionType


def test_clean_chain_strikes_for_expiry_sorted_unique():
    cc = CleanChain(
        underlying="AAPL", as_of="2026-06-10T20:00:00Z", spot=100.0, div_yield=0.0,
        contracts=(
            CleanContract("2026-07-17", 105.0, OptionType.CALL, mid=1.0, iv=0.3, volume=10, open_interest=50),
            CleanContract("2026-07-17", 95.0, OptionType.PUT, mid=1.2, iv=0.32, volume=8, open_interest=40),
            CleanContract("2026-07-17", 105.0, OptionType.PUT, mid=2.0, iv=0.31, volume=5, open_interest=20),
        ),
    )
    assert cc.strikes_for_expiry("2026-07-17") == [95.0, 105.0]
    assert cc.expiries() == ["2026-07-17"]


def test_quote_is_frozen():
    q = Quote("2026-07-17", 100.0, OptionType.CALL, bid=1.0, ask=1.2, iv=0.3, volume=1, open_interest=2)
    assert q.strike == 100.0
