import time

import requests

from .fundamentals import AnnualPoint, CompanyFundamentals

SEC_HEADERS = {"User-Agent": "saalr-research equity-screener (research@saalr.local)"}

_REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]
_SHARES_TAGS = ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]


def fetch_company_facts(cik: str, *, session: requests.Session | None = None) -> dict:
    s = session or requests.Session()
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
    resp = s.get(url, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    time.sleep(0.12)  # stay under SEC's ~10 req/s
    return resp.json()


def _annual_points(facts: dict, namespaces: list[str], tags: list[str]) -> list[AnnualPoint]:
    """First tag (across given namespaces) that yields annual (10-K, FY) points."""
    for ns in namespaces:
        for tag in tags:
            node = facts.get("facts", {}).get(ns, {}).get(tag)
            if not node:
                continue
            points: list[AnnualPoint] = []
            for _unit, entries in node.get("units", {}).items():
                for e in entries:
                    if e.get("form") == "10-K" and e.get("fp") == "FY" and e.get("fy") and e.get("filed"):
                        points.append(
                            AnnualPoint(int(e["fy"]), e["end"], e["filed"], float(e["val"]))
                        )
            if points:
                return points
    return []


def extract_fundamentals(facts: dict, cik: str, ticker: str) -> CompanyFundamentals:
    return CompanyFundamentals(
        cik=cik,
        ticker=ticker,
        revenue=_annual_points(facts, ["us-gaap"], _REVENUE_TAGS),
        shares=_annual_points(facts, ["dei", "us-gaap"], _SHARES_TAGS),
        ebit=_annual_points(facts, ["us-gaap"], ["OperatingIncomeLoss"]),
        assets=_annual_points(facts, ["us-gaap"], ["Assets"]),
        current_liabilities=_annual_points(facts, ["us-gaap"], ["LiabilitiesCurrent"]),
    )
