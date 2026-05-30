# Backtest engine (8a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure, rolling, model-priced backtest engine plus a worker that runs a backtest by id and persists results to the `backtests` table — testable end-to-end via a CLI/direct call (no queue/API yet; that is slice 8b).

**Architecture:** Pure compute lives in a new `saalr_core/backtest/` package (metrics, realized-vol, relative-template, rolling engine) reusing the existing BSM `pricing` engine and `strategies` leg types. A new `apps/backtest-worker/` app (sibling to `ingest-worker`) loads strategy + bars under a tenant RLS session, runs the engine, and persists. Option prices are BSM-modeled with IV from trailing realized volatility; every result is labeled `approximate`.

**Tech Stack:** Python 3.12, stdlib `math` only for compute (no numpy/pandas), SQLAlchemy 2.0 async (asyncpg), uv workspace, pytest (`pytest-asyncio`), ruff.

**Spec:** `docs/superpowers/specs/2026-05-30-backtest-engine-design.md`

**Conventions to follow (from the existing codebase):**
- `from __future__ import annotations` at the top of every module.
- Enums: `OptionType.CALL/PUT`, `Side.BUY/SELL` (`Side.sign` → +1/-1). Pricing uses a *separate* `OptionKind.CALL/PUT` (in `saalr_core.pricing.types`).
- `OptionLeg(option_type, side, strike, expiry, qty, entry_price=None, kind="option")` — `expiry` is a `YYYY-MM-DD` string. `EquityLeg(side, qty, entry_price=None)`. `CashLeg(amount)`. `OPTION_MULTIPLIER = 100`.
- BSM price: `saalr_core.pricing.greeks.price(OptionParams(spot, strike, t_years, rate, sigma, div_yield, kind))`.
- RLS: tenant-scoped tables (`strategies`, `backtests`) require `tenant_session(sessionmaker, tenant_id)` (sets `app.current_tenant`, runs ONE transaction — do not nest `session.begin()`). `bars` is non-RLS (shared).
- asyncpg is strict: bind `Decimal` for NUMERIC, `datetime`/`date` for TIMESTAMPTZ/DATE — never `str`/`float`.
- Tests run against the local Docker DB on host **55432** (native PG shadows 5432/5433). The integration conftest defaults the URLs; the suite is invoked with the 55432 env already set by the runner.

---

## Task 1: Pure metrics (`saalr_core/backtest/metrics.py`)

**Files:**
- Create: `packages/core/saalr_core/backtest/__init__.py` (empty)
- Create: `packages/core/saalr_core/backtest/metrics.py`
- Test: `packages/core/tests/test_backtest_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_backtest_metrics.py
import math

from saalr_core.backtest import metrics as m


def test_total_return():
    assert m.total_return([100.0, 110.0]) == 110.0 / 100.0 - 1.0
    assert m.total_return([100.0]) == 0.0
    assert m.total_return([]) == 0.0


def test_daily_returns():
    assert m.daily_returns([100.0, 110.0, 121.0]) == [0.1, 0.1]
    assert m.daily_returns([100.0]) == []


def test_annualized_return_one_year_flat_growth():
    # 10% over ~365 days -> ~10% annualized
    r = m.annualized_return([100.0, 110.0], 365)
    assert abs(r - 0.10) < 1e-6


def test_max_drawdown_is_negative_trough():
    # peak 120 then trough 90 -> -25%
    assert abs(m.max_drawdown([100.0, 120.0, 90.0, 110.0]) - (-0.25)) < 1e-9
    assert m.max_drawdown([]) == 0.0


def test_sharpe_zero_variance_is_zero():
    assert m.sharpe([0.01, 0.01, 0.01], rf=0.0) == 0.0


def test_sharpe_positive_for_steady_gains():
    assert m.sharpe([0.01, 0.012, 0.009, 0.011], rf=0.0) > 0


def test_sortino_ignores_upside_volatility():
    # all-positive returns -> no downside deviation -> 0.0 by convention
    assert m.sortino([0.01, 0.02, 0.03], rf=0.0) == 0.0
    assert m.sortino([0.02, -0.01, 0.02, -0.01], rf=0.0) > 0


def test_win_rate_and_avg_trade_pnl():
    assert m.win_rate([10.0, -5.0, 3.0, 0.0]) == 0.5  # >0 wins: 10,3 of 4
    assert m.avg_trade_pnl([10.0, -5.0, 3.0, 0.0]) == 2.0
    assert m.win_rate([]) == 0.0
    assert m.avg_trade_pnl([]) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_backtest_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.backtest'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/backtest/metrics.py
from __future__ import annotations

import math

TRADING_DAYS = 252


def total_return(equity: list[float]) -> float:
    if len(equity) < 2 or equity[0] == 0:
        return 0.0
    return equity[-1] / equity[0] - 1.0


def annualized_return(equity: list[float], days: int) -> float:
    if len(equity) < 2 or equity[0] <= 0 or days <= 0:
        return 0.0
    growth = equity[-1] / equity[0]
    if growth <= 0:
        return -1.0
    years = days / 365.0
    return growth ** (1.0 / years) - 1.0


def daily_returns(equity: list[float]) -> list[float]:
    out: list[float] = []
    for prev, cur in zip(equity, equity[1:]):
        out.append(cur / prev - 1.0 if prev != 0 else 0.0)
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def sharpe(returns: list[float], rf: float = 0.0, periods: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    rf_daily = rf / periods
    excess = [r - rf_daily for r in returns]
    sd = _stdev(excess)
    if sd == 0:
        return 0.0
    return _mean(excess) / sd * math.sqrt(periods)


def sortino(returns: list[float], rf: float = 0.0, periods: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    rf_daily = rf / periods
    excess = [r - rf_daily for r in returns]
    downside = [min(0.0, e) for e in excess]
    dd = math.sqrt(sum(d * d for d in downside) / len(downside))
    if dd == 0:
        return 0.0
    return _mean(excess) / dd * math.sqrt(periods)


def max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < mdd:
                mdd = dd
    return mdd


def win_rate(trade_pnls: list[float]) -> float:
    if not trade_pnls:
        return 0.0
    return sum(1 for p in trade_pnls if p > 0) / len(trade_pnls)


def avg_trade_pnl(trade_pnls: list[float]) -> float:
    return sum(trade_pnls) / len(trade_pnls) if trade_pnls else 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_backtest_metrics.py -v`
Expected: PASS (all 8)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/backtest/__init__.py packages/core/saalr_core/backtest/metrics.py packages/core/tests/test_backtest_metrics.py
git commit -m "feat(backtest): pure performance metrics (sharpe/sortino/max-dd/win-rate)"
```

---

## Task 2: Realized volatility (`saalr_core/backtest/vol.py`)

**Files:**
- Create: `packages/core/saalr_core/backtest/vol.py`
- Test: `packages/core/tests/test_backtest_vol.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_backtest_vol.py
import math

from saalr_core.backtest import vol


def test_log_returns():
    r = vol.log_returns([100.0, 110.0, 121.0])
    assert len(r) == 2
    assert abs(r[0] - math.log(1.1)) < 1e-12


def test_realized_vol_matches_hand_calc():
    # alternating +1%/-1% log moves -> stdev of [ln(1.01), ln(0.99*... )] annualized
    closes = [100.0]
    for _ in range(10):
        closes.append(closes[-1] * 1.01)
        closes.append(closes[-1] * 0.99)
    v = vol.realized_vol(closes, lookback=20)
    assert v > 0.0
    # sanity: annualized vol of ~1% daily moves is roughly 0.01*sqrt(252) ~ 0.16
    assert 0.05 < v < 0.40


def test_realized_vol_floor_on_insufficient_data():
    assert vol.realized_vol([100.0], lookback=20) == vol.VOL_FLOOR
    assert vol.realized_vol([], lookback=20) == vol.VOL_FLOOR


def test_realized_vol_floor_on_flat_series():
    assert vol.realized_vol([100.0] * 30, lookback=20) == vol.VOL_FLOOR


def test_realized_vol_uses_only_last_lookback_returns():
    # a long calm history then nothing changes the windowed result vs short calm
    closes = [100.0 * (1.0 + 0.001 * (i % 2)) for i in range(100)]
    v_full = vol.realized_vol(closes, lookback=20)
    v_short = vol.realized_vol(closes[-21:], lookback=20)
    assert abs(v_full - v_short) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_backtest_vol.py -v`
Expected: FAIL — `ModuleNotFoundError` / attribute missing

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/backtest/vol.py
from __future__ import annotations

import math

VOL_FLOOR = 0.01
TRADING_DAYS = 252


def log_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev > 0 and cur > 0:
            out.append(math.log(cur / prev))
    return out


def realized_vol(closes: list[float], lookback: int, periods: int = TRADING_DAYS) -> float:
    """Annualized stdev of the last `lookback` daily log returns. Floors at VOL_FLOOR
    on insufficient or degenerate (flat) data so BSM never divides by zero."""
    rets = log_returns(closes)
    window = rets[-lookback:] if lookback and len(rets) > lookback else rets
    if len(window) < 2:
        return VOL_FLOOR
    mu = sum(window) / len(window)
    var = sum((r - mu) ** 2 for r in window) / (len(window) - 1)
    vol = math.sqrt(var) * math.sqrt(periods)
    return max(vol, VOL_FLOOR)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_backtest_vol.py -v`
Expected: PASS (all 5)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/backtest/vol.py packages/core/tests/test_backtest_vol.py
git commit -m "feat(backtest): realized-volatility estimator with floor"
```

---

## Task 3: Relative template (`saalr_core/backtest/template.py`)

**Files:**
- Create: `packages/core/saalr_core/backtest/template.py`
- Test: `packages/core/tests/test_backtest_template.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_backtest_template.py
from datetime import date

import pytest

from saalr_core.backtest.template import RelativeTemplate
from saalr_core.strategies.types import (
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
    Side,
    StrategyConfig,
)


def _vertical() -> StrategyConfig:
    return StrategyConfig(
        underlying="AAPL",
        legs=[
            OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2025-03-21", 1),
            OptionLeg(OptionType.CALL, Side.SELL, 110.0, "2025-03-21", 1),
        ],
    )


def _calendar() -> StrategyConfig:
    return StrategyConfig(
        underlying="AAPL",
        legs=[
            OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2025-02-21", 1),  # front
            OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2025-04-21", 1),  # back
        ],
    )


def test_from_config_relative_legs_and_cycle_dte():
    ref = date(2025, 1, 1)
    t = RelativeTemplate.from_config(_vertical(), ref_spot=100.0, ref_date=ref)
    assert t.cycle_dte == (date(2025, 3, 21) - ref).days
    assert [round(rl.moneyness, 4) for rl in t.legs] == [1.0, 1.1]
    assert all(rl.dte == t.cycle_dte for rl in t.legs)  # same expiry vertical


def test_calendar_keeps_per_leg_dte_and_front_cycle():
    ref = date(2025, 1, 1)
    t = RelativeTemplate.from_config(_calendar(), ref_spot=100.0, ref_date=ref)
    front = (date(2025, 2, 21) - ref).days
    back = (date(2025, 4, 21) - ref).days
    assert sorted(rl.dte for rl in t.legs) == [front, back]
    assert t.cycle_dte == front  # min


def test_instantiate_rounds_strikes_and_sets_per_leg_expiry():
    ref = date(2025, 1, 1)
    t = RelativeTemplate.from_config(_calendar(), ref_spot=100.0, ref_date=ref)
    legs = t.instantiate(date(2025, 6, 2), spot=207.4, strike_increment=1.0)
    # both legs ATM (moneyness 1.0) -> strike rounds to 207
    assert all(leg.strike == 207.0 for leg in legs)
    # per-leg expiries preserved: roll_date + each leg's own dte
    expiries = sorted(leg.expiry for leg in legs)
    assert expiries == ["2025-07-23", "2025-09-20"]  # +51d (front), +110d (back)


def test_equity_and_cash_legs_carry_through():
    ref = date(2025, 1, 1)
    cfg = StrategyConfig(
        underlying="AAPL",
        legs=[
            OptionLeg(OptionType.CALL, Side.SELL, 105.0, "2025-03-21", 1),
            EquityLeg(Side.BUY, 100),
            CashLeg(5000.0),
        ],
    )
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=ref)
    legs = t.instantiate(date(2025, 1, 1), spot=100.0)
    kinds = sorted(leg.kind for leg in legs)
    assert kinds == ["cash", "equity", "option"]


def test_no_option_legs_raises():
    cfg = StrategyConfig(underlying="AAPL", legs=[EquityLeg(Side.BUY, 100)])
    with pytest.raises(ValueError, match="no option legs"):
        RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=date(2025, 1, 1))


def test_expired_leg_raises():
    cfg = StrategyConfig(
        underlying="AAPL",
        legs=[OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2024-12-01", 1)],
    )
    with pytest.raises(ValueError, match="not after"):
        RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=date(2025, 1, 1))
```

> Note on expected expiry dates: `2025-06-02 + 51d = 2025-07-23`; `2025-06-02 + 110d = 2025-09-20`. The implementer must confirm these by computing `roll_date + timedelta(days=dte)` — do not hand-wave.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_backtest_template.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/backtest/template.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from saalr_core.strategies.types import (
    CashLeg,
    EquityLeg,
    Leg,
    OptionLeg,
    OptionType,
    Side,
    StrategyConfig,
)


@dataclass(frozen=True)
class RelativeLeg:
    kind: str  # "option" | "equity" | "cash"
    side: Side | None = None
    qty: int = 0
    option_type: OptionType | None = None
    moneyness: float | None = None  # strike / ref_spot
    dte: int | None = None  # (expiry - ref_date).days
    amount: float | None = None  # cash collateral


@dataclass(frozen=True)
class RelativeTemplate:
    legs: list[RelativeLeg]
    cycle_dte: int  # the front (minimum) option-leg DTE

    @staticmethod
    def from_config(config: StrategyConfig, ref_spot: float, ref_date: date) -> "RelativeTemplate":
        if ref_spot <= 0:
            raise ValueError("ref_spot must be positive")
        rel: list[RelativeLeg] = []
        option_dtes: list[int] = []
        for leg in config.legs:
            if isinstance(leg, OptionLeg):
                expiry = date.fromisoformat(leg.expiry)
                dte = (expiry - ref_date).days
                if dte <= 0:
                    raise ValueError(
                        f"option leg expiry {leg.expiry} is not after {ref_date.isoformat()}"
                    )
                option_dtes.append(dte)
                rel.append(
                    RelativeLeg(
                        kind="option",
                        side=leg.side,
                        qty=leg.qty,
                        option_type=leg.option_type,
                        moneyness=leg.strike / ref_spot,
                        dte=dte,
                    )
                )
            elif isinstance(leg, EquityLeg):
                rel.append(RelativeLeg(kind="equity", side=leg.side, qty=leg.qty))
            elif isinstance(leg, CashLeg):
                rel.append(RelativeLeg(kind="cash", amount=leg.amount))
            else:  # pragma: no cover - defensive
                raise TypeError(f"unknown leg type: {type(leg)!r}")
        if not option_dtes:
            raise ValueError("strategy has no option legs to backtest")
        return RelativeTemplate(legs=rel, cycle_dte=min(option_dtes))

    def instantiate(
        self, roll_date: date, spot: float, strike_increment: float = 1.0
    ) -> list[Leg]:
        out: list[Leg] = []
        for rl in self.legs:
            if rl.kind == "option":
                strike = round(spot * rl.moneyness / strike_increment) * strike_increment
                expiry = (roll_date + timedelta(days=rl.dte)).isoformat()
                out.append(
                    OptionLeg(
                        option_type=rl.option_type,
                        side=rl.side,
                        strike=strike,
                        expiry=expiry,
                        qty=rl.qty,
                    )
                )
            elif rl.kind == "equity":
                out.append(EquityLeg(side=rl.side, qty=rl.qty))
            else:
                out.append(CashLeg(amount=rl.amount))
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_backtest_template.py -v`
Expected: PASS (all 6)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/backtest/template.py packages/core/tests/test_backtest_template.py
git commit -m "feat(backtest): relative template (per-leg moneyness/DTE, front-expiry cycle)"
```

---

## Task 4: Rolling engine (`saalr_core/backtest/engine.py`)

**Files:**
- Create: `packages/core/saalr_core/backtest/engine.py`
- Test: `packages/core/tests/test_backtest_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_backtest_engine.py
from datetime import date, timedelta

from saalr_core.backtest.engine import BacktestParams, run_backtest_engine
from saalr_core.backtest.template import RelativeTemplate
from saalr_core.strategies.types import OptionLeg, OptionType, Side, StrategyConfig


def _closes(start: date, prices: list[float]) -> dict:
    return {start + timedelta(days=i): p for i, p in enumerate(prices)}


def _long_call(dte_expiry: str) -> StrategyConfig:
    return StrategyConfig(
        underlying="X",
        legs=[OptionLeg(OptionType.CALL, Side.BUY, 100.0, dte_expiry, 1)],
    )


def _params(start: date, end: date, **kw) -> BacktestParams:
    base = dict(start=start, end=end, initial_capital=100_000.0, rate=0.04,
                vol_lookback=20, include_costs=False)
    base.update(kw)
    return BacktestParams(**base)


def test_long_call_on_flat_underlying_loses_to_theta():
    start = date(2025, 1, 1)
    prices = [100.0] * 120  # dead flat
    closes = _closes(start, prices)
    # ref_date is first sim day; template built against it
    cfg = _long_call("2025-02-15")  # ~45 DTE from 2025-01-01
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=start)
    res = run_backtest_engine(closes, t, _params(start, start + timedelta(days=119)))
    assert res["metrics"]["total_return"] < 0  # long premium decays on flat tape
    assert res["model"] == "bsm"
    assert res["iv_source"] == "realized_vol"
    assert res["approximate"] is True
    assert res["metrics"]["trades"] >= 1
    # every metric finite
    for v in res["metrics"].values():
        assert v == v  # not NaN


def test_long_call_on_rising_underlying_profits():
    start = date(2025, 1, 1)
    prices = [100.0 + i * 0.5 for i in range(120)]  # steady uptrend
    closes = _closes(start, prices)
    cfg = _long_call("2025-02-15")
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=start)
    res = run_backtest_engine(closes, t, _params(start, start + timedelta(days=119)))
    assert res["metrics"]["total_return"] > 0


def test_calendar_cycles_on_front_expiry_and_is_net_positive_on_flat_tape():
    start = date(2025, 1, 1)
    prices = [100.0] * 200
    closes = _closes(start, prices)
    cfg = StrategyConfig(
        underlying="X",
        legs=[
            OptionLeg(OptionType.CALL, Side.SELL, 100.0, "2025-02-01", 1),  # front ~31d
            OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2025-04-01", 1),  # back ~90d
        ],
    )
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=start)
    res = run_backtest_engine(closes, t, _params(start, start + timedelta(days=199)))
    # ~31-day front cycles over ~199 days -> multiple completed cycles
    assert res["metrics"]["trades"] >= 4
    # short front decays faster than long back on a flat tape -> net positive
    assert res["metrics"]["total_return"] > 0


def test_too_few_bars_raises():
    start = date(2025, 1, 1)
    closes = _closes(start, [100.0])  # one bar
    cfg = _long_call("2025-02-15")
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=start)
    try:
        run_backtest_engine(closes, t, _params(start, start))
        assert False, "expected ValueError"
    except ValueError:
        pass
```

> The directional assertions (`< 0`, `> 0`) are the contract — the implementer must NOT tune magic numbers to pass. If `test_calendar...` does not come out net-positive, that is a real signal: re-check that the front (short) leg settles at intrinsic while the back (long) leg retains time value at the front expiry.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_backtest_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/backtest/engine.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from saalr_core.pricing.greeks import price as bsm_price
from saalr_core.pricing.types import OptionKind, OptionParams
from saalr_core.strategies.types import (
    OPTION_MULTIPLIER,
    EquityLeg,
    Leg,
    OptionLeg,
    OptionType,
)

from . import metrics as _m
from .template import RelativeTemplate
from .vol import realized_vol

ENGINE_VERSION = "bt-engine-1"


@dataclass(frozen=True)
class BacktestParams:
    start: date
    end: date
    initial_capital: float = 100_000.0
    rate: float = 0.04
    vol_lookback: int = 20
    include_costs: bool = True
    commission_per_contract: float = 0.65
    slippage_per_contract: float = 0.50
    strike_increment: float = 1.0


def _kind(ot: OptionType) -> OptionKind:
    return OptionKind.CALL if ot is OptionType.CALL else OptionKind.PUT


def _intrinsic(ot: OptionType, spot: float, strike: float) -> float:
    return max(0.0, spot - strike) if ot is OptionType.CALL else max(0.0, strike - spot)


def _option_unit_value(leg: OptionLeg, spot: float, sigma: float, t_years: float, rate: float) -> float:
    if t_years <= 0:
        return _intrinsic(leg.option_type, spot, leg.strike)
    return bsm_price(
        OptionParams(
            spot=spot, strike=leg.strike, t_years=t_years, rate=rate,
            sigma=sigma, div_yield=0.0, kind=_kind(leg.option_type),
        )
    )


def _position_value(legs: list[Leg], spot: float, sigma: float, d: date, rate: float) -> float:
    """Signed mark value of the position (what it is worth to liquidate now).
    Short legs contribute negative value; per-leg time decays to its own expiry."""
    total = 0.0
    for leg in legs:
        if isinstance(leg, OptionLeg):
            expiry = date.fromisoformat(leg.expiry)
            t = max(0, (expiry - d).days) / 365.0
            unit = _option_unit_value(leg, spot, sigma, t, rate)
            total += leg.side.sign * leg.qty * OPTION_MULTIPLIER * unit
        elif isinstance(leg, EquityLeg):
            total += leg.side.sign * leg.qty * spot
        # CashLeg contributes no P&L
    return total


def _cycle_cost(legs: list[Leg], params: BacktestParams) -> float:
    if not params.include_costs:
        return 0.0
    contracts = sum(leg.qty for leg in legs if isinstance(leg, OptionLeg))
    return contracts * (params.commission_per_contract + params.slippage_per_contract)


def run_backtest_engine(
    closes: dict[date, float], template: RelativeTemplate, params: BacktestParams
) -> dict:
    if not closes:
        raise ValueError("no bars supplied for the underlying")
    all_dates = sorted(closes)
    sim_days = [d for d in all_dates if params.start <= d <= params.end]
    if len(sim_days) < 2:
        raise ValueError("need at least 2 trading days with bars in [start, end]")

    def vol_at(d: date) -> float:
        series = [closes[x] for x in all_dates if x <= d]
        return realized_vol(series, params.vol_lookback)

    equity_curve: list[float] = []
    trade_pnls: list[float] = []
    realized = 0.0

    def open_cycle(d: date) -> tuple[list[Leg], float, float, date]:
        legs = template.instantiate(d, closes[d], params.strike_increment)
        entry_value = _position_value(legs, closes[d], vol_at(d), d, params.rate)
        cost = _cycle_cost(legs, params)
        front_expiry = d + timedelta(days=template.cycle_dte)
        return legs, entry_value, cost, front_expiry

    legs, entry_value, open_cost, front_expiry = open_cycle(sim_days[0])

    for d in sim_days:
        if d >= front_expiry:
            # settle the current cycle at d (front legs intrinsic, longer legs marked)
            settle_value = _position_value(legs, closes[d], vol_at(d), d, params.rate)
            total_cost = open_cost + _cycle_cost(legs, params)
            cycle_pnl = (settle_value - entry_value) - total_cost
            realized += cycle_pnl
            trade_pnls.append(cycle_pnl)
            # close-and-reopen the full structure on this day
            legs, entry_value, open_cost, front_expiry = open_cycle(d)
        cur_value = _position_value(legs, closes[d], vol_at(d), d, params.rate)
        equity_curve.append(params.initial_capital + realized + (cur_value - entry_value - open_cost))

    # realize the final still-open cycle (for trade stats) if it never hit its front expiry
    last_d = sim_days[-1]
    if last_d < front_expiry:
        settle_value = _position_value(legs, closes[last_d], vol_at(last_d), last_d, params.rate)
        total_cost = open_cost + _cycle_cost(legs, params)
        trade_pnls.append((settle_value - entry_value) - total_cost)

    days_span = (sim_days[-1] - sim_days[0]).days
    returns = _m.daily_returns(equity_curve)
    metrics = {
        "total_return": _m.total_return(equity_curve),
        "annualized_return": _m.annualized_return(equity_curve, days_span),
        "sharpe": _m.sharpe(returns, params.rate),
        "sortino": _m.sortino(returns, params.rate),
        "max_drawdown": _m.max_drawdown(equity_curve),
        "win_rate": _m.win_rate(trade_pnls),
        "trades": len(trade_pnls),
        "avg_trade_pnl": _m.avg_trade_pnl(trade_pnls),
    }
    return {
        "metrics": metrics,
        "model": "bsm",
        "iv_source": "realized_vol",
        "rate": params.rate,
        "vol_lookback": params.vol_lookback,
        "include_costs": params.include_costs,
        "engine_version": ENGINE_VERSION,
        "approximate": True,
        "equity_points": len(equity_curve),
        "start": params.start.isoformat(),
        "end": params.end.isoformat(),
        "initial_capital": params.initial_capital,
        "final_equity": equity_curve[-1],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_backtest_engine.py -v`
Expected: PASS (all 4)

- [ ] **Step 5: Run the whole core suite + ruff**

Run: `uv run pytest packages/core/tests/ -q && uvx ruff check packages/core/saalr_core/backtest/`
Expected: PASS, no lint errors

- [ ] **Step 6: Commit**

```bash
git add packages/core/saalr_core/backtest/engine.py packages/core/tests/test_backtest_engine.py
git commit -m "feat(backtest): rolling model-priced engine (per-leg expiry, MTM, settle)"
```

---

## Task 5: Config deserializer (`saalr_core/strategies/serde.py`)

The worker reads `strategies.config_json` (a plain dict from JSONB, with enum values as strings) and must reconstruct a typed `StrategyConfig`.

**Files:**
- Create: `packages/core/saalr_core/strategies/serde.py`
- Test: `packages/core/tests/test_strategies_serde.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_strategies_serde.py
import pytest

from saalr_core.strategies.serde import config_from_json
from saalr_core.strategies.types import (
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
    Side,
)


def test_round_trip_all_leg_kinds():
    data = {
        "underlying": "AAPL",
        "legs": [
            {"kind": "option", "option_type": "CALL", "side": "BUY", "strike": 100,
             "expiry": "2025-03-21", "qty": 1, "entry_price": 6.0},
            {"kind": "equity", "side": "SELL", "qty": 100, "entry_price": None},
            {"kind": "cash", "amount": 5000},
        ],
    }
    cfg = config_from_json(data)
    assert cfg.underlying == "AAPL"
    opt, eq, cash = cfg.legs
    assert isinstance(opt, OptionLeg)
    assert opt.option_type is OptionType.CALL and opt.side is Side.BUY
    assert opt.strike == 100.0 and opt.expiry == "2025-03-21" and opt.qty == 1
    assert isinstance(eq, EquityLeg) and eq.side is Side.SELL and eq.qty == 100
    assert isinstance(cash, CashLeg) and cash.amount == 5000.0


def test_kind_defaults_to_option():
    cfg = config_from_json(
        {"underlying": "X", "legs": [
            {"option_type": "PUT", "side": "SELL", "strike": 90, "expiry": "2025-03-21", "qty": 2}
        ]}
    )
    assert isinstance(cfg.legs[0], OptionLeg) and cfg.legs[0].option_type is OptionType.PUT


def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="unknown leg kind"):
        config_from_json({"underlying": "X", "legs": [{"kind": "future"}]})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_strategies_serde.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/core/saalr_core/strategies/serde.py
from __future__ import annotations

from .types import CashLeg, EquityLeg, Leg, OptionLeg, OptionType, Side, StrategyConfig


def _leg_from_dict(d: dict) -> Leg:
    kind = d.get("kind", "option")
    if kind == "option":
        return OptionLeg(
            option_type=OptionType(d["option_type"]),
            side=Side(d["side"]),
            strike=float(d["strike"]),
            expiry=d["expiry"],
            qty=int(d["qty"]),
            entry_price=d.get("entry_price"),
        )
    if kind == "equity":
        return EquityLeg(side=Side(d["side"]), qty=int(d["qty"]), entry_price=d.get("entry_price"))
    if kind == "cash":
        return CashLeg(amount=float(d["amount"]))
    raise ValueError(f"unknown leg kind: {kind!r}")


def config_from_json(data: dict) -> StrategyConfig:
    return StrategyConfig(
        underlying=data["underlying"],
        legs=[_leg_from_dict(d) for d in data.get("legs", [])],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_strategies_serde.py -v`
Expected: PASS (all 3)

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/strategies/serde.py packages/core/tests/test_strategies_serde.py
git commit -m "feat(strategies): config_from_json deserializer for stored JSONB configs"
```

---

## Task 6: Backtest-worker scaffold + repo (`apps/backtest-worker/`)

**Files:**
- Create: `apps/backtest-worker/pyproject.toml`
- Create: `apps/backtest-worker/backtest_worker/__init__.py` (empty)
- Create: `apps/backtest-worker/backtest_worker/__main__.py`
- Create: `apps/backtest-worker/backtest_worker/repo.py`

- [ ] **Step 1: Create the package manifest**

```toml
# apps/backtest-worker/pyproject.toml
[project]
name = "saalr-backtest-worker"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "saalr-core",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["backtest_worker"]

[tool.uv.sources]
saalr-core = { workspace = true }
```

- [ ] **Step 2: Create the package + entrypoint**

```python
# apps/backtest-worker/backtest_worker/__init__.py
```

```python
# apps/backtest-worker/backtest_worker/__main__.py
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write the repo**

```python
# apps/backtest-worker/backtest_worker/repo.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.trading import Backtest, Strategy


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_strategy(session: AsyncSession, strategy_id: UUID) -> Strategy | None:
    return (
        await session.execute(select(Strategy).where(Strategy.strategy_id == strategy_id))
    ).scalar_one_or_none()


async def get_backtest(session: AsyncSession, backtest_id: UUID) -> Backtest | None:
    return (
        await session.execute(select(Backtest).where(Backtest.backtest_id == backtest_id))
    ).scalar_one_or_none()


async def load_underlying_closes(
    session: AsyncSession, symbol: str, market: str, start: date, end: date, lookback: int
) -> dict[date, float]:
    """Daily closes in [start - warmup, end]. Warmup pads back enough calendar days to
    fill the realized-vol lookback window. `bars` is non-RLS (shared market data)."""
    pad_start = start - timedelta(days=int(lookback * 1.6) + 7)
    rows = (
        await session.execute(
            text(
                """
                SELECT ts, close FROM bars
                WHERE symbol = :sym AND market = :mkt AND interval = '1d'
                  AND ts::date >= :s AND ts::date <= :e
                ORDER BY ts
                """
            ),
            {"sym": symbol, "mkt": market, "s": pad_start, "e": end},
        )
    ).all()
    return {r.ts.date(): float(r.close) for r in rows}


async def create_backtest(
    session: AsyncSession,
    tenant_id: UUID,
    strategy_id: UUID,
    start: date,
    end: date,
    config_snapshot: dict,
) -> UUID:
    row = Backtest(
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        start_date=start,
        end_date=end,
        status="queued",
        config_snapshot=config_snapshot,
    )
    session.add(row)
    await session.flush()
    return row.backtest_id


async def mark_running(session: AsyncSession, backtest_id: UUID) -> None:
    bt = await get_backtest(session, backtest_id)
    bt.status = "running"
    bt.started_at = _utcnow()


async def save_result(
    session: AsyncSession,
    backtest_id: UUID,
    metrics_json: dict | None,
    status: str,
    error: str | None = None,
) -> None:
    bt = await get_backtest(session, backtest_id)
    bt.status = status
    bt.metrics_json = metrics_json
    bt.error_message = error
    bt.completed_at = _utcnow()
```

- [ ] **Step 4: Register the workspace member**

Run: `uv sync`
Expected: resolves and installs `saalr-backtest-worker` (editable) into the workspace venv. If `apps/backtest-worker` is not auto-picked-up, confirm the root `pyproject.toml` `[tool.uv.workspace] members` includes `apps/*` (it does) — no edit needed.

- [ ] **Step 5: Commit**

```bash
git add apps/backtest-worker/pyproject.toml apps/backtest-worker/backtest_worker/__init__.py apps/backtest-worker/backtest_worker/__main__.py apps/backtest-worker/backtest_worker/repo.py uv.lock
git commit -m "feat(backtest-worker): scaffold app + DB repo (strategy/bars/backtest)"
```

---

## Task 7: Worker service + integration test (`service.py`)

**Files:**
- Create: `apps/backtest-worker/backtest_worker/service.py`
- Test: `tests/integration/test_backtest.py`

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_backtest.py
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from backtest_worker import service
from saalr_core.db.session import tenant_session
from saalr_core.ids import new_id


async def _bootstrap_tenant(admin_engine, email: str, cuid: str):
    uid, tid, sid = new_id(), new_id(), new_id()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("SELECT auth_bootstrap(:uid, :tid, :sid, :cuid, :email)"),
            {"uid": str(uid), "tid": str(tid), "sid": str(sid), "cuid": cuid, "email": email},
        )
    return uid, tid


async def _seed_bars(admin_engine, symbol: str, start: datetime, prices: list[float]):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol = :s"), {"s": symbol})
        for i, px in enumerate(prices):
            ts = start + timedelta(days=i)
            await conn.execute(
                text(
                    """INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                       VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""
                ),
                {"ts": ts, "sym": symbol, "o": Decimal(str(px)), "h": Decimal(str(px + 1)),
                 "l": Decimal(str(px - 1)), "c": Decimal(str(px)), "v": 1000},
            )


async def _seed_strategy(app_sessionmaker, tid, uid, underlying: str):
    sid = new_id()
    config = {
        "underlying": underlying,
        "legs": [
            {"kind": "option", "option_type": "CALL", "side": "BUY",
             "strike": 100, "expiry": "2025-03-01", "qty": 1, "entry_price": None}
        ],
    }
    async with tenant_session(app_sessionmaker, tid) as s:
        await s.execute(
            text(
                """INSERT INTO strategies (strategy_id, tenant_id, user_id, name, state, config_json, market)
                   VALUES (:sid,:tid,:uid,'BT','draft', CAST(:cfg AS JSONB), 'US')"""
            ),
            {"sid": str(sid), "tid": str(tid), "uid": str(uid), "cfg": json.dumps(config)},
        )
    return sid


async def test_backtest_succeeds_and_persists(app_sessionmaker, admin_engine):
    uid, tid = await _bootstrap_tenant(admin_engine, "bt-ok@x.com", "ct_bt_ok")
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await _seed_bars(admin_engine, "AAPL", start, [100.0 + i * 0.3 for i in range(80)])
    sid = await _seed_strategy(app_sessionmaker, tid, uid, "AAPL")

    bt_id, outcome = await service.create_and_run(
        app_sessionmaker, tid, sid,
        {"start": "2025-02-01", "end": "2025-03-10", "vol_lookback": 20, "include_costs": False},
    )
    assert outcome["status"] == "succeeded"

    async with tenant_session(app_sessionmaker, tid) as s:
        row = (
            await s.execute(
                text("SELECT status, metrics_json FROM backtests WHERE backtest_id = :b"),
                {"b": str(bt_id)},
            )
        ).first()
    assert row.status == "succeeded"
    assert row.metrics_json["model"] == "bsm"
    assert row.metrics_json["iv_source"] == "realized_vol"
    assert row.metrics_json["approximate"] is True
    assert "sharpe" in row.metrics_json["metrics"]


async def test_backtest_fails_when_no_bars(app_sessionmaker, admin_engine):
    uid, tid = await _bootstrap_tenant(admin_engine, "bt-nobars@x.com", "ct_bt_nobars")
    sid = await _seed_strategy(app_sessionmaker, tid, uid, "ZZZZ")  # no bars seeded

    bt_id, outcome = await service.create_and_run(
        app_sessionmaker, tid, sid, {"start": "2025-02-01", "end": "2025-03-10"}
    )
    assert outcome["status"] == "failed"

    async with tenant_session(app_sessionmaker, tid) as s:
        row = (
            await s.execute(
                text("SELECT status, error_message FROM backtests WHERE backtest_id = :b"),
                {"b": str(bt_id)},
            )
        ).first()
    assert row.status == "failed"
    assert row.error_message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_backtest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest_worker.service'`

- [ ] **Step 3: Write the service**

```python
# apps/backtest-worker/backtest_worker/service.py
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from saalr_core.backtest.engine import ENGINE_VERSION, BacktestParams, run_backtest_engine
from saalr_core.backtest.template import RelativeTemplate
from saalr_core.db.session import tenant_session
from saalr_core.strategies.serde import config_from_json

from . import repo


def _params_from(bt_params: dict, start: date, end: date) -> BacktestParams:
    return BacktestParams(
        start=start,
        end=end,
        initial_capital=float(bt_params.get("initial_capital", 100_000.0)),
        rate=float(bt_params.get("rate", 0.04)),
        vol_lookback=int(bt_params.get("vol_lookback", 20)),
        include_costs=bool(bt_params.get("include_costs", True)),
        commission_per_contract=float(bt_params.get("commission_per_contract", 0.65)),
        slippage_per_contract=float(bt_params.get("slippage_per_contract", 0.50)),
        strike_increment=float(bt_params.get("strike_increment", 1.0)),
    )


async def run_backtest(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: UUID, backtest_id: UUID
) -> dict:
    """Run an existing (queued) backtest by id, persisting status + metrics.

    Runs in ONE tenant transaction. On a backtest-logic failure we persist
    status='failed' and return — we do NOT re-raise, because tenant_session would
    otherwise roll back the very failure row we just wrote."""
    async with tenant_session(sessionmaker, tenant_id) as session:
        bt = await repo.get_backtest(session, backtest_id)
        if bt is None:
            raise ValueError(f"backtest {backtest_id} not found")
        await repo.mark_running(session, backtest_id)
        try:
            strat = await repo.get_strategy(session, bt.strategy_id)
            if strat is None:
                raise ValueError("strategy not found")
            config = config_from_json(strat.config_json)
            params = _params_from(bt.config_snapshot.get("params", {}), bt.start_date, bt.end_date)
            closes = await repo.load_underlying_closes(
                session, config.underlying, strat.market, bt.start_date, bt.end_date, params.vol_lookback
            )
            sim_dates = sorted(d for d in closes if bt.start_date <= d <= bt.end_date)
            if len(sim_dates) < 2:
                raise ValueError(f"insufficient bars for {config.underlying} in [{bt.start_date}, {bt.end_date}]")
            ref_date = sim_dates[0]
            template = RelativeTemplate.from_config(config, ref_spot=closes[ref_date], ref_date=ref_date)
            result = run_backtest_engine(closes, template, params)
            await repo.save_result(session, backtest_id, result, "succeeded")
            return {"status": "succeeded", "result": result}
        except Exception as exc:  # noqa: BLE001 - persisted as a failed run, then returned
            await repo.save_result(session, backtest_id, None, "failed", str(exc))
            return {"status": "failed", "error": str(exc)}


async def create_and_run(
    sessionmaker: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    strategy_id: UUID,
    params: dict,
) -> tuple[UUID, dict]:
    """Create a queued backtest row (its own transaction), then run it. Mirrors how
    8b's API will create the row and the queue worker will run it later."""
    start = date.fromisoformat(params["start"])
    end = date.fromisoformat(params["end"])
    async with tenant_session(sessionmaker, tenant_id) as session:
        strat = await repo.get_strategy(session, strategy_id)
        if strat is None:
            raise ValueError("strategy not found")
        snapshot = {"config": strat.config_json, "params": params, "engine_version": ENGINE_VERSION}
        backtest_id = await repo.create_backtest(session, tenant_id, strategy_id, start, end, snapshot)
    outcome = await run_backtest(sessionmaker, tenant_id, backtest_id)
    return backtest_id, outcome
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_backtest.py -v`
Expected: PASS (both). If `test_backtest_succeeds_and_persists` fails on a poisoned-session error after a DB statement error inside the try, confirm the only DB call there is `load_underlying_closes` (a SELECT) and that the "insufficient bars" check is a pure Python guard on the returned dict (it is) — engine failures are pure Python and leave the session healthy.

- [ ] **Step 5: Commit**

```bash
git add apps/backtest-worker/backtest_worker/service.py tests/integration/test_backtest.py
git commit -m "feat(backtest-worker): run-by-id service + create_and_run, with integration tests"
```

---

## Task 8: CLI (`cli.py`)

**Files:**
- Create: `apps/backtest-worker/backtest_worker/cli.py`
- Test: `apps/backtest-worker/tests/test_cli_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/backtest-worker/tests/test_cli_parser.py
from backtest_worker.cli import build_parser


def test_backtest_subcommand_parses():
    p = build_parser()
    args = p.parse_args(
        ["backtest", "--strategy", "s-1", "--tenant", "t-1",
         "--start", "2025-01-01", "--end", "2025-06-01", "--no-costs"]
    )
    assert args.cmd == "backtest"
    assert args.strategy == "s-1" and args.tenant == "t-1"
    assert args.start == "2025-01-01" and args.end == "2025-06-01"
    assert args.no_costs is True


def test_run_subcommand_parses():
    p = build_parser()
    args = p.parse_args(["run", "--tenant", "t-1", "bt-9"])
    assert args.cmd == "run" and args.tenant == "t-1" and args.backtest_id == "bt-9"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/backtest-worker/tests/test_cli_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the CLI**

```python
# apps/backtest-worker/backtest_worker/cli.py
from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker

from . import service


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backtest_worker", description="Saalr backtest worker")
    sub = p.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", help="create + run a backtest for a strategy")
    bt.add_argument("--strategy", required=True)
    bt.add_argument("--tenant", required=True)
    bt.add_argument("--start", required=True)
    bt.add_argument("--end", required=True)
    bt.add_argument("--capital", type=float, default=100_000.0)
    bt.add_argument("--rate", type=float, default=0.04)
    bt.add_argument("--vol-lookback", type=int, default=20, dest="vol_lookback")
    bt.add_argument("--no-costs", action="store_true", dest="no_costs")

    rn = sub.add_parser("run", help="run an existing (queued) backtest by id")
    rn.add_argument("--tenant", required=True)
    rn.add_argument("backtest_id")
    return p


async def _with_sessionmaker(fn):
    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    try:
        return await fn(create_sessionmaker(engine))
    finally:
        await engine.dispose()


async def _cmd_backtest(args) -> None:
    params = {
        "start": args.start,
        "end": args.end,
        "initial_capital": args.capital,
        "rate": args.rate,
        "vol_lookback": args.vol_lookback,
        "include_costs": not args.no_costs,
    }

    async def go(sm):
        return await service.create_and_run(sm, UUID(args.tenant), UUID(args.strategy), params)

    bt_id, outcome = await _with_sessionmaker(go)
    print(f"backtest {bt_id}: {outcome['status']}")
    if outcome["status"] == "succeeded":
        print(json.dumps(outcome["result"]["metrics"], indent=2))
    else:
        print(outcome.get("error", ""))


async def _cmd_run(args) -> None:
    async def go(sm):
        return await service.run_backtest(sm, UUID(args.tenant), UUID(args.backtest_id))

    outcome = await _with_sessionmaker(go)
    print(f"backtest {args.backtest_id}: {outcome['status']}")


_DISPATCH = {"backtest": _cmd_backtest, "run": _cmd_run}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest apps/backtest-worker/tests/test_cli_parser.py -v`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add apps/backtest-worker/backtest_worker/cli.py apps/backtest-worker/tests/test_cli_parser.py
git commit -m "feat(backtest-worker): CLI (backtest create+run / run-by-id)"
```

---

## Task 9: Full suite + lint gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: all green (core + integration on the 55432 env; any live-only tests skipped as before)

- [ ] **Step 2: Lint**

Run: `uvx ruff check packages/core/saalr_core/backtest packages/core/saalr_core/strategies/serde.py apps/backtest-worker`
Expected: no errors

- [ ] **Step 3: CLI smoke (no DB)**

Run: `uv run python -m backtest_worker --help`
Expected: prints usage listing `backtest` and `run` subcommands

- [ ] **Step 4: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "chore(backtest): suite + lint green for slice 8a"
```

---

## Self-review notes (addressed)

- **Spec coverage:** metrics (T1), realized-vol IV (T2), relative template incl. calendars/diagonals + front-expiry cycle (T3), rolling BSM engine w/ per-leg expiry + settle + honesty labels (T4), config deserialize (T5), worker repo (T6), run-by-id + create_and_run + persistence + RLS tenant session (T7), CLI (T8), gate (T9). Equity-only → failure is covered by T3 `test_no_option_legs_raises` and surfaced as `status=failed` via the engine/template error path in T7.
- **RLS rollback trap:** `run_backtest` deliberately does NOT re-raise after persisting `status='failed'`, because `tenant_session` wraps one transaction — re-raising would roll back the failure write. `create_and_run` uses two separate `tenant_session` blocks (create commits, then run commits), mirroring 8b's API-creates / worker-runs split. Documented in T7 Step 3.
- **asyncpg binding:** bars seeded with `Decimal` for NUMERIC and `datetime` for `ts`; `load_underlying_closes` compares `ts::date` against `date` params. No `str`/`float` bound to typed columns.
- **Type consistency:** `OptionType`/`Side` (domain) vs `OptionKind` (pricing) bridged by `_kind()` in the engine. `expiry` is a `YYYY-MM-DD` string everywhere (matches `OptionLeg`). Engine returns a plain JSON-serializable dict → straight into `metrics_json` (JSONB).
