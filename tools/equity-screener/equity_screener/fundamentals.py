from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AnnualPoint:
    fiscal_year: int
    period_end: str  # ISO date
    filed: str       # ISO filing date
    value: float


@dataclass(frozen=True)
class CompanyFundamentals:
    cik: str
    ticker: str
    revenue: list[AnnualPoint]
    shares: list[AnnualPoint]
    ebit: list[AnnualPoint]
    assets: list[AnnualPoint]
    current_liabilities: list[AnnualPoint]


def points_as_of(points: list[AnnualPoint], as_of: date) -> list[AnnualPoint]:
    """Points filed on/before as_of, one per fiscal year (latest filed wins), sorted by FY asc."""
    by_year: dict[int, AnnualPoint] = {}
    for p in points:
        if date.fromisoformat(p.filed) > as_of:
            continue
        cur = by_year.get(p.fiscal_year)
        if cur is None or p.filed > cur.filed:
            by_year[p.fiscal_year] = p
    return [by_year[y] for y in sorted(by_year)]


def cagr(begin: float, end: float, years: int) -> float | None:
    if begin <= 0 or end <= 0 or years <= 0:
        return None
    return (end / begin) ** (1 / years) - 1


def roce(ebit: float, assets: float, current_liabilities: float) -> float | None:
    capital_employed = assets - current_liabilities
    if capital_employed <= 0:
        return None
    return ebit / capital_employed
