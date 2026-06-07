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


def split_adjust_shares(
    shares: list[AnnualPoint], splits: list[tuple[date, float]]
) -> list[AnnualPoint]:
    """Express each historical share count on the current (post-all-splits) basis.

    SEC `EntityCommonStockSharesOutstanding` is reported on each filing's raw,
    split-unadjusted basis, so a 4:1 split makes the raw count jump 4x even though
    no shares were truly issued. Comparing raw counts across a split would falsely
    flag "dilution". We multiply each count by the cumulative product of split
    ratios occurring AFTER its period_end, putting every year in today's share
    units; the dilution ratio (latest/old) then reflects only real issuance/buyback.
    """
    ordered = sorted(splits, key=lambda s: s[0])
    out: list[AnnualPoint] = []
    for p in shares:
        period_end = date.fromisoformat(p.period_end)
        factor = 1.0
        for split_date, ratio in ordered:
            if split_date > period_end:
                factor *= ratio
        out.append(AnnualPoint(p.fiscal_year, p.period_end, p.filed, p.value * factor))
    return out


def cagr(begin: float, end: float, years: int) -> float | None:
    if begin <= 0 or end <= 0 or years <= 0:
        return None
    return (end / begin) ** (1 / years) - 1


def roce(ebit: float, assets: float, current_liabilities: float) -> float | None:
    capital_employed = assets - current_liabilities
    if capital_employed <= 0:
        return None
    return ebit / capital_employed
