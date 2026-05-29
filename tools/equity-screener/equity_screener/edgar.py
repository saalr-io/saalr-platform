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
    """Merge annual (10-K, FY) points across the given namespaces/tags.

    A single concept (e.g. revenue) is reported under different XBRL tags across
    eras — older filings use ``Revenues``/``SalesRevenueNet``; post-ASC-606 filings
    use ``RevenueFromContractWithCustomer...``. Returning only the first non-empty
    tag captures just one era (often <11 FYs), so we merge: tags are tried in
    priority order and the first one that covers a given fiscal year claims it
    (keeping every filing for that year so point-in-time dedup can pick the latest
    filed on/before the as-of date).
    """
    chosen: dict[int, list[AnnualPoint]] = {}
    for ns in namespaces:
        for tag in tags:
            node = facts.get("facts", {}).get(ns, {}).get(tag)
            if not node:
                continue
            tag_points: dict[int, list[AnnualPoint]] = {}
            for _unit, entries in node.get("units", {}).items():
                for e in entries:
                    if e.get("form") == "10-K" and e.get("fp") == "FY" and e.get("fy") and e.get("filed"):
                        fy = int(e["fy"])
                        tag_points.setdefault(fy, []).append(
                            AnnualPoint(fy, e["end"], e["filed"], float(e["val"]))
                        )
            for fy, pts in tag_points.items():
                if fy not in chosen:  # a higher-priority tag already covers this year
                    chosen[fy] = pts
    out: list[AnnualPoint] = []
    for fy in sorted(chosen):
        out.extend(chosen[fy])
    return out


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
