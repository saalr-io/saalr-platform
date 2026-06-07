from equity_screener.report import format_report

_METRICS = {"sharpe": 0.95, "cagr": 0.12, "vol": 0.18, "max_dd": -0.25, "avg_holdings": 7}
_BENCH = {"sharpe": 0.88, "cagr": 0.17}
_COVERAGE = {"screened": 480, "dropped": 20}


def test_report_below_target_and_caveats():
    out = format_report(_METRICS, _BENCH, _COVERAGE)
    assert "Strategy Sharpe : 0.95" in out
    assert "target 1.5: BELOW" in out
    assert "SURVIVORSHIP BIAS" in out
    assert "SHORT HISTORY" in out
    assert "SPLITS" in out


def test_report_above_target_flag():
    out = format_report({**_METRICS, "sharpe": 1.80}, _BENCH, _COVERAGE)
    assert "target 1.5: ABOVE" in out


def test_report_holdings_by_year_and_invested_window():
    out = format_report(
        _METRICS, _BENCH, _COVERAGE,
        holdings_by_year=[(2015, 0), (2016, 0), (2020, 5), (2021, 8)],
    )
    assert "2015:0" in out and "2021:8" in out
    assert "Effective invested window: 2020-2021" in out
