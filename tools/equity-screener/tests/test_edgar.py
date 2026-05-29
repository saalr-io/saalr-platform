import json
from pathlib import Path

from equity_screener.edgar import extract_fundamentals

FIXTURE = Path(__file__).parent / "fixtures" / "companyfacts_sample.json"


def test_extract_annual_only_and_dedup():
    facts = json.loads(FIXTURE.read_text())
    f = extract_fundamentals(facts, cik="0000000001", ticker="SMP")
    rev_years = {p.fiscal_year: p.value for p in f.revenue}
    assert rev_years == {2013: 800.0, 2014: 1000.0}  # Q1 10-Q excluded
    assert f.ebit[0].value == 300.0
    assert f.assets[0].value == 2000.0
    assert f.current_liabilities[0].value == 500.0
    assert f.shares[0].value == 100.0


def _fy(fy, val, filed=None):
    return {"fy": fy, "fp": "FY", "form": "10-K", "end": f"{fy}-12-31",
            "filed": filed or f"{fy + 1}-02-15", "val": val}


def test_revenue_tags_merge_across_eras():
    # Real companies switch revenue tags over time: the old `Revenues`/`SalesRevenueNet`
    # tags hold pre-2018 years, the ASC-606 tag holds 2018+. Extraction must MERGE them
    # (priority order fills gaps) so the full multi-year series is assembled.
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [_fy(2018, 5000)]}},  # stray single year, highest priority
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            _fy(2018, 4999), _fy(2019, 5200), _fy(2020, 5500),
        ]}},
        "SalesRevenueNet": {"units": {"USD": [_fy(2016, 4500), _fy(2017, 4700)]}},
    }}}
    f = extract_fundamentals(facts, cik="0000000002", ticker="MRG")
    rev = {p.fiscal_year: p.value for p in f.revenue}
    # union of years across all three tags; 2018 taken from highest-priority `Revenues`
    assert rev == {2016: 4500.0, 2017: 4700.0, 2018: 5000.0, 2019: 5200.0, 2020: 5500.0}
