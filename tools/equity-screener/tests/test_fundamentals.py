from datetime import date

from equity_screener.fundamentals import AnnualPoint, cagr, points_as_of, roce


def test_cagr_basic():
    assert cagr(100.0, 200.0, 10) == (2.0) ** (1 / 10) - 1
    assert cagr(0.0, 200.0, 10) is None
    assert cagr(100.0, 200.0, 0) is None


def test_roce():
    assert roce(20.0, 200.0, 100.0) == 20.0 / 100.0
    assert roce(20.0, 100.0, 100.0) is None  # capital employed <= 0


def test_points_as_of_filters_and_dedups():
    pts = [
        AnnualPoint(2013, "2013-12-31", "2014-02-01", 10.0),
        AnnualPoint(2014, "2014-12-31", "2015-02-01", 20.0),
        AnnualPoint(2014, "2014-12-31", "2015-05-01", 21.0),  # restatement, later filing
        AnnualPoint(2015, "2015-12-31", "2016-02-01", 30.0),
    ]
    out = points_as_of(pts, date(2016, 1, 1))
    # 2015 filed 2016-02 is after as_of -> excluded; 2014 dedups to the latest filed on/before
    assert [(p.fiscal_year, p.value) for p in out] == [(2013, 10.0), (2014, 21.0)]
