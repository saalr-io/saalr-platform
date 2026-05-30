# packages/core/tests/test_strategies_serde.py
import pytest

from saalr_core.strategies.serde import config_from_json
from saalr_core.strategies.types import (
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
    Side,
)


def test_round_trip_all_leg_kinds():
    data = {
        "underlying": "AAPL",
        "legs": [
            {"kind": "option", "option_type": "CALL", "side": "BUY", "strike": 100,
             "expiry": "2025-03-21", "qty": 1, "entry_price": 6.0},
            {"kind": "equity", "side": "SELL", "qty": 100, "entry_price": None},
            {"kind": "cash", "amount": 5000},
        ],
    }
    cfg = config_from_json(data)
    assert cfg.underlying == "AAPL"
    opt, eq, cash = cfg.legs
    assert isinstance(opt, OptionLeg)
    assert opt.option_type is OptionType.CALL and opt.side is Side.BUY
    assert opt.strike == 100.0 and opt.expiry == "2025-03-21" and opt.qty == 1
    assert isinstance(eq, EquityLeg) and eq.side is Side.SELL and eq.qty == 100
    assert isinstance(cash, CashLeg) and cash.amount == 5000.0


def test_kind_defaults_to_option():
    cfg = config_from_json(
        {"underlying": "X", "legs": [
            {"option_type": "PUT", "side": "SELL", "strike": 90, "expiry": "2025-03-21", "qty": 2}
        ]}
    )
    assert isinstance(cfg.legs[0], OptionLeg) and cfg.legs[0].option_type is OptionType.PUT


def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="unknown leg kind"):
        config_from_json({"underlying": "X", "legs": [{"kind": "future"}]})
