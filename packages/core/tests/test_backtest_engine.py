# packages/core/tests/test_backtest_engine.py
from datetime import date, timedelta

from saalr_core.backtest.engine import BacktestParams, run_backtest_engine
from saalr_core.backtest.template import RelativeTemplate
from saalr_core.strategies.types import OptionLeg, OptionType, Side, StrategyConfig


def _closes(start: date, prices: list[float]) -> dict:
    return {start + timedelta(days=i): p for i, p in enumerate(prices)}


def _long_call(dte_expiry: str) -> StrategyConfig:
    return StrategyConfig(
        underlying="X",
        legs=[OptionLeg(OptionType.CALL, Side.BUY, 100.0, dte_expiry, 1)],
    )


def _params(start: date, end: date, **kw) -> BacktestParams:
    base = dict(start=start, end=end, initial_capital=100_000.0, rate=0.04,
                vol_lookback=20, include_costs=False)
    base.update(kw)
    return BacktestParams(**base)


def test_long_call_on_flat_underlying_loses_to_theta():
    start = date(2025, 1, 1)
    prices = [100.0] * 120  # dead flat
    closes = _closes(start, prices)
    # ref_date is first sim day; template built against it
    cfg = _long_call("2025-02-15")  # ~45 DTE from 2025-01-01
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=start)
    res = run_backtest_engine(closes, t, _params(start, start + timedelta(days=119)))
    assert res["metrics"]["total_return"] < 0  # long premium decays on flat tape
    assert res["model"] == "bsm"
    assert res["iv_source"] == "realized_vol"
    assert res["approximate"] is True
    assert res["metrics"]["trades"] >= 1
    # every metric finite
    for v in res["metrics"].values():
        assert v == v  # not NaN


def test_long_call_on_rising_underlying_profits():
    start = date(2025, 1, 1)
    prices = [100.0 + i * 0.5 for i in range(120)]  # steady uptrend
    closes = _closes(start, prices)
    cfg = _long_call("2025-02-15")
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=start)
    res = run_backtest_engine(closes, t, _params(start, start + timedelta(days=119)))
    assert res["metrics"]["total_return"] > 0


def test_calendar_cycles_on_front_expiry_and_is_net_positive_on_flat_tape():
    start = date(2025, 1, 1)
    prices = [100.0] * 200
    closes = _closes(start, prices)
    cfg = StrategyConfig(
        underlying="X",
        legs=[
            OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2025-02-01", 1),  # front ~31d
            OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2025-04-01", 1),  # back ~90d
        ],
    )
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=start)
    res = run_backtest_engine(closes, t, _params(start, start + timedelta(days=199)))
    # ~31-day front cycles over ~199 days -> multiple completed cycles
    assert res["metrics"]["trades"] >= 4
    # short front decays faster than long back on a flat tape -> net positive
    assert res["metrics"]["total_return"] > 0


def test_too_few_bars_raises():
    start = date(2025, 1, 1)
    closes = _closes(start, [100.0])  # one bar
    cfg = _long_call("2025-02-15")
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=start)
    try:
        run_backtest_engine(closes, t, _params(start, start))
        assert False, "expected ValueError"
    except ValueError:
        pass
