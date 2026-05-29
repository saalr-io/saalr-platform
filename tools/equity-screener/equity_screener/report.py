def format_report(
    metrics: dict,
    benchmark: dict,
    coverage: dict,
    *,
    target: float = 1.5,
    holdings_by_year: list[tuple[int, int]] | None = None,
) -> str:
    verdict = "ABOVE" if metrics["sharpe"] > target else "BELOW"
    lines = [
        "=" * 60,
        "Equity Screener Backtest - RESULT",
        "=" * 60,
        f"Strategy Sharpe : {metrics['sharpe']:.2f}   (target {target}: {verdict})",
        f"Strategy CAGR   : {metrics['cagr'] * 100:.1f}%",
        f"Strategy vol    : {metrics['vol'] * 100:.1f}%",
        f"Strategy maxDD  : {metrics['max_dd'] * 100:.1f}%",
        f"SPY Sharpe      : {benchmark['sharpe']:.2f}   CAGR {benchmark['cagr'] * 100:.1f}%",
        "-" * 60,
        f"Universe screened: {coverage['screened']} | dropped (no data): {coverage['dropped']}",
        f"Avg holdings/yr  : {metrics['avg_holdings']:.0f}",
    ]
    if holdings_by_year:
        lines.append("Holdings/yr      : " + ", ".join(f"{y}:{n}" for y, n in holdings_by_year))
        invested = [y for y, n in holdings_by_year if n > 0]
        if invested:
            lines.append(f"Effective invested window: {invested[0]}-{invested[-1]} "
                         f"(earlier years hold cash -> few/no names clear the 10y history rule)")
    lines += [
        "-" * 60,
        "CAVEATS:",
        "  * SURVIVORSHIP BIAS: current-S&P-500 universe => only today's survivors,",
        "    which likely INFLATES the Sharpe. Point-in-time applies to fundamentals",
        "    (filing dates), not index membership.",
        "  * SHORT HISTORY: SEC XBRL companyfacts begins ~2009, but the screen needs",
        "    11 fiscal years. Pre-~2020 rebalances drop most names for insufficient",
        "    filed history and hold CASH, so the test is effectively only the later",
        "    invested years (this both shrinks the sample and distorts vol/Sharpe).",
        "  * EDGAR TAG GAPS: revenue/EBIT tags vary by company/era (merged across",
        "    fallbacks); names still missing a usable series are dropped.",
        "  * SPLITS: SEC share counts are split-unadjusted, so counts are put on a",
        "    common basis via yfinance splits before the dilution test (splits != dilution).",
        "  * No transaction costs. A Sharpe > 1.5 here should be treated with scrutiny.",
        "=" * 60,
    ]
    return "\n".join(lines)
