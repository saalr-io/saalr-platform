import numpy as np
import pandas as pd

from equity_screener.backtest import equal_weight_value


def test_equal_weight_value_two_stocks():
    idx = pd.bdate_range("2015-01-01", periods=10)
    prices = pd.DataFrame(
        {"A": np.linspace(10, 11, 10), "B": np.linspace(20, 22, 10)}, index=idx
    )
    # one rebalance at the start holding both equally
    holdings = {idx[0]: ["A", "B"]}
    value = equal_weight_value(prices, holdings, start_cash=1000.0)
    assert abs(value.iloc[0] - 1000.0) < 1e-6
    # A +10%, B +10% over window -> ~ +10%
    assert abs(value.iloc[-1] / value.iloc[0] - 1.10) < 1e-6


def test_empty_holdings_holds_cash():
    idx = pd.bdate_range("2015-01-01", periods=5)
    prices = pd.DataFrame({"A": np.linspace(10, 12, 5)}, index=idx)
    value = equal_weight_value(prices, {idx[0]: []}, start_cash=1000.0)
    assert (value == 1000.0).all()
