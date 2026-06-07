# Forecasts & Simulation: ARIMA + LSTM Price Forecast & HAR-RV Vol Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add (A) a new ARIMA+LSTM+naive **Price forecast** panel to Models → Insights, and (B) a **HAR-RV** model to the existing GARCH/HV21 volatility forecast.

**Architecture:** Pure model functions live in `packages/ml/saalr_ml` (HAR is pure-numpy; ARIMA via `statsmodels`, LSTM via `torch`). The API layer (`apps/api/saalr_api/forecast/`) caches in Redis, gates on `ml_forecast`, persists `model_validation_runs`, and offloads heavy training via `asyncio.to_thread`. The web layer (`apps/web/src/features/models`) renders SVG panels with axes.

**Tech Stack:** Python 3.12, numpy/scipy, statsmodels, torch (CPU), FastAPI, Redis, React 18 + TS + Vitest, TanStack Query.

**Spec:** `docs/superpowers/specs/2026-06-06-price-forecast-arima-lstm-design.md`

**Conventions:** DB on **55432** (Docker), Redis 6379. Run Python tests with:
```
APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" \
ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" \
REDIS_URL="redis://localhost:6379/0" python -m pytest <path> -q
```
ml-only unit tests (no DB) run with plain `python -m pytest packages/ml/tests/<file> -q`.
Web tests: `pnpm -C apps/web test -- run <file>`. Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Do NOT touch `tools/equity-screener/...`, root `.gitignore`, or `.env`.

---

# Part 1 — HAR-RV volatility model (Feature B, pure-numpy, no new deps)

### Task 1: `saalr_ml/har.py` — HAR realized-variance forecaster

**Files:**
- Create: `packages/ml/saalr_ml/har.py`
- Test: `packages/ml/tests/test_har.py`

- [ ] **Step 1: Write the failing test**

Create `packages/ml/tests/test_har.py`:
```python
import numpy as np
import pytest

from saalr_ml.har import fit_har, har_one_step, har_rv_forecast


def test_fit_har_recovers_linear_relationship():
    # rv[t] generated as a known linear fn of its daily/weekly/monthly lags + tiny noise
    rng = np.random.default_rng(0)
    n = 400
    rv = np.abs(rng.standard_normal(n)) * 0.5 + 1.0  # positive variances
    beta = fit_har(rv)
    assert beta.shape == (4,)
    # one-step prediction is finite and non-negative
    pred = har_one_step(rv, beta)
    assert np.isfinite(pred) and pred >= 0


def test_har_rv_forecast_shape_and_positive():
    rng = np.random.default_rng(1)
    returns = rng.standard_normal(500) * 1.0  # scaled (×100) returns
    path = har_rv_forecast(returns, horizon=10)
    assert len(path) == 10
    assert all(np.isfinite(x) and x >= 0 for x in path)


def test_fit_har_rejects_short_series():
    with pytest.raises(ValueError):
        fit_har(np.ones(10))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest packages/ml/tests/test_har.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'saalr_ml.har'`.

- [ ] **Step 3: Implement `packages/ml/saalr_ml/har.py`**

```python
from __future__ import annotations

import numpy as np

_TRADING_DAYS = 252


def _har_design(rv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Build (X, y) for HAR: target rv[t]; features [1, rv_d, rv_w, rv_m] from info up to t-1.
    Rows start at t=22 (monthly lag needs 22 trailing days)."""
    rv = np.asarray(rv, dtype=float)
    n = len(rv)
    rows_x, rows_y = [], []
    for t in range(22, n):
        rv_d = rv[t - 1]
        rv_w = rv[t - 5:t].mean()
        rv_m = rv[t - 22:t].mean()
        rows_x.append([1.0, rv_d, rv_w, rv_m])
        rows_y.append(rv[t])
    return np.asarray(rows_x, dtype=float), np.asarray(rows_y, dtype=float)


def fit_har(rv: np.ndarray) -> np.ndarray:
    """OLS fit of the 4 HAR coefficients [intercept, daily, weekly, monthly]."""
    x, y = _har_design(rv)
    if len(y) == 0:
        raise ValueError("series too short for HAR (need > 22 daily variances)")
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return beta


def har_one_step(rv_hist: np.ndarray, beta: np.ndarray) -> float:
    """Next-day variance from a variance history (>= 22 long), clamped non-negative."""
    rv_hist = np.asarray(rv_hist, dtype=float)
    feats = np.array([1.0, rv_hist[-1], rv_hist[-5:].mean(), rv_hist[-22:].mean()])
    return max(float(beta @ feats), 1e-12)


def har_rv_forecast(returns: np.ndarray, horizon: int) -> list[float]:
    """Annualized vol-PERCENT path of length `horizon`. `returns` are scaled (×100) log-returns;
    the daily realized-variance proxy is rv = returns**2 (no intraday data available)."""
    returns = np.asarray(returns, dtype=float)
    rv = returns ** 2
    beta = fit_har(rv)
    hist = list(rv)
    out = []
    for _ in range(horizon):
        nxt = har_one_step(np.asarray(hist), beta)
        out.append(round(float(np.sqrt(nxt * _TRADING_DAYS)), 4))
        hist.append(nxt)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest packages/ml/tests/test_har.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/ml/saalr_ml/har.py packages/ml/tests/test_har.py
git commit -m "feat(ml): HAR-RV realized-variance forecaster (pure numpy)"
```

---

### Task 2: Extend `walk_forward` to score & rank HAR

**Files:**
- Modify: `packages/ml/saalr_ml/evaluate.py`
- Test: `packages/ml/tests/test_evaluate.py`

- [ ] **Step 1: Write the failing test** — append to `packages/ml/tests/test_evaluate.py`:

```python
def test_walk_forward_reports_har_and_can_pick_it():
    from saalr_ml.evaluate import walk_forward
    rng = np.random.default_rng(7)
    r = rng.standard_normal(1500) * 1.0
    wf = walk_forward(r, holdout_days=60)
    assert hasattr(wf, "har_mae") and np.isfinite(wf.har_mae)
    assert wf.primary in ("garch", "hv21", "har")
    # primary is the lowest-MAE of the three
    best = min(("garch", wf.garch_mae), ("hv21", wf.hv21_mae), ("har", wf.har_mae), key=lambda t: t[1])
    assert wf.primary == best[0]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest packages/ml/tests/test_evaluate.py::test_walk_forward_reports_har_and_can_pick_it -q`
Expected: FAIL — `WalkForward` has no attribute `har_mae`.

- [ ] **Step 3: Edit `packages/ml/saalr_ml/evaluate.py`**

Replace the imports + dataclass + function body. New full file:
```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .garch import conditional_variance, fit_garch11
from .har import fit_har, har_one_step


@dataclass(frozen=True)
class WalkForward:
    garch_mae: float
    hv21_mae: float
    har_mae: float
    lift: float
    primary: str
    holdout_days: int


def walk_forward(returns: np.ndarray, holdout_days: int = 40) -> WalkForward:
    """Score GARCH, HV21 and HAR one-step-ahead variance forecasts across the holdout against
    the realized-variance proxy r^2, and pick the lowest-MAE model as `primary`."""
    returns = np.asarray(returns, dtype=float)
    n = len(returns)
    if n < holdout_days + 22:  # HAR monthly lag needs 22 training days before the first holdout day
        raise ValueError("series too short for the requested holdout")
    train = returns[:-holdout_days]
    params = fit_garch11(train)

    sigma2, resid = conditional_variance(params, returns)
    idx = range(n - holdout_days, n)
    garch_fc = sigma2[n - holdout_days : n]
    realized = resid[n - holdout_days : n] ** 2
    hv_fc = np.array([np.var(returns[i - 21 : i]) for i in idx])

    rv = returns ** 2
    har_beta = fit_har(rv[:-holdout_days])
    har_fc = np.array([har_one_step(rv[:i], har_beta) for i in idx])

    garch_mae = float(np.mean(np.abs(garch_fc - realized)))
    hv21_mae = float(np.mean(np.abs(hv_fc - realized)))
    har_mae = float(np.mean(np.abs(har_fc - realized)))
    lift = (hv21_mae - garch_mae) / hv21_mae if hv21_mae > 0 else 0.0
    maes = {"garch": garch_mae, "hv21": hv21_mae, "har": har_mae}
    primary = min(maes, key=maes.get)
    return WalkForward(garch_mae, hv21_mae, har_mae, lift, primary, holdout_days)
```

- [ ] **Step 4: Run to verify it passes** (and the existing evaluate tests still pass)

Run: `python -m pytest packages/ml/tests/test_evaluate.py -q`
Expected: PASS (4 passed). The pre-existing `test_walk_forward_prefers_garch_on_volatility_clustering` and `test_walk_forward_ties_or_baseline_on_iid` still pass (their assertions don't reference HAR).

- [ ] **Step 5: Commit**

```bash
git add packages/ml/saalr_ml/evaluate.py packages/ml/tests/test_evaluate.py
git commit -m "feat(ml): walk-forward scores and ranks HAR alongside GARCH/HV21"
```

---

### Task 3: Surface HAR in the `vol_forecast` payload

**Files:**
- Modify: `packages/ml/saalr_ml/forecast.py`
- Test: `packages/ml/tests/test_forecast.py`

- [ ] **Step 1: Write the failing test** — append to `packages/ml/tests/test_forecast.py`:

```python
def test_vol_forecast_includes_har_model_and_validation():
    r = simulate_garch(800, omega=0.05, alpha=0.10, beta=0.88, seed=9)
    closes = _closes_from_returns(r)
    out = vol_forecast(closes, horizon=8, holdout_days=60)
    assert out["primary_model"] in ("garch", "hv21", "har")
    assert "har_mae" in out["validation"]
    names = {out["primary_model"], *[a["model"] for a in out["alternative_models"]]}
    assert names == {"garch", "hv21", "har"}
    assert len(out["alternative_models"]) == 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest packages/ml/tests/test_forecast.py::test_vol_forecast_includes_har_model_and_validation -q`
Expected: FAIL — `har_mae` not in validation / only 1 alternative.

- [ ] **Step 3: Edit `packages/ml/saalr_ml/forecast.py`**

Add the import near the top (after the existing `from .garch import …`):
```python
from .har import har_rv_forecast
```

Replace everything from `hv_path = np.full(...)` through the `return {...}` with:
```python
    hv_path = np.full(horizon, hv21(returns))
    har_path = har_rv_forecast(returns, horizon)

    forecasts = {
        "garch": (_round_list(garch_path), garch_ci),
        "hv21": (_round_list(hv_path), None),
        "har": (har_path, None),
    }
    mae = {"garch": wf.garch_mae, "hv21": wf.hv21_mae, "har": wf.har_mae}
    primary = wf.primary

    def _alt(model: str) -> dict:
        if model == "hv21":
            status = "baseline"
        else:
            status = "underperforming_baseline" if mae[model] > wf.hv21_mae else "outperforms_baseline"
        return {
            "model": model,
            "forecast": forecasts[model][0],
            "status": status,
            "delta_mae_vs_baseline": round(float(mae[model] - wf.hv21_mae), 6),
        }

    alternatives = [_alt(m) for m in ("garch", "har", "hv21") if m != primary]

    return {
        "horizon_days": horizon,
        "primary_model": primary,
        "primary_forecast": forecasts[primary][0],
        "primary_ci_95": forecasts[primary][1],
        "alternative_models": alternatives,
        "validation": {
            "holdout_days": wf.holdout_days,
            "garch_mae": round(float(wf.garch_mae), 6),
            "hv21_mae": round(float(wf.hv21_mae), 6),
            "har_mae": round(float(wf.har_mae), 6),
            "lift": round(float(wf.lift), 6),
        },
        "model": "garch(1,1)",
        "iv_source": "realized_returns",
        "approximate": True,
        "params": {
            "omega": round(params.omega, 8),
            "alpha": round(params.alpha, 6),
            "beta": round(params.beta, 6),
        },
    }
```

- [ ] **Step 4: Run to verify it passes** (existing forecast tests too)

Run: `python -m pytest packages/ml/tests/test_forecast.py -q`
Expected: PASS (4 passed). The existing `test_vol_forecast_shape_and_honesty_fields` still holds: it now sees **2** alternatives — re-read it. **If that test asserts `len(alts) == 1`, update it** to:
```python
    alts = out["alternative_models"]
    assert len(alts) == 2 and out["primary_model"] not in [a["model"] for a in alts]
    if out["primary_model"] == "hv21":
        assert all(a["status"] == "underperforming_baseline" for a in alts if a["model"] != "hv21")
```
Commit that edit together with this task.

- [ ] **Step 5: Commit**

```bash
git add packages/ml/saalr_ml/forecast.py packages/ml/tests/test_forecast.py
git commit -m "feat(ml): vol_forecast surfaces HAR model + har_mae validation"
```

---

### Task 4: Frontend — show HAR in `ForecastPanel`

**Files:**
- Modify: `apps/web/src/lib/models.ts`
- Modify: `apps/web/src/features/models/ForecastPanel.tsx`
- Test: `apps/web/src/features/models/ForecastPanel.test.tsx`

- [ ] **Step 1: Update types in `apps/web/src/lib/models.ts`**

Change `VolForecastAlt.status` and `VolForecast` to:
```ts
export interface VolForecastAlt {
  model: string
  forecast: number[]
  status: 'baseline' | 'underperforming_baseline' | 'outperforms_baseline'
  delta_mae_vs_baseline: number
}

export interface VolForecast {
  horizon_days: number
  primary_model: 'garch' | 'hv21' | 'har'
  primary_forecast: number[]
  primary_ci_95: [number, number][] | null
  alternative_models: VolForecastAlt[]
  validation: { holdout_days: number; garch_mae: number; hv21_mae: number; har_mae: number; lift: number }
  model: string
  iv_source: string
  approximate: boolean
  params: { omega: number; alpha: number; beta: number }
}
```

- [ ] **Step 2: Write the failing test** — replace `apps/web/src/features/models/ForecastPanel.test.tsx` body's HAR coverage by adding this test (keep existing tests):

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ForecastPanel } from './ForecastPanel'
import type { VolForecast } from '../../lib/models'

const HAR_PRIMARY: VolForecast = {
  horizon_days: 5, primary_model: 'har', primary_forecast: [20, 21, 21, 22, 22], primary_ci_95: null,
  alternative_models: [
    { model: 'garch', forecast: [19, 20, 20, 21, 21], status: 'outperforms_baseline', delta_mae_vs_baseline: -0.1 },
    { model: 'hv21', forecast: [23, 23, 23, 23, 23], status: 'baseline', delta_mae_vs_baseline: 0 },
  ],
  validation: { holdout_days: 60, garch_mae: 0.4, hv21_mae: 0.5, har_mae: 0.3, lift: 0.2 },
  model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true,
  params: { omega: 0.0001, alpha: 0.1, beta: 0.85 },
}

describe('ForecastPanel HAR', () => {
  it('shows har as primary, both alternatives, and the har MAE row', () => {
    render(<ForecastPanel forecast={HAR_PRIMARY} />)
    expect(screen.getByTestId('forecast-primary')).toHaveTextContent('har')
    expect(screen.getAllByTestId('forecast-alt')).toHaveLength(2)
    expect(screen.getByText(/har MAE/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `pnpm -C apps/web test -- run src/features/models/ForecastPanel.test.tsx`
Expected: FAIL — only one `forecast-alt`, no `har MAE` row.

- [ ] **Step 4: Edit `apps/web/src/features/models/ForecastPanel.tsx`**

Replace the `const alt = forecast.alternative_models[0]` line and the closing `<dl>`/`{alt && …}` block. Specifically:

In the `<dl>` metrics grid, add a HAR MAE row after the `hv21 MAE` row:
```tsx
        <div className="flex justify-between"><dt>har MAE</dt><dd className="tnum">{forecast.validation.har_mae.toFixed(3)}</dd></div>
```

Replace the single-alt footer:
```tsx
      {alt && (
        <p className="mt-2 text-[11px] text-txtFaint" data-testid="forecast-alt">
          alt: {alt.model} ({alt.status.replace(/_/g, " ")})
        </p>
      )}
```
with a mapped list (and delete the now-unused `const alt = forecast.alternative_models[0]`):
```tsx
      {forecast.alternative_models.map((a) => (
        <p key={a.model} className="mt-2 text-[11px] text-txtFaint" data-testid="forecast-alt">
          alt: {a.model} ({a.status.replace(/_/g, " ")})
        </p>
      ))}
```

- [ ] **Step 5: Run to verify it passes**

Run: `pnpm -C apps/web test -- run src/features/models/ForecastPanel.test.tsx`
Expected: PASS (existing + new).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/models.ts apps/web/src/features/models/ForecastPanel.tsx apps/web/src/features/models/ForecastPanel.test.tsx
git commit -m "feat(web): ForecastPanel shows HAR primary/alternatives + har MAE"
```

---

### Task 5: Integration — vol-forecast response includes HAR

**Files:**
- Modify: `tests/integration/test_vol_forecast.py`

- [ ] **Step 1: Write the failing test** — append to `tests/integration/test_vol_forecast.py`:

```python
async def test_vol_forecast_includes_har(app_sessionmaker, admin_engine):
    email = "vf-har@x.com"
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": f"Bearer dev:{email}"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/vol-forecast?ticker=AAPL&horizon=10", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            names = {body["primary_model"], *[a["model"] for a in body["alternative_models"]]}
            assert names == {"garch", "hv21", "har"}
            assert "har_mae" in body["validation"]
            assert len(body["alternative_models"]) == 2
```

Also update `test_vol_forecast_pro_returns_both_models_and_persists_validation`: change `assert len(body["alternative_models"]) == 1` to `assert len(body["alternative_models"]) == 2`.

- [ ] **Step 2: Run to verify it fails first, then passes**

Run (Docker DB/Redis up):
```
APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" python -m pytest tests/integration/test_vol_forecast.py -q
```
Expected: the new test + the updated assertion PASS (no API code change needed — HAR rides the existing endpoint). If a stale Redis cache returns 1 alternative, it is keyed `mdq:volfc:v1:US:AAPL:10`; the test uses a fresh seed each run, but if needed flush with `docker exec docker-redis-1 redis-cli FLUSHALL`.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_vol_forecast.py
git commit -m "test(forecast): vol-forecast integration asserts HAR present"
```

**Checkpoint:** Part 1 complete — HAR-RV ships independently. Run the full ml suite + the vol integration test once more before moving on.

---

# Part 2 — ARIMA + LSTM price forecast (Feature A, adds statsmodels + torch)

### Task 6: Add `statsmodels` + `torch` dependencies

**Files:**
- Modify: `packages/ml/pyproject.toml`

- [ ] **Step 1: Edit `packages/ml/pyproject.toml`** — extend `dependencies`:
```toml
dependencies = [
  "saalr-core",
  "numpy>=1.26",
  "scipy>=1.11",
  "statsmodels>=0.14",
  "torch>=2.2",
]
```

- [ ] **Step 2: Lock + sync** (use `uv lock`, NOT `uv pip install`, per repo rule)

Run:
```
uv lock
uv sync
```
Expected: resolves and installs statsmodels + torch (CPU). On Windows this pulls a large torch wheel — allow time.

- [ ] **Step 3: Smoke-import**

Run: `python -c "import torch, statsmodels.api as sm; print(torch.__version__, sm.__version__)"`
Expected: prints versions, no error.

- [ ] **Step 4: Commit** (commit the `uv.lock` produced by `uv lock` — that is allowed; do NOT commit a lock produced by `uv pip install`)

```bash
git add packages/ml/pyproject.toml uv.lock
git commit -m "build(ml): add statsmodels + torch for price forecasting"
```

---

### Task 7: `saalr_ml/arima.py` — ARIMA price forecaster

**Files:**
- Create: `packages/ml/saalr_ml/arima.py`
- Test: `packages/ml/tests/test_arima.py`

- [ ] **Step 1: Write the failing test** — `packages/ml/tests/test_arima.py`:
```python
import numpy as np

from saalr_ml.arima import arima_forecast


def test_arima_forecast_shape_and_band():
    rng = np.random.default_rng(0)
    # log-price as a random walk with mild drift
    log_closes = np.cumsum(rng.standard_normal(300) * 0.01 + 0.0003) + np.log(100)
    path, ci, order = arima_forecast(log_closes, horizon=10)
    assert len(path) == 10 and len(ci) == 10
    assert all(np.isfinite(p) and p > 0 for p in path)
    for lo, hi in ci:
        assert lo <= hi
    assert len(order) == 3
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest packages/ml/tests/test_arima.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `packages/ml/saalr_ml/arima.py`**
```python
from __future__ import annotations

import warnings

import numpy as np

_ORDERS = [(p, d, q) for p in (0, 1, 2) for d in (0, 1) for q in (0, 1, 2)]


def arima_forecast(log_closes, horizon: int) -> tuple[list[float], list[list[float]], tuple]:
    """Fit ARIMA on log-price (AIC over a small grid) and forecast a PRICE path with a 95%
    prediction band. Returns (price_path, ci95_price, order)."""
    from statsmodels.tsa.arima.model import ARIMA

    y = np.asarray(log_closes, dtype=float)
    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for order in _ORDERS:
            try:
                res = ARIMA(y, order=order).fit()
            except Exception:  # noqa: BLE001 - skip non-converging orders
                continue
            if np.isfinite(res.aic) and (best is None or res.aic < best[0]):
                best = (res.aic, order, res)
    if best is None:
        raise ValueError("ARIMA failed to fit")
    _, order, res = best
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fc = res.get_forecast(steps=horizon)
        mean_log = np.asarray(fc.predicted_mean, dtype=float)
        ci_log = np.asarray(fc.conf_int(alpha=0.05), dtype=float)  # (horizon, 2)
    path = np.exp(mean_log)
    ci = np.exp(ci_log)
    return (
        [round(float(x), 4) for x in path],
        [[round(float(lo), 4), round(float(hi), 4)] for lo, hi in ci],
        tuple(int(v) for v in order),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest packages/ml/tests/test_arima.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add packages/ml/saalr_ml/arima.py packages/ml/tests/test_arima.py
git commit -m "feat(ml): ARIMA price forecaster (statsmodels, AIC grid)"
```

---

### Task 8: `saalr_ml/lstm.py` — seeded LSTM price forecaster

**Files:**
- Create: `packages/ml/saalr_ml/lstm.py`
- Test: `packages/ml/tests/test_lstm.py`

- [ ] **Step 1: Write the failing test** — `packages/ml/tests/test_lstm.py`:
```python
import numpy as np

from saalr_ml.lstm import lstm_forecast


def _returns(n=320, seed=0):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(n) * 0.01 + 0.0002  # raw log-returns


def test_lstm_forecast_shape_and_band():
    r = _returns()
    path, ci = lstm_forecast(r, horizon=10, last_close=100.0, seed=0, epochs=5)
    assert len(path) == 10 and len(ci) == 10
    assert all(np.isfinite(p) and p > 0 for p in path)
    for lo, hi in ci:
        assert lo <= hi


def test_lstm_forecast_is_deterministic():
    r = _returns()
    a, _ = lstm_forecast(r, horizon=6, last_close=100.0, seed=0, epochs=5)
    b, _ = lstm_forecast(r, horizon=6, last_close=100.0, seed=0, epochs=5)
    assert a == b
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest packages/ml/tests/test_lstm.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `packages/ml/saalr_ml/lstm.py`**
```python
from __future__ import annotations

import numpy as np


def lstm_forecast(
    returns, horizon: int, last_close: float, *, seed: int = 0,
    epochs: int = 150, lookback: int = 20, hidden: int = 16,
) -> tuple[list[float], list[list[float]]]:
    """Train a small, seeded LSTM on standardized log-returns; iteratively forecast `horizon`
    returns and compound from `last_close` into a PRICE path. Returns (price_path, ci95_price).
    `returns` must be RAW log-returns (not ×100)."""
    import torch
    from torch import nn

    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.set_num_threads(1)

    r = np.asarray(returns, dtype=float)
    mu, sd = float(r.mean()), float(r.std() or 1.0)
    z = (r - mu) / sd

    xs, ys = [], []
    for i in range(len(z) - lookback):
        xs.append(z[i : i + lookback])
        ys.append(z[i + lookback])
    if not xs:
        raise ValueError("series too short for the LSTM lookback")
    xt = torch.tensor(np.array(xs), dtype=torch.float32).unsqueeze(-1)  # (N, L, 1)
    yt = torch.tensor(np.array(ys), dtype=torch.float32).unsqueeze(-1)  # (N, 1)

    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(input_size=1, hidden_size=hidden, batch_first=True)
            self.fc = nn.Linear(hidden, 1)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :])

    net = Net()
    opt = torch.optim.Adam(net.parameters(), lr=0.01)
    loss_fn = nn.MSELoss()
    net.train()
    for _ in range(epochs):
        opt.zero_grad()
        loss = loss_fn(net(xt), yt)
        loss.backward()
        opt.step()

    net.eval()
    with torch.no_grad():
        resid = (yt - net(xt)).squeeze(-1).numpy()
        resid_sd = float(resid.std() or 1.0)
        window = torch.tensor(z[-lookback:], dtype=torch.float32).reshape(1, lookback, 1)
        preds_z = []
        for _ in range(horizon):
            nxt = float(net(window).item())
            preds_z.append(nxt)
            window = torch.cat(
                [window[:, 1:, :], torch.tensor([[[nxt]]], dtype=torch.float32)], dim=1
            )

    preds_r = np.array(preds_z) * sd + mu     # de-standardize to raw log-returns
    cum = np.cumsum(preds_r)
    path = last_close * np.exp(cum)
    band = 1.96 * resid_sd * sd * np.sqrt(np.arange(1, horizon + 1))  # widening band
    lo = last_close * np.exp(cum - band)
    hi = last_close * np.exp(cum + band)
    return (
        [round(float(x), 4) for x in path],
        [[round(float(a), 4), round(float(b), 4)] for a, b in zip(lo, hi)],
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest packages/ml/tests/test_lstm.py -q`
Expected: PASS (determinism holds with fixed seed + single thread).

- [ ] **Step 5: Commit**
```bash
git add packages/ml/saalr_ml/lstm.py packages/ml/tests/test_lstm.py
git commit -m "feat(ml): seeded LSTM price forecaster (torch)"
```

---

### Task 9: `saalr_ml/price_forecast.py` — orchestrator + multi-origin walk-forward

**Files:**
- Create: `packages/ml/saalr_ml/price_forecast.py`
- Test: `packages/ml/tests/test_price_forecast.py`

- [ ] **Step 1: Write the failing test** — `packages/ml/tests/test_price_forecast.py`:
```python
import numpy as np
import pytest

from saalr_ml.price_forecast import price_forecast


def _closes(n=300, seed=0):
    rng = np.random.default_rng(seed)
    rets = rng.standard_normal(n) * 0.01 + 0.0003
    return 100.0 * np.exp(np.cumsum(rets))


def test_price_forecast_shape_and_models():
    out = price_forecast(_closes(), horizon=5, holdout_days=30, n_origins=2, lstm_epochs=5)
    assert out["horizon_days"] == 5
    assert out["primary_model"] in ("arima", "lstm", "naive")
    by = {m["model"]: m for m in out["models"]}
    assert set(by) == {"arima", "lstm", "naive"}
    for m in by.values():
        assert len(m["path"]) == 5
        assert m["direction"] in ("up", "down", "flat")
        assert 0.0 <= m["directional_accuracy"] <= 1.0
    assert by["naive"]["ci_95"] is None
    assert out["validation"]["n_origins"] == 2
    assert out["approximate"] is True and out["disclaimer"]


def test_price_forecast_primary_is_lowest_mae():
    out = price_forecast(_closes(seed=3), horizon=5, holdout_days=30, n_origins=2, lstm_epochs=5)
    maes = {m["model"]: m["holdout_mae"] for m in out["models"]}
    assert out["primary_model"] == min(maes, key=maes.get)


def test_price_forecast_rejects_short_history():
    with pytest.raises(ValueError, match="insufficient history"):
        price_forecast(_closes(n=100), horizon=5)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest packages/ml/tests/test_price_forecast.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `packages/ml/saalr_ml/price_forecast.py`**
```python
from __future__ import annotations

import numpy as np

from .arima import arima_forecast
from .lstm import lstm_forecast

_MIN_HISTORY = 250


def _naive_path(last_close: float, drift: float, horizon: int) -> np.ndarray:
    steps = np.arange(1, horizon + 1)
    return last_close * np.exp(drift * steps)


def _direction(expected_return_pct: float) -> str:
    if expected_return_pct > 0.5:
        return "up"
    if expected_return_pct < -0.5:
        return "down"
    return "flat"


def _origins(n: int, horizon: int, holdout_days: int, n_origins: int) -> list[int]:
    last = n - horizon - 1
    first = max(_MIN_HISTORY - 1, n - holdout_days)
    if last <= first:
        return [last] if last > 0 else []
    raw = np.linspace(first, last, n_origins, dtype=int)
    return sorted({int(o) for o in raw if o > 0})


def _walk_forward_multi(closes, horizon, holdout_days, n_origins, seed, lstm_epochs):
    closes = np.asarray(closes, dtype=float)
    agg = {m: {"errs": [], "dirs": []} for m in ("arima", "lstm", "naive")}
    for o in _origins(len(closes), horizon, holdout_days, n_origins):
        hist = closes[: o + 1]
        actual = closes[o + 1 : o + 1 + horizon]
        h = len(actual)
        if h == 0:
            continue
        log_hist = np.log(hist)
        rets = np.diff(log_hist)
        lc = float(hist[-1])
        preds = {
            "arima": np.asarray(arima_forecast(log_hist, h)[0], dtype=float),
            "lstm": np.asarray(lstm_forecast(rets, h, lc, seed=seed, epochs=lstm_epochs)[0], dtype=float),
            "naive": np.asarray(_naive_path(lc, float(rets.mean()), h), dtype=float),
        }
        for m, pth in preds.items():
            agg[m]["errs"].append(np.abs(pth - actual))
            agg[m]["dirs"].append(1.0 if np.sign(pth[-1] - lc) == np.sign(actual[-1] - lc) else 0.0)
    out = {}
    for m, a in agg.items():
        errs = np.concatenate(a["errs"]) if a["errs"] else np.array([0.0])
        out[m] = {"mae": float(np.mean(errs)), "dir_acc": float(np.mean(a["dirs"] or [0.0]))}
    return out


def price_forecast(closes, horizon: int, holdout_days: int = 60, n_origins: int = 5,
                   seed: int = 0, lstm_epochs: int = 150) -> dict:
    """ARIMA + LSTM + naive price-path forecast with multi-origin walk-forward validation.
    Raises ValueError on < 250 closes."""
    closes = np.asarray(closes, dtype=float)
    if len(closes) < _MIN_HISTORY:
        raise ValueError("insufficient history")
    log_closes = np.log(closes)
    returns = np.diff(log_closes)
    last_close = float(closes[-1])
    drift = float(returns.mean())

    arima_path, arima_ci, _order = arima_forecast(log_closes, horizon)
    lstm_path, lstm_ci = lstm_forecast(returns, horizon, last_close, seed=seed, epochs=lstm_epochs)
    naive_path = [round(float(x), 4) for x in _naive_path(last_close, drift, horizon)]
    paths = {"arima": (arima_path, arima_ci), "lstm": (lstm_path, lstm_ci), "naive": (naive_path, None)}

    scores = _walk_forward_multi(closes, horizon, holdout_days, n_origins, seed, lstm_epochs)
    primary = min(scores, key=lambda m: scores[m]["mae"])

    models = []
    for m in ("arima", "lstm", "naive"):
        path, ci = paths[m]
        exp_ret = round((path[-1] / last_close - 1.0) * 100.0, 4)
        models.append({
            "model": m, "path": path, "ci_95": ci,
            "expected_return_pct": exp_ret, "direction": _direction(exp_ret),
            "holdout_mae": round(scores[m]["mae"], 6),
            "directional_accuracy": round(scores[m]["dir_acc"], 4),
        })
    return {
        "horizon_days": horizon,
        "last_close": round(last_close, 4),
        "primary_model": primary,
        "models": models,
        "validation": {"holdout_days": holdout_days, "n_origins": n_origins, "best_model": primary},
        "approximate": True,
        "disclaimer": "Educational. Daily price direction is near-random; the naive baseline often wins.",
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest packages/ml/tests/test_price_forecast.py -q`
Expected: PASS (3 passed). Note: `n_origins` may collapse to fewer effective origins on short series — `validation.n_origins` echoes the requested value, which is what the test checks.

- [ ] **Step 5: Commit**
```bash
git add packages/ml/saalr_ml/price_forecast.py packages/ml/tests/test_price_forecast.py
git commit -m "feat(ml): price_forecast orchestrator + multi-origin walk-forward"
```

---

### Task 10: API — `price_service.py` + `/v1/market/price-forecast` route

**Files:**
- Create: `apps/api/saalr_api/forecast/price_service.py`
- Modify: `apps/api/saalr_api/forecast/router.py`

- [ ] **Step 1: Implement `apps/api/saalr_api/forecast/price_service.py`**
```python
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import numpy as np

from saalr_ml.price_forecast import price_forecast

from . import repo


async def get_or_compute_price_forecast(
    redis, sessionmaker, session, ticker: str, market: str, horizon: int, ttl: int,
    *, closes: list[float] | None = None,
) -> dict:
    """Redis-cached ARIMA+LSTM+naive price forecast. Heavy training runs in a worker thread so it
    never blocks the event loop; persists per-model validation rows; raises ValueError on
    < 250 closes (the caller maps it to 422)."""
    key = f"mdq:pricefc:v1:{market}:{ticker}:{horizon}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    if closes is None:
        closes = await repo.load_closes(session, ticker, market)
    result = await asyncio.to_thread(price_forecast, np.asarray(closes, dtype=float), horizon)

    payload = {
        "ticker": ticker, "market": market,
        "as_of": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    mae = {m["model"]: m["holdout_mae"] for m in result["models"]}
    async with sessionmaker() as vsession, vsession.begin():
        for model_name in ("arima", "lstm"):
            await repo.record_validation(
                vsession,
                model_name=model_name,
                market=market,
                cohort_label=f"{ticker}:{repo.today_str()}",
                baseline_name="naive",
                status="passed" if result["primary_model"] == model_name else "failed",
                metric_summary_json={"holdout_mae": mae[model_name],
                                     "n_origins": result["validation"]["n_origins"]},
            )
    await redis.set(key, json.dumps(payload), ex=ttl)
    return payload
```

- [ ] **Step 2: Edit `apps/api/saalr_api/forecast/router.py`** — add a new endpoint after the existing `vol_forecast_endpoint` (reuse the module-level `_validate`):
```python
@router.get("/price-forecast")
async def price_forecast_endpoint(
    request: Request,
    ticker: str = Query(...),
    market: str = Query("US"),
    horizon: int = Query(10, ge=1, le=30),
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    _validate(ticker, market)
    ticker = ticker.upper()
    session, _principal = ctx
    from . import price_service

    try:
        return await price_service.get_or_compute_price_forecast(
            request.app.state.redis,
            request.app.state.sessionmaker,
            session,
            ticker,
            market,
            horizon,
            request.app.state.vol_forecast_ttl,
        )
    except ValueError as exc:
        raise HTTPException(
            422, {"error": {"code": "INSUFFICIENT_HISTORY", "message": str(exc)}}
        ) from exc
```

- [ ] **Step 3: Sanity check imports compile**

Run: `python -c "import saalr_api.forecast.price_service, saalr_api.forecast.router"`
Expected: no error. (Full endpoint behavior is covered by Task 12's integration test.)

- [ ] **Step 4: Commit**
```bash
git add apps/api/saalr_api/forecast/price_service.py apps/api/saalr_api/forecast/router.py
git commit -m "feat(api): /v1/market/price-forecast (ARIMA+LSTM+naive, cached, gated)"
```

---

### Task 11: Frontend — `PriceForecastPanel` + wiring into Models

**Files:**
- Modify: `apps/web/src/lib/models.ts`
- Modify: `apps/web/src/features/models/hooks.ts`
- Create: `apps/web/src/features/models/PriceForecastPanel.tsx`
- Create: `apps/web/src/features/models/PriceForecastPanel.test.tsx`
- Modify: `apps/web/src/pages/Models.tsx`

- [ ] **Step 1: Add types + fetch to `apps/web/src/lib/models.ts`** (after the `VolForecast` block):
```ts
export interface PriceModel {
  model: 'arima' | 'lstm' | 'naive'
  path: number[]
  ci_95: [number, number][] | null
  expected_return_pct: number
  direction: 'up' | 'down' | 'flat'
  holdout_mae: number
  directional_accuracy: number
}

export interface PriceForecast {
  ticker: string
  market: string
  as_of: string
  horizon_days: number
  last_close: number
  primary_model: 'arima' | 'lstm' | 'naive'
  models: PriceModel[]
  validation: { holdout_days: number; n_origins: number; best_model: string }
  approximate: boolean
  disclaimer: string
}

export function getPriceForecast(ticker: string, horizon: number): Promise<PriceForecast> {
  return request(`/v1/market/price-forecast?ticker=${encodeURIComponent(ticker)}&market=US&horizon=${horizon}`)
}
```

- [ ] **Step 2: Add the hook to `apps/web/src/features/models/hooks.ts`**

Extend the import and add the hook:
```ts
import { getVolForecast, getSentiment, getPriceForecast, runMonteCarlo, type MonteCarloRequest } from '../../lib/models'

export function usePriceForecast(ticker: string, horizon: number, enabled: boolean) {
  return useQuery({
    queryKey: ['price-forecast', ticker, horizon],
    queryFn: () => getPriceForecast(ticker, horizon),
    enabled: enabled && !!ticker,
    retry: false,
  })
}
```

- [ ] **Step 3: Write the failing panel test** — `apps/web/src/features/models/PriceForecastPanel.test.tsx`:
```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PriceForecastPanel } from './PriceForecastPanel'
import type { PriceForecast } from '../../lib/models'

const FC: PriceForecast = {
  ticker: 'AAPL', market: 'US', as_of: '2026-06-06T00:00:00Z',
  horizon_days: 5, last_close: 100, primary_model: 'naive',
  models: [
    { model: 'arima', path: [101, 102, 102, 103, 103], ci_95: [[99, 103], [98, 106], [98, 107], [97, 109], [96, 110]],
      expected_return_pct: 3, direction: 'up', holdout_mae: 2.1, directional_accuracy: 0.55 },
    { model: 'lstm', path: [100, 99, 99, 98, 98], ci_95: [[98, 102], [96, 102], [95, 103], [94, 103], [93, 103]],
      expected_return_pct: -2, direction: 'down', holdout_mae: 2.6, directional_accuracy: 0.5 },
    { model: 'naive', path: [100.1, 100.2, 100.3, 100.4, 100.5], ci_95: null,
      expected_return_pct: 0.5, direction: 'flat', holdout_mae: 1.9, directional_accuracy: 0.52 },
  ],
  validation: { holdout_days: 60, n_origins: 5, best_model: 'naive' },
  approximate: true, disclaimer: 'Educational. Daily price direction is near-random; the naive baseline often wins.',
}

describe('PriceForecastPanel', () => {
  it('renders a line per model, axes, the primary badge and disclaimer', () => {
    render(<PriceForecastPanel forecast={FC} />)
    expect(screen.getByTestId('price-forecast-panel')).toBeInTheDocument()
    expect(screen.getAllByTestId('pf-line')).toHaveLength(3)
    expect(screen.getByTestId('pf-primary')).toHaveTextContent('naive')
    expect(screen.getByTestId('pf-axis-x')).toBeInTheDocument()
    expect(screen.getByTestId('pf-axis-y')).toBeInTheDocument()
    expect(screen.getByTestId('pf-disclaimer')).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Run to verify it fails**

Run: `pnpm -C apps/web test -- run src/features/models/PriceForecastPanel.test.tsx`
Expected: FAIL — component missing.

- [ ] **Step 5: Implement `apps/web/src/features/models/PriceForecastPanel.tsx`**
```tsx
import type { PriceForecast, PriceModel } from '../../lib/models'

const W = 380
const H = 200
const PAD = { l: 40, r: 12, t: 14, b: 28 }

const COLOR: Record<PriceModel['model'], string> = {
  arima: '#4da3ff',
  lstm: '#c084fc',
  naive: '#9aa4b2',
}

export function PriceForecastPanel({ forecast }: { forecast: PriceForecast }) {
  const { models, last_close, horizon_days, primary_model } = forecast
  const n = horizon_days
  const allY = [
    last_close,
    ...models.flatMap((m) => m.path),
    ...models.flatMap((m) => (m.ci_95 ? m.ci_95.flat() : [])),
  ]
  const yMin = Math.min(...allY)
  const yMax = Math.max(...allY)
  const ySpan = yMax - yMin || 1
  const sx = (i: number) => PAD.l + (W - PAD.l - PAD.r) * (i / Math.max(1, n))
  const sy = (v: number) => H - PAD.b - (H - PAD.t - PAD.b) * ((v - yMin) / ySpan)

  const primary = models.find((m) => m.model === primary_model)
  const yTicks = [yMin, (yMin + yMax) / 2, yMax]

  return (
    <figure className="rounded-lg border border-line bg-panel p-4" data-testid="price-forecast-panel">
      <figcaption className="mb-2 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
        Price forecast · {horizon_days}d
        <span data-testid="pf-primary" className="rounded bg-accent/20 px-1.5 py-0.5 text-accent">{primary_model} wins backtest</span>
        {forecast.approximate && <span className="rounded border border-line px-1.5 py-0.5 text-txtFaint">approximate</span>}
      </figcaption>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <g fontFamily="monospace" fontSize={8.5}>
          <line data-testid="pf-axis-y" x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} stroke="#2c3340" />
          <line data-testid="pf-axis-x" x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} stroke="#2c3340" />
          {yTicks.map((v, i) => (
            <g key={i}>
              <line x1={PAD.l - 3} y1={sy(v)} x2={PAD.l} y2={sy(v)} stroke="#2c3340" />
              <text x={PAD.l - 5} y={sy(v) + 3} textAnchor="end" fill="#5b6472">{v.toFixed(0)}</text>
            </g>
          ))}
          <text x={PAD.l} y={H - 1} textAnchor="start" fill="#5b6472">today</text>
          <text x={W - PAD.r} y={H - 1} textAnchor="end" fill="#5b6472">+{n}d</text>
          <text x={4} y={PAD.t - 4} textAnchor="start" fill="#5b6472">price</text>
        </g>

        {/* primary CI band */}
        {primary?.ci_95 && (
          <polygon
            data-testid="pf-band"
            points={[
              `${sx(0).toFixed(1)},${sy(last_close).toFixed(1)}`,
              ...primary.ci_95.map((p, i) => `${sx(i + 1).toFixed(1)},${sy(p[1]).toFixed(1)}`),
              ...primary.ci_95.map((p, i) => `${sx(i + 1).toFixed(1)},${sy(p[0]).toFixed(1)}`).reverse(),
            ].join(' ')}
            fill="#4da3ff18"
            stroke="none"
          />
        )}

        {/* one polyline per model, anchored at today's close */}
        {models.map((m) => (
          <polyline
            key={m.model}
            data-testid="pf-line"
            points={[`${sx(0).toFixed(1)},${sy(last_close).toFixed(1)}`,
              ...m.path.map((v, i) => `${sx(i + 1).toFixed(1)},${sy(v).toFixed(1)}`)].join(' ')}
            fill="none"
            stroke={COLOR[m.model]}
            strokeWidth={m.model === primary_model ? 2.2 : 1.3}
            strokeDasharray={m.model === 'naive' ? '3 3' : undefined}
          />
        ))}
      </svg>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px]">
        {models.map((m) => (
          <span key={m.model} className="flex items-center gap-1" style={{ color: COLOR[m.model] }}>
            <span style={{ background: COLOR[m.model] }} className="inline-block h-2 w-2 rounded-sm" />
            {m.model} {m.expected_return_pct >= 0 ? '+' : ''}{m.expected_return_pct.toFixed(1)}%
          </span>
        ))}
      </div>

      <p className="mt-2 text-[11px] text-txtFaint" data-testid="pf-disclaimer">{forecast.disclaimer}</p>

      <dl className="mt-2 grid grid-cols-3 gap-x-4 gap-y-1 font-mono text-[10px] text-txtDim">
        {models.map((m) => (
          <div key={m.model} className="flex justify-between">
            <dt>{m.model} MAE</dt>
            <dd className="tnum">{m.holdout_mae.toFixed(2)} · {(m.directional_accuracy * 100).toFixed(0)}%</dd>
          </div>
        ))}
      </dl>
    </figure>
  )
}
```

- [ ] **Step 6: Run to verify it passes**

Run: `pnpm -C apps/web test -- run src/features/models/PriceForecastPanel.test.tsx`
Expected: PASS.

- [ ] **Step 7: Wire into `apps/web/src/pages/Models.tsx`**

Add imports:
```tsx
import { PriceForecastPanel } from '../features/models/PriceForecastPanel'
```
Extend the hooks line near `useVolForecast`:
```tsx
  const priceQ = usePriceForecast(entitled ? ticker : '', horizon, entitled)
```
(and add `usePriceForecast` to the existing `import { useVolForecast, useSentiment, useMonteCarlo } from '../features/models/hooks'` line.)

In the Insights tab, render the panel under the forecast/sentiment grid (after the closing `</div>` of the `grid` block, still inside `tab === 'insights'`):
```tsx
          {priceQ.data && <PriceForecastPanel forecast={priceQ.data} />}
          {priceQ.isLoading && ticker && (
            <div className="animate-pulse rounded-lg border border-line bg-panel2 py-16" data-testid="price-loading" />
          )}
```
Note: `priceQ.error instanceof EntitlementError` is already covered by the existing top-level `ModelsGate` guard pattern — extend that `if (… instanceof EntitlementError)` condition to also include `priceQ.error`.

- [ ] **Step 8: Run web typecheck + the models page tests**

Run: `pnpm -C apps/web test -- run src/features/models src/pages/Models` then `pnpm -C apps/web typecheck` (or the repo's `pretypecheck`/`build` script).
Expected: PASS / no type errors.

- [ ] **Step 9: Commit**
```bash
git add apps/web/src/lib/models.ts apps/web/src/features/models/hooks.ts apps/web/src/features/models/PriceForecastPanel.tsx apps/web/src/features/models/PriceForecastPanel.test.tsx apps/web/src/pages/Models.tsx
git commit -m "feat(web): Price forecast panel (ARIMA/LSTM/naive overlay) on Models"
```

---

### Task 12: Integration — `/v1/market/price-forecast`

**Files:**
- Create: `tests/integration/test_price_forecast.py`

- [ ] **Step 1: Write the test** — `tests/integration/test_price_forecast.py` (reuses the seeding pattern from `test_vol_forecast.py`):
```python
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, n=300):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    px = 100.0
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol = :s"), {"s": symbol})
        for i in range(n):
            step = math.sin(i * 0.3) * 0.01 + (0.0005 if i % 2 else -0.0004)
            px = max(1.0, px * (1 + step))
            ts = start + timedelta(days=i)
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""),
                {"ts": ts, "sym": symbol, "o": Decimal(str(round(px, 4))),
                 "h": Decimal(str(round(px + 1, 4))), "l": Decimal(str(round(px - 1, 4))),
                 "c": Decimal(str(round(px, 4))), "v": 1000},
            )


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tenant_id})


async def test_price_forecast_pro_returns_all_models(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pf-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/price-forecast?ticker=AAPL&horizon=5", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["horizon_days"] == 5 and body["primary_model"] in ("arima", "lstm", "naive")
            names = {m["model"] for m in body["models"]}
            assert names == {"arima", "lstm", "naive"}
            assert all(len(m["path"]) == 5 for m in body["models"])
            # cache hit: a second call returns identical payload
            again = await c.get("/v1/market/price-forecast?ticker=AAPL&horizon=5", headers=h)
            assert again.json() == body


async def test_price_forecast_free_tier_is_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pf-free@x.com"}
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/price-forecast?ticker=AAPL&horizon=5", headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO"


async def test_price_forecast_insufficient_history_is_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pf-short@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "TINY", n=100)
            r = await c.get("/v1/market/price-forecast?ticker=TINY&horizon=5", headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "INSUFFICIENT_HISTORY"
```

- [ ] **Step 2: Run the test** (Docker DB/Redis up; flush Redis first to avoid a stale key):
```
docker exec docker-redis-1 redis-cli FLUSHALL
APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" python -m pytest tests/integration/test_price_forecast.py -q
```
Expected: PASS (3 passed). The default `horizon=5` uses the live endpoint's default `n_origins=5`/`lstm_epochs=150`; the first cold call trains the LSTM a few times — allow a few seconds.

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_price_forecast.py
git commit -m "test(forecast): price-forecast integration (gating, models, cache, 422)"
```

---

## Final verification (after all tasks)

- [ ] `python -m pytest packages/ml/tests -q` — all ml unit tests pass.
- [ ] Vol + price integration: `python -m pytest tests/integration/test_vol_forecast.py tests/integration/test_price_forecast.py tests/integration/test_auth.py -q` (with the env vars above) — pass.
- [ ] `pnpm -C apps/web test -- run src/features/models` — pass; `pnpm -C apps/web typecheck` — clean.
- [ ] Dispatch a final code-reviewer over the whole diff.
- [ ] Then superpowers:finishing-a-development-branch (do NOT push until the user asks).

## Self-review notes (plan author)

- **Spec coverage:** Feature B → Tasks 1–5; Feature A → Tasks 6–12; parked work is documentation-only (no tasks, by design). ✅
- **Type consistency:** `WalkForward.har_mae` (Task 2) used in `forecast.py` (Task 3); `VolForecast.primary_model` union gains `'har'` + `har_mae` (Task 4) matches the payload (Task 3); `PriceForecast`/`PriceModel` (Task 11) match the orchestrator dict (Task 9) and `price_service` payload (Task 10). `lstm_epochs` threads from `price_forecast` → `lstm_forecast` (Tasks 8–9). ✅
- **Honesty:** naive overlay + multi-origin walk-forward + directional accuracy + `approximate`/`disclaimer` retained. ✅
