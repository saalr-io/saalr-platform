import requests

from .edgar import SEC_HEADERS

_SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
_CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"


def parse_ticker_cik_map(raw: dict) -> dict[str, str]:
    return {row["ticker"].upper(): f"{int(row['cik_str']):010d}" for row in raw.values()}


def ticker_to_cik(session: requests.Session | None = None) -> dict[str, str]:
    s = session or requests.Session()
    resp = s.get(_CIK_MAP_URL, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    return parse_ticker_cik_map(resp.json())


def sp500_tickers(session: requests.Session | None = None) -> list[str]:
    s = session or requests.Session()
    resp = s.get(_SP500_URL, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    lines = resp.text.strip().splitlines()[1:]  # skip header
    return [ln.split(",")[0].strip().upper() for ln in lines if ln]
