import pytest

from saalr_core.strategies.templates import build, list_templates
from saalr_core.strategies.types import OptionType, Side


def test_catalog_has_expected_keys():
    keys = {t["key"] for t in list_templates()}
    assert {"bull_call_spread", "iron_condor", "covered_call", "cash_secured_put"} <= keys
    for t in list_templates():
        assert t["category"] in ("bullish", "bearish", "neutral")


def test_bull_call_spread_legs():
    cfg = build("bull_call_spread", underlying="AAPL", expiry="2026-12-18", atm_strike=100.0, width=10.0)
    assert cfg.underlying == "AAPL"
    assert len(cfg.legs) == 2
    long_leg = [leg for leg in cfg.legs if leg.side is Side.BUY][0]
    short_leg = [leg for leg in cfg.legs if leg.side is Side.SELL][0]
    assert long_leg.option_type is OptionType.CALL and long_leg.strike == 100.0
    assert short_leg.strike == 110.0


def test_iron_condor_four_legs():
    cfg = build("iron_condor", underlying="AAPL", expiry="2026-12-18", atm_strike=100.0, width=10.0)
    assert len(cfg.legs) == 4


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        build("does_not_exist", underlying="AAPL", expiry="2026-12-18", atm_strike=100.0)
