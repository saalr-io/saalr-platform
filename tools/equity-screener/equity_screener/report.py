def format_report(metrics: dict, benchmark: dict, coverage: dict, *, target: float = 1.5) -> str:
    verdict = "ABOVE" if metrics["sharpe"] > target else "BELOW"
    return "\n".join([
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
        "-" * 60,
        "CAVEATS: current-S&P-500 universe => SURVIVORSHIP BIAS (Sharpe likely",
        "  optimistic). Point-in-time applies to fundamentals (filing dates), not",
        "  index membership. EDGAR tag gaps drop names. No transaction costs unless",
        "  --cost-bps given. A Sharpe > 1.5 here should be treated with scrutiny.",
        "=" * 60,
    ])
