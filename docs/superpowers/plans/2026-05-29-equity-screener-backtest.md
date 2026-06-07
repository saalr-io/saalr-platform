# Equity Screener Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone CLI that screens the S&P 500 on a low-dilution / sales-CAGR / ROCE / market-cap rule (point-in-time via SEC EDGAR), backtests an annual equal-weight portfolio, and reports its Sharpe (+CAGR/vol/drawdown) vs SPY with survivorship + coverage caveats.

**Architecture:** Pure deterministic core (fundamentals math, screen, backtest metrics, portfolio) is fully TDD'd with synthetic data. EDGAR parsing is fixture-tested (no network in unit tests). `universe`/`prices` wrap SEC + yfinance with disk caching. A CLI wires it end-to-end; the live run is the final step and produces the actual finding.

**Tech Stack:** Python 3.12, `requests`, `pandas`, `numpy`, `yfinance`, `pytest`. Standalone under `tools/equity-screener/` — **not** part of the options uv workspace.

**Spec:** `docs/superpowers/specs/2026-05-29-equity-screener-backtest-design.md`

**All commands run from:** `tools/equity-screener/` (its own uv project) unless noted. Tests: `uv run pytest`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `tools/equity-screener/pyproject.toml` | standalone project + deps |
| `equity_screener/__init__.py` | package marker |
| `equity_screener/fundamentals.py` | `AnnualPoint`, `CompanyFundamentals`, `points_as_of`, `cagr`, `roce` |
| `equity_screener/screen.py` | `ScreenResult`, `evaluate(...)` (4 criteria, point-in-time) |
| `equity_screener/backtest.py` | `sharpe`, `cagr_from_value`, `max_drawdown`, `equal_weight_returns` |
| `equity_screener/edgar.py` | `fetch_company_facts`, `extract_fundamentals` (XBRL → annual series) |
| `equity_screener/universe.py` | `sp500_tickers`, `ticker_to_cik` |
| `equity_screener/prices.py` | `get_prices` (yfinance + disk cache) |
| `equity_screener/report.py` | `format_report(metrics, coverage, caveats)` |
| `equity_screener/cli.py` | `main()` — end-to-end run |
| `tests/…` + `tests/fixtures/companyfacts_sample.json` | unit + integration |

---

## Task 1: Scaffold the standalone project

**Files:** Create `tools/equity-screener/pyproject.toml`, `equity_screener/__init__.py`, `tests/__init__.py`.

- [ ] **Step 1: `pyproject.toml`**

```toml
[project]
name = "saalr-equity-screener"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "requests>=2.31",
  "pandas>=2.2",
  "numpy>=1.26",
  "yfinance>=0.2.40",
]

[dependency-groups]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["equity_screener"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: package markers**

`equity_screener/__init__.py`: empty file.
`tests/__init__.py`: empty file.

- [ ] **Step 3: install + smoke**

Run: `cd "c:/Users/sreek/myprojects/saalr-demo/SAALR F2F/tools/equity-screener" && uv sync && uv run python -c "import equity_screener; print('ok')"`
Expected: `uv sync` resolves; prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add tools/equity-screener/pyproject.toml tools/equity-screener/equity_screener/__init__.py tools/equity-screener/tests/__init__.py tools/equity-screener/uv.lock
git commit -m "feat(equity): scaffold standalone equity-screener project"
```

---

## Task 2: Fundamentals math (pure, TDD)

**Files:** Create `equity_screener/fundamentals.py`; Test `tests/test_fundamentals.py`.

- [ ] **Step 1: Write the failing test**

`tests/test_fundamentals.py`:
```python
from datetime import date

from equity_screener.fundamentals import AnnualPoint, cagr, points_as_of, roce


def test_cagr_basic():
    assert cagr(100.0, 200.0, 10) == (2.0) ** (1 / 10) - 1
    assert cagr(0.0, 200.0, 10) is None
    assert cagr(100.0, 200.0, 0) is None


def test_roce():
    assert roce(20.0, 200.0, 100.0) == 20.0 / 100.0
    assert roce(20.0, 100.0, 100.0) is None  # capital employed <= 0


def test_points_as_of_filters_and_dedups():
    pts = [
        AnnualPoint(2013, "2013-12-31", "2014-02-01", 10.0),
        AnnualPoint(2014, "2014-12-31", "2015-02-01", 20.0),
        AnnualPoint(2014, "2014-12-31", "2015-05-01", 21.0),  # restatement, later filing
        AnnualPoint(2015, "2015-12-31", "2016-02-01", 30.0),
    ]
    out = points_as_of(pts, date(2016, 1, 1))
    # 2015 filed 2016-02 is after as_of -> excluded; 2014 dedups to the latest filed on/before
    assert [(p.fiscal_year, p.value) for p in out] == [(2013, 10.0), (2014, 21.0)]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_fundamentals.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `fundamentals.py`**

```python
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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_fundamentals.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/equity-screener/equity_screener/fundamentals.py tools/equity-screener/tests/test_fundamentals.py
git commit -m "feat(equity): point-in-time fundamentals math (cagr, roce, as-of)"
```

---

## Task 3: The screen (pure, TDD)

**Files:** Create `equity_screener/screen.py`; Test `tests/test_screen.py`.

- [ ] **Step 1: Write the failing test**

`tests/test_screen.py`:
```python
from datetime import date

from equity_screener.fundamentals import AnnualPoint, CompanyFundamentals
from equity_screener.screen import evaluate


def _series(values: dict[int, float]) -> list[AnnualPoint]:
    return [AnnualPoint(y, f"{y}-12-31", f"{y + 1}-02-15", v) for y, v in values.items()]


def _company() -> CompanyFundamentals:
    years = range(2004, 2015)  # 2004..2014 (11 FYs available as of 2015 rebalance)
    return CompanyFundamentals(
        cik="0000000001",
        ticker="GOOD",
        revenue=_series({y: 100.0 * (1.15 ** (y - 2004)) for y in years}),  # ~15% CAGR
        shares=_series({y: 1000.0 for y in years}),                          # flat shares
        ebit=_series({y: 30.0 for y in years}),
        assets=_series({y: 200.0 for y in years}),
        current_liabilities=_series({y: 50.0 for y in years}),               # ROCE = 30/150 = 20%
    )


def test_quality_company_passes():
    r = evaluate(_company(), price_at_t=50.0, as_of=date(2015, 6, 1))
    assert r is not None and r.passed
    assert r.reasons["dilution"] and r.reasons["sales_growth"]
    assert r.reasons["roce"] and r.reasons["market_cap"]


def test_dilution_fails_when_shares_grew():
    c = _company()
    diluted = CompanyFundamentals(
        c.cik, c.ticker, c.revenue,
        _series({y: 1000.0 if y == 2004 else 2000.0 for y in range(2004, 2015)}),
        c.ebit, c.assets, c.current_liabilities,
    )
    r = evaluate(diluted, price_at_t=50.0, as_of=date(2015, 6, 1))
    assert r is not None and not r.passed and not r.reasons["dilution"]


def test_insufficient_history_returns_none():
    short = CompanyFundamentals("0000000002", "NEW",
        _series({2013: 100.0, 2014: 130.0}), _series({2013: 10.0, 2014: 10.0}),
        _series({2013: 5.0, 2014: 5.0}), _series({2013: 50.0, 2014: 50.0}),
        _series({2013: 10.0, 2014: 10.0}))
    assert evaluate(short, price_at_t=50.0, as_of=date(2015, 6, 1)) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_screen.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `screen.py`**

```python
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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_screen.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/equity-screener/equity_screener/screen.py tools/equity-screener/tests/test_screen.py
git commit -m "feat(equity): point-in-time screen (dilution/sales/roce/market-cap)"
```

---

## Task 4: Backtest metrics (pure, TDD)

**Files:** Create `equity_screener/backtest.py`; Test `tests/test_backtest_metrics.py`.

- [ ] **Step 1: Write the failing test**

`tests/test_backtest_metrics.py`:
```python
import numpy as np
import pandas as pd

from equity_screener.backtest import cagr_from_value, max_drawdown, sharpe


def test_sharpe_known_series():
    # daily returns alternating +/- around a positive mean
    r = pd.Series([0.001, -0.0005] * 500)
    expected = (r.mean() / r.std(ddof=0)) * (252 ** 0.5)
    assert abs(sharpe(r) - expected) < 1e-9


def test_sharpe_zero_vol_is_zero():
    assert sharpe(pd.Series([0.0, 0.0, 0.0])) == 0.0


def test_max_drawdown():
    value = pd.Series([100, 120, 90, 110])  # peak 120 -> trough 90 = -25%
    assert abs(max_drawdown(value) - (-0.25)) < 1e-9


def test_cagr_from_value():
    value = pd.Series([100.0, 200.0], index=pd.to_datetime(["2015-01-01", "2025-01-01"]))
    assert abs(cagr_from_value(value) - ((2.0) ** (1 / 10) - 1)) < 1e-6
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_backtest_metrics.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the metrics in `backtest.py`**

```python
import pandas as pd


def sharpe(daily_returns: pd.Series, rf_annual: float = 0.0, periods: int = 252) -> float:
    if len(daily_returns) == 0:
        return 0.0
    excess = daily_returns - rf_annual / periods
    sd = excess.std(ddof=0)
    if sd == 0 or pd.isna(sd):
        return 0.0
    return float(excess.mean() / sd * (periods ** 0.5))


def max_drawdown(value: pd.Series) -> float:
    if len(value) == 0:
        return 0.0
    running_max = value.cummax()
    drawdown = value / running_max - 1.0
    return float(drawdown.min())


def cagr_from_value(value: pd.Series) -> float:
    if len(value) < 2 or value.iloc[0] <= 0:
        return 0.0
    years = (value.index[-1] - value.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return float((value.iloc[-1] / value.iloc[0]) ** (1 / years) - 1)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_backtest_metrics.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/equity-screener/equity_screener/backtest.py tools/equity-screener/tests/test_backtest_metrics.py
git commit -m "feat(equity): backtest metrics (sharpe, max drawdown, cagr)"
```

---

## Task 5: Equal-weight rebalanced portfolio (TDD with synthetic prices)

**Files:** Modify `equity_screener/backtest.py`; Test `tests/test_portfolio.py`.

- [ ] **Step 1: Write the failing test**

`tests/test_portfolio.py`:
```python
import numpy as np
import pandas as pd

from equity_screener.backtest import equal_weight_value


def test_equal_weight_value_two_stocks():
    idx = pd.bdate_range("2015-01-01", periods=10)
    prices = pd.DataFrame(
        {"A": np.linspace(10, 11, 10), "B": np.linspace(20, 22, 10)}, index=idx
    )
    # one rebalance at the start holding both equally
    holdings = {idx[0]: ["A", "B"]}
    value = equal_weight_value(prices, holdings, start_cash=1000.0)
    assert abs(value.iloc[0] - 1000.0) < 1e-6
    # A +10%, B +10% over window -> ~ +10%
    assert abs(value.iloc[-1] / value.iloc[0] - 1.10) < 1e-6


def test_empty_holdings_holds_cash():
    idx = pd.bdate_range("2015-01-01", periods=5)
    prices = pd.DataFrame({"A": np.linspace(10, 12, 5)}, index=idx)
    value = equal_weight_value(prices, {idx[0]: []}, start_cash=1000.0)
    assert (value == 1000.0).all()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_portfolio.py -q`
Expected: FAIL — `equal_weight_value` not defined.

- [ ] **Step 3: Implement `equal_weight_value` + `daily_returns` in `backtest.py`**

Append to `equity_screener/backtest.py`:
```python
def equal_weight_value(
    prices: pd.DataFrame,
    holdings: dict,
    start_cash: float = 1000.0,
) -> pd.Series:
    """Walk the trading calendar; at each rebalance date in `holdings` (date -> [tickers]),
    re-allocate the current portfolio value equally across those tickers (cash if empty)."""
    dates = prices.index
    rebal_dates = sorted(holdings)
    value = pd.Series(index=dates, dtype=float)
    cash = start_cash
    units: dict[str, float] = {}

    def portfolio_value(row) -> float:
        held = sum(u * row[t] for t, u in units.items() if t in row and not pd.isna(row[t]))
        return cash + held

    next_rebal = 0
    for d in dates:
        if next_rebal < len(rebal_dates) and d >= rebal_dates[next_rebal]:
            row = prices.loc[d]
            current = portfolio_value(row)
            tickers = [t for t in holdings[rebal_dates[next_rebal]] if t in row and not pd.isna(row[t])]
            units = {}
            cash = current
            if tickers:
                each = current / len(tickers)
                for t in tickers:
                    units[t] = each / row[t]
                cash = 0.0
            next_rebal += 1
        value.loc[d] = portfolio_value(prices.loc[d])
    return value


def daily_returns(value: pd.Series) -> pd.Series:
    return value.pct_change().dropna()
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_portfolio.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/equity-screener/equity_screener/backtest.py tools/equity-screener/tests/test_portfolio.py
git commit -m "feat(equity): equal-weight rebalanced portfolio value path"
```

---

## Task 6: EDGAR extraction (fixture-tested)

**Files:** Create `equity_screener/edgar.py`, `tests/fixtures/companyfacts_sample.json`; Test `tests/test_edgar.py`.

- [ ] **Step 1: Create a trimmed fixture**

`tests/fixtures/companyfacts_sample.json` — a minimal companyfacts shape with two FYs of the tags we read:
```json
{
  "cik": 1,
  "entityName": "Sample Co",
  "facts": {
    "us-gaap": {
      "Revenues": {"units": {"USD": [
        {"fy": 2014, "fp": "FY", "form": "10-K", "end": "2014-12-31", "filed": "2015-02-15", "val": 1000},
        {"fy": 2013, "fp": "FY", "form": "10-K", "end": "2013-12-31", "filed": "2014-02-15", "val": 800},
        {"fy": 2014, "fp": "Q1", "form": "10-Q", "end": "2014-03-31", "filed": "2014-05-01", "val": 250}
      ]}},
      "OperatingIncomeLoss": {"units": {"USD": [
        {"fy": 2014, "fp": "FY", "form": "10-K", "end": "2014-12-31", "filed": "2015-02-15", "val": 300}
      ]}},
      "Assets": {"units": {"USD": [
        {"fy": 2014, "fp": "FY", "form": "10-K", "end": "2014-12-31", "filed": "2015-02-15", "val": 2000}
      ]}},
      "LiabilitiesCurrent": {"units": {"USD": [
        {"fy": 2014, "fp": "FY", "form": "10-K", "end": "2014-12-31", "filed": "2015-02-15", "val": 500}
      ]}}
    },
    "dei": {
      "EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"fy": 2014, "fp": "FY", "form": "10-K", "end": "2014-12-31", "filed": "2015-02-15", "val": 100}
      ]}}
    }
  }
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_edgar.py`:
```python
import json
from pathlib import Path

from equity_screener.edgar import extract_fundamentals

FIXTURE = Path(__file__).parent / "fixtures" / "companyfacts_sample.json"


def test_extract_annual_only_and_dedup():
    facts = json.loads(FIXTURE.read_text())
    f = extract_fundamentals(facts, cik="0000000001", ticker="SMP")
    rev_years = {p.fiscal_year: p.value for p in f.revenue}
    assert rev_years == {2013: 800.0, 2014: 1000.0}  # Q1 10-Q excluded
    assert f.ebit[0].value == 300.0
    assert f.assets[0].value == 2000.0
    assert f.current_liabilities[0].value == 500.0
    assert f.shares[0].value == 100.0
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/test_edgar.py -q`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement `edgar.py`**

```python
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
    """First tag (across given namespaces) that yields annual (10-K, FY) points."""
    for ns in namespaces:
        for tag in tags:
            node = facts.get("facts", {}).get(ns, {}).get(tag)
            if not node:
                continue
            points: list[AnnualPoint] = []
            for _unit, entries in node.get("units", {}).items():
                for e in entries:
                    if e.get("form") == "10-K" and e.get("fp") == "FY" and e.get("fy") and e.get("filed"):
                        points.append(
                            AnnualPoint(int(e["fy"]), e["end"], e["filed"], float(e["val"]))
                        )
            if points:
                return points
    return []


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
```

> Note: `extract_fundamentals` may return empty lists per metric when tags are missing — that's the coverage gap the screen treats as "exclude" (`evaluate` returns `None`).

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/test_edgar.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/equity-screener/equity_screener/edgar.py tools/equity-screener/tests/test_edgar.py tools/equity-screener/tests/fixtures/companyfacts_sample.json
git commit -m "feat(equity): EDGAR companyfacts annual extraction (fixture-tested)"
```

---

## Task 7: Universe + prices (SEC map + yfinance, cached)

**Files:** Create `equity_screener/universe.py`, `equity_screener/prices.py`; Test `tests/test_universe.py`.

- [ ] **Step 1: Write the failing test (CIK-map parsing, no network)**

`tests/test_universe.py`:
```python
from equity_screener.universe import parse_ticker_cik_map


def test_parse_ticker_cik_map():
    raw = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft"},
    }
    m = parse_ticker_cik_map(raw)
    assert m["AAPL"] == "0000320193"
    assert m["MSFT"] == "0000789019"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_universe.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `universe.py`**

```python
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
```

- [ ] **Step 4: Implement `prices.py` (yfinance + disk cache)**

`equity_screener/prices.py`:
```python
from pathlib import Path

import pandas as pd
import yfinance as yf

_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "prices"


def get_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Adjusted-close prices for tickers in [start, end]; cached per (tickers,start,end)."""
    _CACHE.mkdir(parents=True, exist_ok=True)
    key = f"{'_'.join(sorted(tickers))[:60]}_{start}_{end}.parquet"
    path = _CACHE / key
    if path.exists():
        return pd.read_parquet(path)
    data = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    close = data["Close"] if "Close" in data else data
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close = close.dropna(how="all")
    close.to_parquet(path)
    return close
```

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/test_universe.py -q`
Expected: PASS. (Add `pyarrow` to deps if parquet errors: `uv add pyarrow`.)

- [ ] **Step 6: Commit**

```bash
git add tools/equity-screener/equity_screener/universe.py tools/equity-screener/equity_screener/prices.py tools/equity-screener/tests/test_universe.py tools/equity-screener/uv.lock
git commit -m "feat(equity): S&P500 universe + CIK map + cached yfinance prices"
```

---

## Task 8: Report + CLI + end-to-end integration test

**Files:** Create `equity_screener/report.py`, `equity_screener/cli.py`, `equity_screener/__main__.py`; Test `tests/test_integration.py`.

- [ ] **Step 1: Write the failing integration test (synthetic, no network)**

`tests/test_integration.py`:
```python
from datetime import date

import numpy as np
import pandas as pd

from equity_screener.backtest import daily_returns, equal_weight_value, sharpe
from equity_screener.fundamentals import AnnualPoint, CompanyFundamentals
from equity_screener.screen import evaluate


def _co(ticker, rev0, growth, shares, ebit, assets, curliab):
    years = range(2004, 2015)
    s = lambda f: [AnnualPoint(y, f"{y}-12-31", f"{y + 1}-02-15", f(y)) for y in years]
    return CompanyFundamentals(
        cik=ticker, ticker=ticker,
        revenue=s(lambda y: rev0 * (growth ** (y - 2004))),
        shares=s(lambda _y: shares), ebit=s(lambda _y: ebit),
        assets=s(lambda _y: assets), current_liabilities=s(lambda _y: curliab),
    )


def test_end_to_end_synthetic():
    universe = {
        "PASS": _co("PASS", 100, 1.15, 1000, 30, 200, 50),   # passes
        "DILUTE": _co("DILUTE", 100, 1.15, 1000, 30, 200, 50),
    }
    universe["DILUTE"] = CompanyFundamentals(
        "DILUTE", "DILUTE", universe["DILUTE"].revenue,
        [AnnualPoint(y, f"{y}-12-31", f"{y+1}-02-15", 1000 if y == 2004 else 3000) for y in range(2004, 2015)],
        universe["DILUTE"].ebit, universe["DILUTE"].assets, universe["DILUTE"].current_liabilities,
    )
    as_of = date(2015, 1, 2)
    passers = [t for t, f in universe.items() if (r := evaluate(f, 50.0, as_of)) and r.passed]
    assert passers == ["PASS"]

    idx = pd.bdate_range("2015-01-02", periods=252)
    prices = pd.DataFrame({"PASS": np.linspace(50, 60, 252), "DILUTE": np.linspace(50, 40, 252)}, index=idx)
    value = equal_weight_value(prices, {idx[0]: passers})
    assert sharpe(daily_returns(value)) > 0  # PASS rose -> positive sharpe
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_integration.py -q`
Expected: PASS already for the assertions above IF Tasks 3–5 done — but it also drives `report.py`/`cli.py` next; if green, proceed (this test pins the wiring contract).

- [ ] **Step 3: Implement `report.py`**

```python
def format_report(metrics: dict, benchmark: dict, coverage: dict, *, target: float = 1.5) -> str:
    verdict = "ABOVE" if metrics["sharpe"] > target else "BELOW"
    return "\n".join([
        "=" * 60,
        "Equity Screener Backtest — RESULT",
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
```

- [ ] **Step 4: Implement `cli.py` + `__main__.py`**

`equity_screener/cli.py`:
```python
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
```

`equity_screener/__main__.py`:
```python
from .cli import main

main()
```

- [ ] **Step 5: Run tests + a smoke**

Run: `uv run pytest -q`
Expected: all tests pass.
Then a tiny live smoke (network): `uv run python -m equity_screener --limit 8 --start 2018 --end 2021`
Expected: prints a RESULT block with a Sharpe (value will vary; just confirm it runs end-to-end on 8 names).

- [ ] **Step 6: Commit**

```bash
git add tools/equity-screener/equity_screener/report.py tools/equity-screener/equity_screener/cli.py tools/equity-screener/equity_screener/__main__.py tools/equity-screener/tests/test_integration.py
git commit -m "feat(equity): report + CLI wiring + end-to-end integration test"
```

---

## Task 9: Run the real backtest (the finding)

- [ ] **Step 1: Full run on the S&P 500**

Run: `cd "c:/Users/sreek/myprojects/saalr-demo/SAALR F2F/tools/equity-screener" && uv run python -m equity_screener --start 2015 --end 2025`
Expected: completes (a few minutes; EDGAR + prices throttled/cached) and prints the RESULT block — **Sharpe, CAGR, vol, maxDD, SPY comparison, coverage, caveats**.

- [ ] **Step 2: Record the finding**

Capture the printed Sharpe and whether it cleared 1.5, **with the caveats**. Report the number honestly (it is the answer to the original question, not a target). If coverage dropped a large fraction of names, say so — it weakens the result.

- [ ] **Step 3 (optional): Save the result**

If useful, write the report block to `tools/equity-screener/RESULT.md` and commit it.

---

## Self-Review

**Spec coverage:**
- §3 data (EDGAR companyfacts + tags, yfinance, S&P500/CIK) → Tasks 6, 7.
- §4 screen (4 criteria, point-in-time via filing dates) → Tasks 2 (`points_as_of`/`cagr`/`roce`) + 3 (`evaluate`).
- §5 backtest (annual equal-weight rebalance, Sharpe/CAGR/vol/maxDD, SPY benchmark, rf/cost flags) → Tasks 4, 5, 8 (`--rf`; `--cost-bps` is noted optional in spec §5 and intentionally deferred from the CLI — see note).
- §6 honest reporting + survivorship/coverage caveats → Task 8 `report.py`.
- §7 testing (fundamentals/backtest unit, EDGAR fixture, synthetic integration, network-gated) → Tasks 2–8 (the live smoke in Task 8 Step 5 is the network exercise).
- §8 success (CLI runs, prints Sharpe + caveats) → Task 9.

**Placeholder scan:** none — every code step is complete. The one intentional spec-vs-plan trim: `--cost-bps` (spec §5 "optional") is **not** wired in the CLI to keep the slice focused; flagging it here rather than leaving a stub. The optional network-gated single-CIK test (spec §7) is realized as the Task 8 Step 5 live smoke instead of a separate test.

**Type/name consistency:** `AnnualPoint`/`CompanyFundamentals` (Task 2) used by `screen.evaluate` (Task 3), `edgar.extract_fundamentals` (Task 6), and the integration test (Task 8). `sharpe`/`max_drawdown`/`cagr_from_value`/`equal_weight_value`/`daily_returns` (Tasks 4–5) used by `cli.run` (Task 8). `ScreenResult.passed/reasons/metrics` consistent across Task 3 and its tests. `evaluate(f, price_at_t, as_of, *, lookback_years, market_cap_min)` signature identical in Tasks 3 and 8.

**Resolved during review:** added the `--limit` flag (Task 8) so the live exercise (Step 5) and debugging can run on a handful of names without a full ~500-name pull; the full run is Task 9.
