from datetime import date

import numpy as np
import pandas as pd

from equity_screener.backtest import daily_returns, equal_weight_value, sharpe
from equity_screener.fundamentals import AnnualPoint, CompanyFundamentals
from equity_screener.screen import evaluate


def _co(ticker, rev0, growth, shares, ebit, assets, curliab):
    years = range(2004, 2015)

    def s(fn):
        return [AnnualPoint(y, f"{y}-12-31", f"{y + 1}-02-15", fn(y)) for y in years]

    return CompanyFundamentals(
        cik=ticker, ticker=ticker,
        revenue=s(lambda y: rev0 * (growth ** (y - 2004))),
        shares=s(lambda _y: shares), ebit=s(lambda _y: ebit),
        assets=s(lambda _y: assets), current_liabilities=s(lambda _y: curliab),
    )


def test_end_to_end_synthetic():
    universe = {
        "PASS": _co("PASS", 100, 1.15, 1e8, 30, 200, 50),   # passes (100M shares -> >$1B cap)
        "DILUTE": _co("DILUTE", 100, 1.15, 1e8, 30, 200, 50),
    }
    universe["DILUTE"] = CompanyFundamentals(
        "DILUTE", "DILUTE", universe["DILUTE"].revenue,
        [AnnualPoint(y, f"{y}-12-31", f"{y+1}-02-15", 1e8 if y == 2004 else 3e8) for y in range(2004, 2015)],
        universe["DILUTE"].ebit, universe["DILUTE"].assets, universe["DILUTE"].current_liabilities,
    )
    # June 2015: FY2014 10-Ks (filed Feb 2015) are available -> 11 FYs satisfy the 10y lookback
    as_of = date(2015, 6, 1)
    passers = [t for t, f in universe.items() if (r := evaluate(f, 50.0, as_of)) and r.passed]
    assert passers == ["PASS"]

    idx = pd.bdate_range("2015-01-02", periods=252)
    prices = pd.DataFrame({"PASS": np.linspace(50, 60, 252), "DILUTE": np.linspace(50, 40, 252)}, index=idx)
    value = equal_weight_value(prices, {idx[0]: passers})
    assert sharpe(daily_returns(value)) > 0  # PASS rose -> positive sharpe
