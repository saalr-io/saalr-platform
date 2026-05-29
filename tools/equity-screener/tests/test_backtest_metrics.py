import pandas as pd

from equity_screener.backtest import cagr_from_value, max_drawdown, sharpe


def test_sharpe_known_series():
    # daily returns alternating +/- around a positive mean
    r = pd.Series([0.001, -0.0005] * 500)
    expected = (r.mean() / r.std(ddof=0)) * (252 ** 0.5)
    assert abs(sharpe(r) - expected) < 1e-9


def test_sharpe_zero_vol_is_zero():
    assert sharpe(pd.Series([0.0, 0.0, 0.0])) == 0.0


def test_max_drawdown():
    value = pd.Series([100, 120, 90, 110])  # peak 120 -> trough 90 = -25%
    assert abs(max_drawdown(value) - (-0.25)) < 1e-9


def test_cagr_from_value():
    value = pd.Series([100.0, 200.0], index=pd.to_datetime(["2015-01-01", "2025-01-01"]))
    # calendar-day annualization (3653 days / 365.25 ~ 10.0014y) differs slightly from exact 10y
    assert abs(cagr_from_value(value) - ((2.0) ** (1 / 10) - 1)) < 1e-4
