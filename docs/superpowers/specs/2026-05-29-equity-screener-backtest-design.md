# Equity Screener Backtest (US adaptation) — Design

**Date:** 2026-05-29
**Status:** Approved design — ready for implementation planning
**Standalone:** This is a separate equity-validation capability, intentionally **isolated from the Saalr options platform** (its own package under `tools/`, own deps, not in the uv workspace).

---

## 1. Goal

Honestly answer: **does this quality / low-dilution screen, applied to the S&P 500, yield a portfolio with Sharpe > 1.5?** The deliverable is a **defensible, caveated backtest that reports the actual Sharpe** (and CAGR/vol/drawdown) — whatever it is. We are testing the hypothesis, not engineering a number above 1.5 (validation-first; honest reporting).

Original (Screener.in, India) criteria, re-targeted to US equities:
- shares outstanding now ≤ shares outstanding 10y ago × 1.1 (low dilution)
- 10-year sales (revenue) CAGR > 10%
- 10-year average ROCE > 10%
- market cap > $1B (US adaptation of "> ₹100cr"; configurable; largely non-binding within the S&P 500)

---

## 2. Where it lives

`tools/equity-screener/` — a standalone Python package with its own `pyproject.toml` (deps: `requests`, `pandas`, `numpy`, `yfinance`, dev: `pytest`). **Not** a uv-workspace member, so it shares nothing with the options app. Run via `uv run` inside that directory; CLI entry `python -m equity_screener`.

### Module layout
```
tools/equity-screener/
├── pyproject.toml
├── equity_screener/
│   ├── __init__.py
│   ├── universe.py      # S&P 500 tickers + SEC ticker→CIK map
│   ├── edgar.py         # fetch companyfacts; extract annual series (with filing dates)
│   ├── fundamentals.py  # derive revenue CAGR, avg ROCE, share-count check; as-of selection
│   ├── screen.py        # apply the 4 criteria as-of a date → pass/fail
│   ├── prices.py        # yfinance adjusted-close fetch (+ disk cache)
│   ├── backtest.py      # annual rebalance, equal-weight, returns, Sharpe/CAGR/DD/turnover
│   ├── report.py        # format results + caveats
│   └── cli.py           # run end-to-end, print report
└── tests/               # unit + integration + fixtures/ (saved companyfacts JSON)
```

---

## 3. Data (all free)

- **SEC EDGAR `companyfacts`** — `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json` (requires a `User-Agent` header; throttle to ≤10 req/s). Ticker→CIK from `https://www.sec.gov/files/company_tickers.json`. Each fact carries `end` (period end), `filed` (filing date), `form`, `fy`, `fp`, `units` — we use annual (`form=10-K`, `fp=FY`) values and key by fiscal-year end, retaining `filed` for **point-in-time** screening.
  - **XBRL tags (with fallbacks):** revenue = `Revenues` → `RevenueFromContractWithCustomerExcludingAssessedTax` → `RevenueFromContractWithCustomerIncludingAssessedTax` → `SalesRevenueNet`; shares = `dei:EntityCommonStockSharesOutstanding` → `CommonStockSharesOutstanding`; EBIT = `OperatingIncomeLoss`; assets = `Assets`; current liabilities = `LiabilitiesCurrent`.
- **yfinance** — historical adjusted-close for passers + `SPY` benchmark; cached to disk to avoid refetching.
- **Universe** — current S&P 500 constituents (from a maintained list / Wikipedia), mapped to CIK.

---

## 4. Screen — evaluated as-of each rebalance date T (point-in-time)

Using only fundamentals **filed on or before T**:
- **Dilution:** `shares_out(latest FY ≤ T) ≤ shares_out(~10 FYs earlier) × 1.1`
- **Sales growth:** `revenue CAGR over the ~10y window > 0.10`, `CAGR = (rev_latest / rev_10y_ago) ** (1/years) − 1`
- **ROCE:** `mean(annual ROCE over last ~10 FYs) > 0.10`, `ROCE = OperatingIncomeLoss / (Assets − LiabilitiesCurrent)`
- **Size:** `shares_out × price(T) > $1B`

A company missing required tags/years is **excluded** (and counted in a coverage report), not guessed.

---

## 5. Backtest method

- **Window:** ~2015→2025 (configurable `--start`/`--end`).
- **Rebalance:** annually (first trading day of each year). At T: screen the universe point-in-time → passers → **equal-weight**, hold to next rebalance, reinvest.
- **Returns:** daily portfolio value path from adjusted close; concatenate yearly segments → daily return series.
- **Metrics:** **annualized Sharpe** = `mean(daily_excess) / std(daily) × √252` (rf configurable, default 0; `--rf` annual → daily), plus CAGR, annualized vol, max drawdown, avg #holdings/yr, annual turnover, optional `--cost-bps` per side.
- **Benchmark:** `SPY` over the same window (its Sharpe/CAGR), reported alongside.

---

## 6. Honest reporting (non-negotiable)

`report.py` prints the Sharpe **with its assumptions** (rf, equal-weight, annual rebalance, costs) and **explicit caveats**:
- **Survivorship bias** — current S&P 500 membership ⇒ only today's survivors; this likely **inflates** the Sharpe. (Point-in-time *membership* is out of scope.)
- Point-in-time applies to *fundamentals* (via `filed`), not index membership.
- **EDGAR coverage gaps / restatements** — report how many names were screened vs dropped.
- Strategy Sharpe is reported **relative to SPY**, not just in absolute terms. A result > 1.5 is explicitly flagged for survivorship scrutiny.

---

## 7. Testing

- **`fundamentals.py` (unit):** synthetic annual series → CAGR, avg ROCE, share-check return known values; the as-of selector picks the right years given `filed` dates.
- **`backtest.py` (unit):** a known daily-return series → Sharpe matches a hand-computed value within tolerance; max-drawdown on a known path.
- **`edgar.py` (unit):** parse a **saved `companyfacts` fixture JSON** (trimmed real company) → expected annual revenue/shares/EBIT/assets/current-liabilities (no network).
- **Integration:** a tiny 2–3 synthetic-stock universe (injected prices + fundamentals) → deterministic end-to-end Sharpe.
- **Network-gated:** one optional test hitting EDGAR for a single CIK (skipped unless `RUN_NETWORK_TESTS=1`).

---

## 8. Success criteria

`uv run python -m equity_screener --start 2015 --end 2025` runs end-to-end: pulls EDGAR + prices, screens the S&P 500 point-in-time, backtests, and **prints the Sharpe** (+ CAGR/vol/maxDD), the SPY comparison, coverage stats, and the caveats. Unit + integration tests green. **The Sharpe value is the finding** — success is a credible, caveated answer, not a number above 1.5.

---

## 9. Out of scope

India data; point-in-time index membership (survivorship caveat remains); factor attribution; sector caps; realistic borrow/tax; any "validated edge" marketing claim; integration with the options platform.

## 10. Realism notes

EDGAR XBRL is heterogeneous (revenue/EBIT tags differ by company and era) — tag fallbacks reduce but won't eliminate drops; expect a meaningful fraction of names excluded and report it. yfinance and SEC both rate-limit — fetches are throttled and cached. First full run may take a few minutes for ~500 names.
