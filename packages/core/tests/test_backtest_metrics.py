# packages/core/tests/test_backtest_metrics.py

import pytest

from saalr_core.backtest import metrics as m


def test_total_return():
    assert m.total_return([100.0, 110.0]) == 110.0 / 100.0 - 1.0
    assert m.total_return([100.0]) == 0.0
    assert m.total_return([]) == 0.0


def test_daily_returns():
    assert m.daily_returns([100.0, 110.0, 121.0]) == pytest.approx([0.1, 0.1])
    assert m.daily_returns([100.0]) == []


def test_annualized_return_one_year_flat_growth():
    # 10% over ~365 days -> ~10% annualized
    r = m.annualized_return([100.0, 110.0], 365)
    assert abs(r - 0.10) < 1e-6


def test_max_drawdown_is_negative_trough():
    # peak 120 then trough 90 -> -25%
    assert abs(m.max_drawdown([100.0, 120.0, 90.0, 110.0]) - (-0.25)) < 1e-9
    assert m.max_drawdown([]) == 0.0


def test_sharpe_zero_variance_is_zero():
    assert m.sharpe([0.01, 0.01, 0.01], rf=0.0) == 0.0


def test_sharpe_positive_for_steady_gains():
    assert m.sharpe([0.01, 0.012, 0.009, 0.011], rf=0.0) > 0


def test_sortino_ignores_upside_volatility():
    # all-positive returns -> no downside deviation -> 0.0 by convention
    assert m.sortino([0.01, 0.02, 0.03], rf=0.0) == 0.0
    assert m.sortino([0.02, -0.01, 0.02, -0.01], rf=0.0) > 0


def test_win_rate_and_avg_trade_pnl():
    assert m.win_rate([10.0, -5.0, 3.0, 0.0]) == 0.5  # >0 wins: 10,3 of 4
    assert m.avg_trade_pnl([10.0, -5.0, 3.0, 0.0]) == 2.0
    assert m.win_rate([]) == 0.0
    assert m.avg_trade_pnl([]) == 0.0
