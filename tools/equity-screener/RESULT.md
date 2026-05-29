# Equity Screener Backtest — Result

**Date:** 2026-05-29
**Question:** Does the quality / low-dilution screen (shares ≤ 10y-ago ×1.1, 10y sales CAGR > 10%, 10y avg ROCE > 10%, market cap > $1B), applied to the S&P 500 and rebalanced annually equal-weight, yield a Sharpe > 1.5?

## Answer: No.

Over the testable window the screened portfolio delivered **Sharpe ≈ 0.67**, **below the 1.5 target** and **below a plain SPY hold (0.80)**. There is no evidence this screen produces a Sharpe > 1.5; on the data we can test point-in-time with free sources, it underperformed the index.

```
============================================================
Equity Screener Backtest - RESULT
============================================================
Strategy Sharpe : 0.67   (target 1.5: BELOW)
Strategy CAGR   : 11.9%
Strategy vol    : 19.7%
Strategy maxDD  : -31.5%
SPY Sharpe      : 0.80   CAGR 13.5%
------------------------------------------------------------
Universe screened: 501 | dropped (no data): 2
Avg holdings/yr  : 11
Holdings/yr      : 2015:0, 2016:0, 2017:0, 2018:0, 2019:0, 2020:1, 2021:10, 2022:24, 2023:36, 2024:35
Effective invested window: 2020-2024 (earlier years hold cash -> few/no names clear the 10y history rule)
============================================================
```

Run: `cd tools/equity-screener && uv run python -m equity_screener --start 2015 --end 2025`

## How to read this (the caveats are load-bearing)

1. **The test is effectively 2020–2024, not 2015–2025.** The screen requires 11 fiscal years of filed fundamentals (a 10-year lookback). SEC XBRL `companyfacts` only begins ~2009, so for rebalances before ~2020 almost no name has enough *filed* point-in-time history — those years hold **cash** (0 holdings 2015–2019). The reported Sharpe therefore reflects a short, recent window (which includes the 2022 drawdown and the 2023–24 mega-cap rally) over a small, growing book (1 → 35 names). Treat vol/Sharpe as noisy.

2. **Survivorship bias should INFLATE this number, and it still underperforms.** The universe is the *current* S&P 500, i.e. today's survivors. Point-in-time is applied to *fundamentals* (filing dates), not index *membership*. A clean, look-ahead-free result would more likely be lower, not higher — so 0.67 is, if anything, optimistic.

3. **Data-quality fixes were required to get a credible number** (not to hit a target):
   - **Revenue tag merging:** companies switch XBRL revenue tags across eras (old `Revenues`/`SalesRevenueNet` → post-2018 ASC-606 `RevenueFromContractWithCustomer…`). Reading one tag gave most names a 1-year series and dropped them; we merge tags per fiscal year.
   - **Split adjustment:** SEC `EntityCommonStockSharesOutstanding` is split-*unadjusted*, so splitters (AAPL 7:1+4:1, NVDA, AMZN 20:1, GOOGL 20:1, TSLA…) falsely tripped the "dilution" test. Counts are normalized via yfinance split events before the dilution check — splits are not dilution.
   - Even after these fixes some names are dropped for missing/short series (e.g. GOOGL never reaches 11 revenue FYs in companyfacts). 2 names dropped outright; many more silently fail the 11-FY history gate in early years.

4. **No transaction costs, no slippage, equal-weight, annual rebalance, rf = 0.**

## Bottom line

The hypothesis (Sharpe > 1.5) is **not supported**. On a free, point-in-time, survivorship-biased-toward-optimism setup, the screen returned ~0.67 Sharpe / 11.9% CAGR and trailed SPY (0.80 / 13.5%). A more rigorous test would need (a) a point-in-time *membership* universe to remove survivorship bias, and (b) a fundamentals source with deeper history than XBRL's ~2009 start so the 10-year screen can actually run across 2015–2019. Neither would plausibly push this toward 1.5.
