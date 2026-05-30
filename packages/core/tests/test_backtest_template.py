# packages/core/tests/test_backtest_template.py
from datetime import date

import pytest

from saalr_core.backtest.template import RelativeTemplate
from saalr_core.strategies.types import (
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
    Side,
    StrategyConfig,
)


def _vertical() -> StrategyConfig:
    return StrategyConfig(
        underlying="AAPL",
        legs=[
            OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2025-03-21", 1),
            OptionLeg(OptionType.CALL, Side.SELL, 110.0, "2025-03-21", 1),
        ],
    )


def _calendar() -> StrategyConfig:
    return StrategyConfig(
        underlying="AAPL",
        legs=[
            OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2025-02-21", 1),  # front
            OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2025-04-21", 1),  # back
        ],
    )


def test_from_config_relative_legs_and_cycle_dte():
    ref = date(2025, 1, 1)
    t = RelativeTemplate.from_config(_vertical(), ref_spot=100.0, ref_date=ref)
    assert t.cycle_dte == (date(2025, 3, 21) - ref).days
    assert [round(rl.moneyness, 4) for rl in t.legs] == [1.0, 1.1]
    assert all(rl.dte == t.cycle_dte for rl in t.legs)  # same expiry vertical


def test_calendar_keeps_per_leg_dte_and_front_cycle():
    ref = date(2025, 1, 1)
    t = RelativeTemplate.from_config(_calendar(), ref_spot=100.0, ref_date=ref)
    front = (date(2025, 2, 21) - ref).days
    back = (date(2025, 4, 21) - ref).days
    assert sorted(rl.dte for rl in t.legs) == [front, back]
    assert t.cycle_dte == front  # min


def test_instantiate_rounds_strikes_and_sets_per_leg_expiry():
    ref = date(2025, 1, 1)
    t = RelativeTemplate.from_config(_calendar(), ref_spot=100.0, ref_date=ref)
    legs = t.instantiate(date(2025, 6, 2), spot=207.4, strike_increment=1.0)
    # both legs ATM (moneyness 1.0) -> strike rounds to 207
    assert all(leg.strike == 207.0 for leg in legs)
    # per-leg expiries preserved: roll_date + each leg's own dte
    expiries = sorted(leg.expiry for leg in legs)
    assert expiries == ["2025-07-23", "2025-09-20"]  # +51d (front), +110d (back)


def test_equity_and_cash_legs_carry_through():
    ref = date(2025, 1, 1)
    cfg = StrategyConfig(
        underlying="AAPL",
        legs=[
            OptionLeg(OptionType.CALL, Side.SELL, 105.0, "2025-03-21", 1),
            EquityLeg(Side.BUY, 100),
            CashLeg(5000.0),
        ],
    )
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=ref)
    legs = t.instantiate(date(2025, 1, 1), spot=100.0)
    kinds = sorted(leg.kind for leg in legs)
    assert kinds == ["cash", "equity", "option"]


def test_no_option_legs_raises():
    cfg = StrategyConfig(underlying="AAPL", legs=[EquityLeg(Side.BUY, 100)])
    with pytest.raises(ValueError, match="no option legs"):
        RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=date(2025, 1, 1))


def test_expired_leg_raises():
    cfg = StrategyConfig(
        underlying="AAPL",
        legs=[OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2024-12-01", 1)],
    )
    with pytest.raises(ValueError, match="not after"):
        RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=date(2025, 1, 1))
