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
