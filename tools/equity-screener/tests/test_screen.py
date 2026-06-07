from datetime import date

from equity_screener.fundamentals import AnnualPoint, CompanyFundamentals
from equity_screener.screen import evaluate


def _series(values: dict[int, float]) -> list[AnnualPoint]:
    return [AnnualPoint(y, f"{y}-12-31", f"{y + 1}-02-15", v) for y, v in values.items()]


def _company() -> CompanyFundamentals:
    years = range(2004, 2015)  # 2004..2014 (11 FYs available as of 2015 rebalance)
    return CompanyFundamentals(
        cik="0000000001",
        ticker="GOOD",
        revenue=_series({y: 100.0 * (1.15 ** (y - 2004)) for y in years}),  # ~15% CAGR
        shares=_series({y: 1e8 for y in years}),                             # flat 100M shares
        ebit=_series({y: 30.0 for y in years}),
        assets=_series({y: 200.0 for y in years}),
        current_liabilities=_series({y: 50.0 for y in years}),               # ROCE = 30/150 = 20%
    )


def test_quality_company_passes():
    r = evaluate(_company(), price_at_t=50.0, as_of=date(2015, 6, 1))
    assert r is not None and r.passed
    assert r.reasons["dilution"] and r.reasons["sales_growth"]
    assert r.reasons["roce"] and r.reasons["market_cap"]


def test_dilution_fails_when_shares_grew():
    c = _company()
    diluted = CompanyFundamentals(
        c.cik, c.ticker, c.revenue,
        _series({y: 1000.0 if y == 2004 else 2000.0 for y in range(2004, 2015)}),
        c.ebit, c.assets, c.current_liabilities,
    )
    r = evaluate(diluted, price_at_t=50.0, as_of=date(2015, 6, 1))
    assert r is not None and not r.passed and not r.reasons["dilution"]


def test_insufficient_history_returns_none():
    short = CompanyFundamentals("0000000002", "NEW",
        _series({2013: 100.0, 2014: 130.0}), _series({2013: 10.0, 2014: 10.0}),
        _series({2013: 5.0, 2014: 5.0}), _series({2013: 50.0, 2014: 50.0}),
        _series({2013: 10.0, 2014: 10.0}))
    assert evaluate(short, price_at_t=50.0, as_of=date(2015, 6, 1)) is None
