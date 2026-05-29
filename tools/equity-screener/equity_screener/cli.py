import argparse
from datetime import date

import pandas as pd
import requests

from .backtest import cagr_from_value, daily_returns, equal_weight_value, max_drawdown, sharpe
from .edgar import extract_fundamentals, fetch_company_facts
from .prices import get_prices
from .report import format_report
from .screen import evaluate
from .universe import sp500_tickers, ticker_to_cik


def run(start_year: int, end_year: int, rf: float, limit: int | None) -> str:
    session = requests.Session()
    tickers = sp500_tickers(session)
    if limit:
        tickers = tickers[:limit]
    cik_map = ticker_to_cik(session)

    funds: dict[str, object] = {}
    dropped = 0
    for t in tickers:
        cik = cik_map.get(t)
        if not cik:
            dropped += 1
            continue
        try:
            funds[t] = extract_fundamentals(fetch_company_facts(cik, session=session), cik, t)
        except Exception:
            dropped += 1

    start, end = f"{start_year}-01-01", f"{end_year}-12-31"
    prices = get_prices([*funds.keys(), "SPY"], start, end)

    holdings: dict = {}
    holding_counts: list[int] = []
    for year in range(start_year, end_year):
        rebal = pd.Timestamp(f"{year}-01-01")
        day = prices.index[prices.index >= rebal]
        if len(day) == 0:
            continue
        d = day[0]
        as_of = date(year, 1, 1)
        passers = []
        for t, f in funds.items():
            if t not in prices.columns:
                continue
            px = prices.loc[d, t]
            if pd.isna(px):
                continue
            r = evaluate(f, float(px), as_of)
            if r and r.passed:
                passers.append(t)
        holdings[d] = passers
        holding_counts.append(len(passers))

    value = equal_weight_value(prices.drop(columns=["SPY"], errors="ignore"), holdings)
    rets = daily_returns(value)
    spy = prices["SPY"].dropna()
    spy_rets = spy.pct_change().dropna()

    metrics = {
        "sharpe": sharpe(rets, rf), "cagr": cagr_from_value(value),
        "vol": float(rets.std(ddof=0) * (252 ** 0.5)), "max_dd": max_drawdown(value),
        "avg_holdings": sum(holding_counts) / len(holding_counts) if holding_counts else 0,
    }
    benchmark = {"sharpe": sharpe(spy_rets, rf), "cagr": cagr_from_value(spy)}
    coverage = {"screened": len(funds), "dropped": dropped}
    return format_report(metrics, benchmark, coverage)


def main() -> None:
    p = argparse.ArgumentParser(description="Equity screener backtest")
    p.add_argument("--start", type=int, default=2015)
    p.add_argument("--end", type=int, default=2025)
    p.add_argument("--rf", type=float, default=0.0)
    p.add_argument("--limit", type=int, default=None, help="cap universe size (smoke runs)")
    args = p.parse_args()
    print(run(args.start, args.end, args.rf, args.limit))


if __name__ == "__main__":
    main()
