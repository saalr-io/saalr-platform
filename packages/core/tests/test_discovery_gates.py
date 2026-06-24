from saalr_core.discovery.gates import clean_quotes, is_free_lunch
from saalr_core.discovery.types import Quote
from saalr_core.strategies.types import OptionType


def _q(strike, bid, ask, kind=OptionType.PUT):
    return Quote("2026-07-17", strike, kind, bid=bid, ask=ask, iv=0.3, volume=10, open_interest=50)


def test_clean_quotes_drops_zero_bid_crossed_and_missing():
    quotes = [
        _q(100, 1.0, 1.2),      # ok -> mid 1.1
        _q(95, 0.0, 0.5),       # zero bid -> dropped (DATA-3)
        _q(90, 1.5, 1.0),       # crossed bid>ask -> dropped (DATA-3)
        _q(85, None, 1.0),      # missing bid -> dropped
    ]
    clean, dropped = clean_quotes(quotes)
    assert [c.strike for c in clean] == [100.0]
    assert clean[0].mid == 1.1
    reasons = {d["strike"]: d["reason"] for d in dropped}
    assert reasons == {95.0: "zero_bid", 90.0: "crossed", 85.0: "missing_quote"}


def test_is_free_lunch_flags_credit_with_nonnegative_payoff():
    # net credit (premium < 0) AND payoff >= 0 everywhere == bad quote (RANK-2)
    credit_curve = [(0.0, 10.0), (100.0, 5.0), (200.0, 0.0)]
    assert is_free_lunch(net_premium=-110.0, curve=credit_curve) is True


def test_is_free_lunch_false_for_normal_credit_spread():
    # normal credit spread loses money below the short strike
    curve = [(0.0, -390.0), (100.0, 110.0), (200.0, 110.0)]
    assert is_free_lunch(net_premium=-110.0, curve=curve) is False
