import pytest

from saalr_core.strategies.templates import build, list_templates
from saalr_core.strategies.types import EquityLeg, OptionLeg, OptionType, Side

ALL_KEYS = {
    "bull_call_spread", "bear_put_spread", "long_straddle", "long_strangle",
    "iron_condor", "iron_butterfly", "covered_call", "cash_secured_put", "long_calendar",
    "bull_put_spread", "bear_call_spread", "short_straddle", "short_strangle",
    "protective_put", "collar", "call_ratio_spread", "put_ratio_spread",
    "jade_lizard", "call_butterfly", "put_butterfly", "broken_wing_butterfly",
}

MARKET_VIEWS = {"bullish", "bearish", "neutral", "volatile"}
VOL_VIEWS = {"long_vol", "short_vol", "neutral"}
NETS = {"debit", "credit", "mixed"}
DEFINED = {"defined", "undefined"}
COMPLEXITIES = {"beginner", "intermediate", "advanced"}

_BUILD_ARGS = dict(underlying="AAPL", expiry="2026-12-18", atm_strike=100.0, width=10.0)


def _opts(cfg):
    return [leg for leg in cfg.legs if isinstance(leg, OptionLeg)]


def test_catalog_has_all_21_keys():
    keys = {t["key"] for t in list_templates()}
    assert keys == ALL_KEYS


def test_every_template_has_complete_valid_metadata():
    # Slice B's recommender trusts this schema — guard it.
    for t in list_templates():
        assert t["market_view"] in MARKET_VIEWS, t["key"]
        assert t["vol_view"] in VOL_VIEWS, t["key"]
        assert t["net"] in NETS, t["key"]
        assert t["risk"] in DEFINED, t["key"]
        assert t["reward"] in DEFINED, t["key"]
        assert t["complexity"] in COMPLEXITIES, t["key"]
        assert isinstance(t["legs"], int) and t["legs"] >= 1, t["key"]
        assert t["name"] and t["description"], t["key"]


def test_every_key_builds_with_legs_matching_metadata_count():
    meta = {t["key"]: t for t in list_templates()}
    for key in ALL_KEYS:
        cfg = build(key, **_BUILD_ARGS)
        assert len(cfg.legs) == meta[key]["legs"], key


def test_long_straddle_is_volatile_long_vol():
    meta = {t["key"]: t for t in list_templates()}["long_straddle"]
    assert meta["market_view"] == "volatile" and meta["vol_view"] == "long_vol"


def test_bull_put_spread_is_a_put_credit_spread():
    cfg = build("bull_put_spread", **_BUILD_ARGS)
    legs = _opts(cfg)
    assert len(legs) == 2 and all(leg.option_type is OptionType.PUT for leg in legs)
    short = [leg for leg in legs if leg.side is Side.SELL][0]
    long = [leg for leg in legs if leg.side is Side.BUY][0]
    assert short.strike == 100.0 and long.strike == 90.0  # sell k, buy k-w


def test_bear_call_spread_is_a_call_credit_spread():
    cfg = build("bear_call_spread", **_BUILD_ARGS)
    legs = _opts(cfg)
    short = [leg for leg in legs if leg.side is Side.SELL][0]
    long = [leg for leg in legs if leg.side is Side.BUY][0]
    assert all(leg.option_type is OptionType.CALL for leg in legs)
    assert short.strike == 100.0 and long.strike == 110.0  # sell k, buy k+w


def test_call_ratio_spread_sells_two_against_one():
    cfg = build("call_ratio_spread", **_BUILD_ARGS)
    short = [leg for leg in _opts(cfg) if leg.side is Side.SELL][0]
    long = [leg for leg in _opts(cfg) if leg.side is Side.BUY][0]
    assert long.qty == 1 and short.qty == 2
    assert long.strike == 100.0 and short.strike == 110.0


def test_call_butterfly_is_1_2_1():
    cfg = build("call_butterfly", **_BUILD_ARGS)
    legs = _opts(cfg)
    assert all(leg.option_type is OptionType.CALL for leg in legs)
    body = [leg for leg in legs if leg.side is Side.SELL][0]
    wings = [leg for leg in legs if leg.side is Side.BUY]
    assert body.qty == 2 and body.strike == 100.0
    assert sorted(leg.strike for leg in wings) == [90.0, 110.0]


def test_broken_wing_butterfly_has_asymmetric_upper_wing():
    cfg = build("broken_wing_butterfly", **_BUILD_ARGS)
    wings = sorted(leg.strike for leg in _opts(cfg) if leg.side is Side.BUY)
    assert wings == [90.0, 120.0]  # k-w and k+2w


def test_collar_wraps_long_stock_with_put_and_call():
    cfg = build("collar", **_BUILD_ARGS)
    assert any(isinstance(leg, EquityLeg) for leg in cfg.legs)
    opts = _opts(cfg)
    assert {leg.option_type for leg in opts} == {OptionType.PUT, OptionType.CALL}
    put = [leg for leg in opts if leg.option_type is OptionType.PUT][0]
    call = [leg for leg in opts if leg.option_type is OptionType.CALL][0]
    assert put.side is Side.BUY and put.strike == 90.0
    assert call.side is Side.SELL and call.strike == 110.0


def test_jade_lizard_short_put_plus_short_call_spread():
    cfg = build("jade_lizard", **_BUILD_ARGS)
    legs = _opts(cfg)
    assert len(legs) == 3
    put = [leg for leg in legs if leg.option_type is OptionType.PUT][0]
    calls = sorted((leg for leg in legs if leg.option_type is OptionType.CALL), key=lambda x: x.strike)
    assert put.side is Side.SELL and put.strike == 90.0
    assert calls[0].side is Side.SELL and calls[0].strike == 110.0   # short call k+w
    assert calls[1].side is Side.BUY and calls[1].strike == 120.0    # long call k+2w


def test_protective_put_is_stock_plus_long_put():
    cfg = build("protective_put", **_BUILD_ARGS)
    assert any(isinstance(leg, EquityLeg) for leg in cfg.legs)
    put = _opts(cfg)[0]
    assert put.side is Side.BUY and put.option_type is OptionType.PUT and put.strike == 90.0


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        build("does_not_exist", **_BUILD_ARGS)
