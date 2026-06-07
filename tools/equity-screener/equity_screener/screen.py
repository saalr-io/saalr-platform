from dataclasses import dataclass
from datetime import date

from .fundamentals import CompanyFundamentals, cagr, points_as_of, roce


@dataclass(frozen=True)
class ScreenResult:
    passed: bool
    reasons: dict[str, bool]
    metrics: dict[str, float]


def evaluate(
    f: CompanyFundamentals,
    price_at_t: float,
    as_of: date,
    *,
    lookback_years: int = 10,
    market_cap_min: float = 1e9,
) -> ScreenResult | None:
    rev = points_as_of(f.revenue, as_of)
    sh = points_as_of(f.shares, as_of)
    ebit = {p.fiscal_year: p.value for p in points_as_of(f.ebit, as_of)}
    assets = {p.fiscal_year: p.value for p in points_as_of(f.assets, as_of)}
    curliab = {p.fiscal_year: p.value for p in points_as_of(f.current_liabilities, as_of)}

    # need at least lookback_years+1 fiscal years of revenue and shares
    if len(rev) < lookback_years + 1 or len(sh) < lookback_years + 1:
        return None

    rev_latest, rev_old = rev[-1], rev[-1 - lookback_years]
    sh_latest, sh_old = sh[-1], sh[-1 - lookback_years]
    span = rev_latest.fiscal_year - rev_old.fiscal_year

    sales_cagr = cagr(rev_old.value, rev_latest.value, span)

    # average ROCE over the last `lookback_years` fiscal years that have all inputs
    roce_vals: list[float] = []
    for p in rev[-lookback_years:]:
        y = p.fiscal_year
        if y in ebit and y in assets and y in curliab:
            r = roce(ebit[y], assets[y], curliab[y])
            if r is not None:
                roce_vals.append(r)
    avg_roce = sum(roce_vals) / len(roce_vals) if roce_vals else None

    market_cap = sh_latest.value * price_at_t
    share_ratio = sh_latest.value / sh_old.value if sh_old.value else float("inf")

    if sales_cagr is None or avg_roce is None:
        return None

    reasons = {
        "dilution": share_ratio <= 1.1,
        "sales_growth": sales_cagr > 0.10,
        "roce": avg_roce > 0.10,
        "market_cap": market_cap > market_cap_min,
    }
    return ScreenResult(
        passed=all(reasons.values()),
        reasons=reasons,
        metrics={
            "sales_cagr": sales_cagr,
            "avg_roce": avg_roce,
            "share_ratio": share_ratio,
            "market_cap": market_cap,
        },
    )
