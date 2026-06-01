# GARCH volatility forecast (ML slice A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `GET /v1/market/vol-forecast` — a hand-rolled GARCH(1,1) volatility forecast always reported alongside the HV21 baseline, with a request-time walk-forward holdout honestly choosing the `primary` model, gated by `ml_forecast`, cached in Redis, and persisted to `model_validation_runs`.

**Architecture:** A new isolated `saalr-ml` workspace package (numpy + scipy) holds the pure math; a new `apps/api/saalr_api/forecast/` feature serves the endpoint synchronously, loading daily `bars` and writing a validation row.

**Tech Stack:** Python 3.12, numpy, scipy, FastAPI, SQLAlchemy 2.0 async, redis.asyncio, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-05-31-garch-vol-forecast-design.md`

**Conventions / facts (verified):**
- `from __future__ import annotations` at the top of every module.
- The root workspace globs `packages/*`, so `saalr-ml` auto-registers. `saalr-api` (a root dep) will depend on `saalr-ml`, so `saalr-ml` installs editable in the root env → both `packages/ml/tests` and the API integration tests run under a plain `uv run pytest` (Redis on 6379, DB env to 55432).
- `model_validation_runs` is **non-RLS** and `saalr_app` already has INSERT/SELECT on it (0001 line 290 grants `ON ALL TABLES`; it is NOT in the RLS `TENANT_SCOPED` set). No grant migration needed. ORM model `saalr_core.db.models.trading.ModelValidationRun`: `validation_id` (PK, default `new_id`), `model_name`, `market` (CHAR(2)), `cohort_label`, `baseline_name`, `status` (CHECK in `running|passed|failed`), `metric_summary_json` (JSONB, NOT NULL), `report_uri` (nullable), `started_at` (server default now), `completed_at` (nullable).
- Entitlement gate pattern: `apps/api/saalr_api/market/gating.py::require_vol_surface` (402 if `not entitlements_for(tier)["vol_surface"]`). `ml_forecast` is an existing entitlement (free=False, pro/premium=True).
- Redis cache pattern: `key`; `cached = await redis.get(key)`; `json.loads`; else compute, `await redis.set(key, json.dumps(payload), ex=ttl)`. App state: `request.app.state.redis`, `.sessionmaker`; `get_principal` yields `(session, principal)` (RLS session; fine to INSERT into the non-RLS validation table on it).
- `bars` columns: `ts` (TIMESTAMPTZ), `symbol`, `market`, `interval` ('1d'), `open/high/low/close` (NUMERIC), `volume`. Bind a Python `date` against `ts::date` (asyncpg-safe, as the backtest worker does).
- `saalr_core.ids.new_id()` returns a UUID.

---

## Task 1: `saalr-ml` package + GARCH core (`garch.py`)

**Files:**
- Create: `packages/ml/pyproject.toml`
- Create: `packages/ml/saalr_ml/__init__.py` (empty)
- Create: `packages/ml/saalr_ml/garch.py`
- Test: `packages/ml/tests/test_garch.py`

- [ ] **Step 1: Create the package manifest**

```toml
# packages/ml/pyproject.toml
[project]
name = "saalr-ml"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "saalr-core",
  "numpy>=1.26",
  "scipy>=1.11",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["saalr_ml"]

[tool.uv.sources]
saalr-core = { workspace = true }
```

- [ ] **Step 2: Write the failing test**

```python
# packages/ml/tests/test_garch.py
import numpy as np

from saalr_ml.garch import (
    GarchParams,
    conditional_variance,
    fit_garch11,
    forecast_var,
    simulate_ci,
)


def _simulate_garch(n, omega, alpha, beta, mu=0.0, seed=7):
    rng = np.random.default_rng(seed)
    r = np.empty(n)
    sigma2 = omega / (1 - alpha - beta)
    resid_prev2 = sigma2
    for t in range(n):
        sigma2 = omega + alpha * resid_prev2 + beta * sigma2
        eps = np.sqrt(sigma2) * rng.standard_normal()
        r[t] = mu + eps
        resid_prev2 = eps * eps
    return r


def test_fit_recovers_known_params():
    # data from known GARCH(1,1); fit should land in the neighbourhood
    r = _simulate_garch(4000, omega=0.05, alpha=0.08, beta=0.90, seed=11)
    p = fit_garch11(r)
    assert isinstance(p, GarchParams)
    assert 0.0 <= p.alpha < 1.0 and 0.0 <= p.beta < 1.0
    assert p.alpha + p.beta < 1.0          # stationarity always enforced
    assert abs((p.alpha + p.beta) - 0.98) < 0.06   # persistence recovered roughly


def test_forecast_converges_to_unconditional():
    r = _simulate_garch(3000, omega=0.05, alpha=0.08, beta=0.90, seed=3)
    p = fit_garch11(r)
    sigma2, resid = conditional_variance(p, r)
    fc = forecast_var(p, sigma2[-1], resid[-1] ** 2, horizon=400)
    uncond = p.omega / (1 - p.alpha - p.beta)
    assert abs(fc[-1] - uncond) < 0.05 * uncond   # tail converges to unconditional variance


def test_conditional_variance_shapes_and_positive():
    r = _simulate_garch(500, omega=0.05, alpha=0.08, beta=0.90, seed=5)
    p = fit_garch11(r)
    sigma2, resid = conditional_variance(p, r)
    assert sigma2.shape == r.shape and resid.shape == r.shape
    assert np.all(sigma2 > 0)


def test_simulate_ci_brackets_point_and_is_deterministic():
    r = _simulate_garch(1000, omega=0.05, alpha=0.08, beta=0.90, seed=9)
    p = fit_garch11(r)
    sigma2, resid = conditional_variance(p, r)
    point = np.sqrt(forecast_var(p, sigma2[-1], resid[-1] ** 2, horizon=10) * 252)
    lo1, hi1 = simulate_ci(p, sigma2[-1], resid[-1] ** 2, horizon=10, n_paths=2000, seed=0)
    lo2, hi2 = simulate_ci(p, sigma2[-1], resid[-1] ** 2, horizon=10, n_paths=2000, seed=0)
    assert np.allclose(lo1, lo2) and np.allclose(hi1, hi2)   # deterministic under seed
    assert np.all(lo1 <= point + 1e-9) and np.all(point <= hi1 + 1e-9)  # brackets point
    assert np.all(hi1[1:] >= hi1[:-1] - 1e-9)                # band widens with horizon
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest packages/ml/tests/test_garch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_ml'`. (If `saalr_ml` is not importable at all, first run `uv sync` so the new workspace member installs.)

- [ ] **Step 4: Write the implementation**

```python
# packages/ml/saalr_ml/garch.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

TRADING_DAYS = 252


@dataclass(frozen=True)
class GarchParams:
    omega: float
    alpha: float
    beta: float
    mu: float


def conditional_variance(params: GarchParams, returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Filter the GARCH(1,1) conditional-variance series and residuals for `returns`
    (already scaled). sigma2[t] is the variance for day t given info up to t-1."""
    resid = returns - params.mu
    n = len(returns)
    sigma2 = np.empty(n)
    sigma2[0] = max(np.var(resid), 1e-8)
    for t in range(1, n):
        sigma2[t] = params.omega + params.alpha * resid[t - 1] ** 2 + params.beta * sigma2[t - 1]
    return sigma2, resid


def _neg_loglik(theta: np.ndarray, returns: np.ndarray) -> float:
    omega, alpha, beta, mu = theta
    if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1.0:
        return 1e12
    p = GarchParams(omega, alpha, beta, mu)
    sigma2, resid = conditional_variance(p, returns)
    if np.any(sigma2 <= 0):
        return 1e12
    ll = -0.5 * np.sum(np.log(2.0 * np.pi * sigma2) + resid**2 / sigma2)
    return 1e12 if not np.isfinite(ll) else -ll


def fit_garch11(returns: np.ndarray) -> GarchParams:
    """Maximum-likelihood GARCH(1,1) with constant mean, normal innovations.
    `returns` should already be scaled (×100) for optimizer conditioning."""
    returns = np.asarray(returns, dtype=float)
    var = float(np.var(returns))
    mu0 = float(np.mean(returns))
    alpha0, beta0 = 0.05, 0.90
    omega0 = max(var * (1 - alpha0 - beta0), 1e-6)
    x0 = np.array([omega0, alpha0, beta0, mu0])
    bounds = [(1e-9, None), (0.0, 0.9999), (0.0, 0.9999), (None, None)]
    constraints = [{"type": "ineq", "fun": lambda th: 1.0 - th[1] - th[2] - 1e-6}]
    res = minimize(
        _neg_loglik, x0, args=(returns,), method="SLSQP", bounds=bounds, constraints=constraints
    )
    omega, alpha, beta, mu = (float(v) for v in res.x)
    if alpha + beta >= 1.0:  # numerical guard: renormalize just below the unit root
        scale = (alpha + beta) / 0.999
        alpha, beta = alpha / scale, beta / scale
    return GarchParams(max(omega, 1e-9), max(alpha, 0.0), max(beta, 0.0), mu)


def forecast_var(
    params: GarchParams, last_sigma2: float, last_resid2: float, horizon: int
) -> np.ndarray:
    """Daily conditional-variance forecast for steps 1..horizon (scaled units)."""
    persistence = params.alpha + params.beta
    out = np.empty(horizon)
    prev = params.omega + params.alpha * last_resid2 + params.beta * last_sigma2
    out[0] = prev
    for k in range(1, horizon):
        prev = params.omega + persistence * prev
        out[k] = prev
    return out


def simulate_ci(
    params: GarchParams,
    last_sigma2: float,
    last_resid2: float,
    horizon: int,
    n_paths: int = 1000,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Simulation-based 95% band on the annualized vol forecast (percent) per step."""
    rng = np.random.default_rng(seed)
    sigma2 = np.full(n_paths, last_sigma2)
    resid2 = np.full(n_paths, last_resid2)
    vols = np.empty((horizon, n_paths))
    for k in range(horizon):
        sigma2 = params.omega + params.alpha * resid2 + params.beta * sigma2
        vols[k] = np.sqrt(sigma2 * TRADING_DAYS)  # annualized percent (scale cancels)
        resid = np.sqrt(sigma2) * rng.standard_normal(n_paths)
        resid2 = resid**2
    lo = np.percentile(vols, 2.5, axis=1)
    hi = np.percentile(vols, 97.5, axis=1)
    return lo, hi


def annualize_vol_pct(daily_var_scaled: np.ndarray | float) -> np.ndarray | float:
    """Scaled daily variance -> annualized vol PERCENT. The ×100 return-scaling and the
    ×100 percent conversion cancel, so this is just sqrt(var * 252)."""
    return np.sqrt(np.asarray(daily_var_scaled) * TRADING_DAYS)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest packages/ml/tests/test_garch.py -v`
Expected: PASS (4). If `test_fit_recovers_known_params`'s persistence tolerance is too tight for the SLSQP fit on simulated data, widen the tolerance band slightly (it is a statistical recovery, not exact) and report it — do NOT loosen the stationarity assertion `alpha+beta<1`.

- [ ] **Step 6: Lint + commit**

```bash
uv sync
uvx ruff check packages/ml/saalr_ml/garch.py packages/ml/tests/test_garch.py
git add packages/ml/pyproject.toml packages/ml/saalr_ml/__init__.py packages/ml/saalr_ml/garch.py packages/ml/tests/test_garch.py uv.lock
git commit -m "feat(ml): saalr-ml package + hand-rolled GARCH(1,1) (fit/forecast/CI)"
```

---

## Task 2: HV21 baseline + walk-forward evaluation

**Files:**
- Create: `packages/ml/saalr_ml/baseline.py`
- Create: `packages/ml/saalr_ml/evaluate.py`
- Test: `packages/ml/tests/test_evaluate.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/ml/tests/test_evaluate.py
import numpy as np

from saalr_ml.baseline import hv21
from saalr_ml.evaluate import WalkForward, walk_forward


def test_hv21_matches_hand_calc():
    rng = np.random.default_rng(1)
    returns = rng.standard_normal(100) * 1.0  # scaled returns
    expected = float(np.std(returns[-21:]) * np.sqrt(252))
    assert abs(hv21(returns) - expected) < 1e-9


def test_walk_forward_prefers_garch_on_volatility_clustering():
    # strong GARCH clustering -> GARCH should beat a flat 21-day window
    from saalr_ml.tests_helpers import simulate_garch  # see note below
    r = simulate_garch(1500, omega=0.05, alpha=0.12, beta=0.86, seed=21)
    wf = walk_forward(r, holdout_days=60)
    assert isinstance(wf, WalkForward)
    assert wf.primary == "garch"
    assert wf.garch_mae < wf.hv21_mae


def test_walk_forward_ties_or_baseline_on_iid():
    rng = np.random.default_rng(2)
    r = rng.standard_normal(1500) * 1.0   # near-constant vol, no clustering
    wf = walk_forward(r, holdout_days=60)
    # GARCH has no clustering to exploit; it must NOT spuriously dominate
    assert wf.primary in ("hv21", "garch")
    assert wf.hv21_mae <= wf.garch_mae * 1.5   # baseline is competitive on IID data
```

> Note: the test imports `simulate_garch` from a shared helper. Create `packages/ml/saalr_ml/tests_helpers.py` exporting the `_simulate_garch` body from Task 1 as a public `simulate_garch(n, omega, alpha, beta, mu=0.0, seed=7)`. (Keeping it in the package, not the test dir, lets both test modules import it without path hacks.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/ml/tests/test_evaluate.py -v`
Expected: FAIL — `ModuleNotFoundError` for `saalr_ml.baseline` / `saalr_ml.evaluate` / `saalr_ml.tests_helpers`.

- [ ] **Step 3: Write the implementations**

```python
# packages/ml/saalr_ml/tests_helpers.py
from __future__ import annotations

import numpy as np


def simulate_garch(n, omega, alpha, beta, mu=0.0, seed=7):
    """Generate a GARCH(1,1) return series (scaled units) for tests."""
    rng = np.random.default_rng(seed)
    r = np.empty(n)
    sigma2 = omega / (1 - alpha - beta)
    resid_prev2 = sigma2
    for t in range(n):
        sigma2 = omega + alpha * resid_prev2 + beta * sigma2
        eps = np.sqrt(sigma2) * rng.standard_normal()
        r[t] = mu + eps
        resid_prev2 = eps * eps
    return r
```

```python
# packages/ml/saalr_ml/baseline.py
from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def hv21(returns: np.ndarray) -> float:
    """Annualized stdev of the last 21 (scaled) daily returns -> vol PERCENT."""
    window = np.asarray(returns, dtype=float)[-21:]
    return float(np.std(window) * np.sqrt(TRADING_DAYS))
```

```python
# packages/ml/saalr_ml/evaluate.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .garch import conditional_variance, fit_garch11


@dataclass(frozen=True)
class WalkForward:
    garch_mae: float
    hv21_mae: float
    lift: float
    primary: str
    holdout_days: int


def walk_forward(returns: np.ndarray, holdout_days: int = 40) -> WalkForward:
    """Fit GARCH on the training window, forward-filter across the holdout, and score
    GARCH vs HV21 one-step-ahead variance forecasts against the realized-variance proxy r^2."""
    returns = np.asarray(returns, dtype=float)
    n = len(returns)
    train = returns[:-holdout_days]
    params = fit_garch11(train)

    # GARCH 1-step variance forecast for each day = the filtered conditional variance
    # (variance for day t given info up to t-1), produced by running the fitted recursion
    # forward across the FULL series.
    sigma2, resid = conditional_variance(params, returns)
    idx = range(n - holdout_days, n)
    garch_fc = sigma2[n - holdout_days : n]
    realized = resid[n - holdout_days : n] ** 2

    # HV21 1-step forecast = variance of the trailing 21 returns ending the day before
    hv_fc = np.array([np.var(returns[i - 21 : i]) for i in idx])

    garch_mae = float(np.mean(np.abs(garch_fc - realized)))
    hv21_mae = float(np.mean(np.abs(hv_fc - realized)))
    lift = (hv21_mae - garch_mae) / hv21_mae if hv21_mae > 0 else 0.0
    primary = "garch" if garch_mae < hv21_mae else "hv21"
    return WalkForward(garch_mae, hv21_mae, lift, primary, holdout_days)
```

> Refactor note: Task 1's `test_garch.py` defines a local `_simulate_garch`. Leave it as-is (tests can keep their own copy); `tests_helpers.simulate_garch` is the shared public version for `test_evaluate.py`. Do not delete Task 1's local helper.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/ml/tests/test_evaluate.py -v`
Expected: PASS (3). If `test_walk_forward_prefers_garch_on_volatility_clustering` is flaky, increase the clustering (`alpha=0.12, beta=0.86`) or the series length — but do NOT weaken to `<=`; GARCH must genuinely beat HV21 on clustered data, that's the whole point. Report any tuning.

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/ml/saalr_ml/baseline.py packages/ml/saalr_ml/evaluate.py packages/ml/saalr_ml/tests_helpers.py packages/ml/tests/test_evaluate.py
git add packages/ml/saalr_ml/baseline.py packages/ml/saalr_ml/evaluate.py packages/ml/saalr_ml/tests_helpers.py packages/ml/tests/test_evaluate.py
git commit -m "feat(ml): HV21 baseline + walk-forward GARCH-vs-baseline evaluation"
```

---

## Task 3: Forecast orchestrator (`forecast.py`)

**Files:**
- Create: `packages/ml/saalr_ml/forecast.py`
- Test: `packages/ml/tests/test_forecast.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/ml/tests/test_forecast.py
import numpy as np
import pytest

from saalr_ml.forecast import vol_forecast
from saalr_ml.tests_helpers import simulate_garch


def _closes_from_returns(returns_scaled, p0=100.0):
    # returns are scaled (×100); de-scale to build a price path
    r = returns_scaled / 100.0
    return p0 * np.exp(np.cumsum(np.concatenate([[0.0], r])))


def test_vol_forecast_shape_and_honesty_fields():
    r = simulate_garch(600, omega=0.05, alpha=0.10, beta=0.88, seed=4)
    closes = _closes_from_returns(r)
    out = vol_forecast(closes, horizon=10)
    assert out["horizon_days"] == 10
    assert out["primary_model"] in ("garch", "hv21")
    assert len(out["primary_forecast"]) == 10
    assert out["model"] == "garch(1,1)" and out["approximate"] is True
    assert "garch_mae" in out["validation"] and "hv21_mae" in out["validation"]
    # exactly one alternative, naming the non-primary model
    alts = out["alternative_models"]
    assert len(alts) == 1 and alts[0]["model"] != out["primary_model"]
    # when GARCH loses, the alternative GARCH is explicitly flagged
    if out["primary_model"] == "hv21":
        assert alts[0]["status"] == "underperforming_baseline"


def test_vol_forecast_primary_matches_walk_forward_on_clustered_data():
    r = simulate_garch(1500, omega=0.05, alpha=0.12, beta=0.86, seed=21)
    closes = _closes_from_returns(r)
    out = vol_forecast(closes, horizon=5, holdout_days=60)
    assert out["primary_model"] == "garch"
    assert out["primary_ci_95"] is not None and len(out["primary_ci_95"]) == 5


def test_vol_forecast_rejects_short_history():
    with pytest.raises(ValueError, match="insufficient history"):
        vol_forecast(np.linspace(100, 110, 100), horizon=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/ml/tests/test_forecast.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_ml.forecast'`.

- [ ] **Step 3: Write the orchestrator**

```python
# packages/ml/saalr_ml/forecast.py
from __future__ import annotations

import numpy as np

from .baseline import hv21
from .evaluate import walk_forward
from .garch import GarchParams, conditional_variance, fit_garch11, forecast_var, simulate_ci

_SCALE = 100.0
_MIN_HISTORY = 250


def _round_list(xs) -> list[float]:
    return [round(float(x), 4) for x in xs]


def vol_forecast(closes, horizon: int, holdout_days: int = 40, seed: int = 0) -> dict:
    """Annualized vol forecast (percent) from a daily close series. Always reports GARCH
    and HV21; `primary` is chosen by the walk-forward holdout. Raises ValueError on too
    little history."""
    closes = np.asarray(closes, dtype=float)
    if len(closes) < _MIN_HISTORY:
        raise ValueError("insufficient history")
    returns = np.diff(np.log(closes)) * _SCALE

    wf = walk_forward(returns, holdout_days)

    params: GarchParams = fit_garch11(returns)
    sigma2, resid = conditional_variance(params, returns)
    fc_var = forecast_var(params, sigma2[-1], resid[-1] ** 2, horizon)
    garch_path = np.sqrt(fc_var * 252)  # annualized percent
    lo, hi = simulate_ci(params, sigma2[-1], resid[-1] ** 2, horizon, seed=seed)
    garch_ci = [[round(float(a), 4), round(float(b), 4)] for a, b in zip(lo, hi)]

    hv_path = np.full(horizon, hv21(returns))

    forecasts = {
        "garch": (_round_list(garch_path), garch_ci),
        "hv21": (_round_list(hv_path), None),
    }
    primary = wf.primary
    alt = "hv21" if primary == "garch" else "garch"
    alt_status = "baseline" if alt == "hv21" else "underperforming_baseline"

    return {
        "horizon_days": horizon,
        "primary_model": primary,
        "primary_forecast": forecasts[primary][0],
        "primary_ci_95": forecasts[primary][1],
        "alternative_models": [
            {
                "model": alt,
                "forecast": forecasts[alt][0],
                "status": alt_status,
                "delta_mae_vs_baseline": round(float(wf.garch_mae - wf.hv21_mae), 6),
            }
        ],
        "validation": {
            "holdout_days": wf.holdout_days,
            "garch_mae": round(float(wf.garch_mae), 6),
            "hv21_mae": round(float(wf.hv21_mae), 6),
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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/ml/tests/test_forecast.py -v`
Expected: PASS (3).

- [ ] **Step 5: Run the whole ml package + lint**

Run: `uv run pytest packages/ml/tests -q && uvx ruff check packages/ml/saalr_ml`
Expected: all green, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add packages/ml/saalr_ml/forecast.py packages/ml/tests/test_forecast.py
git commit -m "feat(ml): vol_forecast orchestrator (honest GARCH-vs-HV21 result)"
```

---

## Task 4: API endpoint (`apps/api/saalr_api/forecast/`) + wiring

**Files:**
- Modify: `apps/api/pyproject.toml` (add `saalr-ml` dep + source)
- Modify: `packages/core/saalr_core/config.py` (add `vol_forecast_cache_ttl_seconds`)
- Create: `apps/api/saalr_api/forecast/__init__.py` (empty)
- Create: `apps/api/saalr_api/forecast/gating.py`
- Create: `apps/api/saalr_api/forecast/repo.py`
- Create: `apps/api/saalr_api/forecast/router.py`
- Modify: `apps/api/saalr_api/main.py` (register router; set TTL on app.state)
- Test: `tests/integration/test_vol_forecast.py`

- [ ] **Step 1: Add the dependency + setting**

In `apps/api/pyproject.toml`: add `"saalr-ml",` to `dependencies` and `saalr-ml = { workspace = true }` under `[tool.uv.sources]`. Then `uv sync`.

In `packages/core/saalr_core/config.py`, add to `Settings` (after `vol_surface_cache_ttl_seconds`):
```python
    vol_forecast_cache_ttl_seconds: int = 21600  # 6h
```

- [ ] **Step 2: Write the failing integration test**

```python
# tests/integration/test_vol_forecast.py
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, n=300):
    # a deterministic pseudo-random walk with mild volatility clustering
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    px = 100.0
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol = :s"), {"s": symbol})
        vol = 0.01
        for i in range(n):
            vol = 0.9 * vol + 0.1 * (0.01 + 0.02 * (i % 7 == 0))
            step = math.sin(i * 0.3) * vol + (0.0005 if i % 2 else -0.0004)
            px = max(1.0, px * (1 + step))
            ts = start + timedelta(days=i)
            await conn.execute(
                text(
                    """INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                       VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""
                ),
                {"ts": ts, "sym": symbol, "o": Decimal(str(round(px, 4))),
                 "h": Decimal(str(round(px + 1, 4))), "l": Decimal(str(round(px - 1, 4))),
                 "c": Decimal(str(round(px, 4))), "v": 1000},
            )


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tenant_id}
        )


async def test_vol_forecast_pro_returns_both_models_and_persists_validation(app_sessionmaker, admin_engine):
    email = "vf-pro@x.com"
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": f"Bearer dev:{email}"}
            # a /me call bootstraps the tenant + subscription and returns the tenant id
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)

            r = await c.get("/v1/market/vol-forecast?ticker=AAPL&horizon=10", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ticker"] == "AAPL" and body["horizon_days"] == 10
            assert body["primary_model"] in ("garch", "hv21")
            assert len(body["primary_forecast"]) == 10
            assert body["validation"]["holdout_days"] >= 1
            assert len(body["alternative_models"]) == 1

    # a model_validation_runs row was written
    async with admin_engine.begin() as conn:
        n = (await conn.execute(
            text("SELECT count(*) FROM model_validation_runs WHERE model_name='garch'")
        )).scalar_one()
    assert n >= 1


async def test_vol_forecast_free_tier_is_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:vf-free@x.com"}
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/vol-forecast?ticker=AAPL&horizon=10", headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO"


async def test_vol_forecast_insufficient_history_is_422(app_sessionmaker, admin_engine):
    email = "vf-short@x.com"
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": f"Bearer dev:{email}"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "TINY", n=100)  # < 250
            r = await c.get("/v1/market/vol-forecast?ticker=TINY&horizon=10", headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "INSUFFICIENT_HISTORY"
```

> The `_make_pro` helper sets the tier directly in the DB after the dev login bootstraps the tenant/subscription. The `/me` call first ensures the tenant + subscription rows exist. (This mirrors how `test_strategies.py` upgrades a tenant to pro.)

- [ ] **Step 3: Run test to verify it fails**

Run (env exported):
```bash
export ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr"
export APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr"
uv run pytest tests/integration/test_vol_forecast.py -v
```
Expected: FAIL — 404 on the route (router not registered yet) / ModuleNotFoundError on `saalr_api.forecast`.

- [ ] **Step 4: Write the gating, repo, router**

```python
# apps/api/saalr_api/forecast/gating.py
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal


async def require_ml_forecast(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    _session, principal = ctx
    if not entitlements_for(principal.tier)["ml_forecast"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": {
                    "code": "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO",
                    "message": "volatility forecasting requires a Pro or Premium plan",
                }
            },
        )
    yield ctx
```

```python
# apps/api/saalr_api/forecast/repo.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.ids import new_id


async def load_closes(
    session: AsyncSession, symbol: str, market: str, lookback_days: int = 760
) -> list[float]:
    """Daily closes for `symbol` over the trailing window (non-RLS shared `bars`)."""
    start = (datetime.now(timezone.utc).date()) - timedelta(days=lookback_days)
    rows = (
        await session.execute(
            text(
                """
                SELECT close FROM bars
                WHERE symbol = :sym AND market = :mkt AND interval = '1d' AND ts::date >= :s
                ORDER BY ts
                """
            ),
            {"sym": symbol, "mkt": market, "s": start},
        )
    ).all()
    return [float(r.close) for r in rows]


async def record_validation(
    session: AsyncSession,
    model_name: str,
    market: str,
    cohort_label: str,
    baseline_name: str,
    status: str,
    metric_summary_json: dict,
) -> None:
    """INSERT a model_validation_runs row (non-RLS shared table; saalr_app has grants)."""
    now = datetime.now(timezone.utc)
    await session.execute(
        text(
            """
            INSERT INTO model_validation_runs
              (validation_id, model_name, market, cohort_label, baseline_name, status,
               metric_summary_json, started_at, completed_at)
            VALUES
              (:vid, :model, :market, :cohort, :baseline, :status,
               CAST(:metrics AS JSONB), :started, :completed)
            """
        ),
        {
            "vid": str(new_id()), "model": model_name, "market": market, "cohort": cohort_label,
            "baseline": baseline_name, "status": status, "metrics": _json(metric_summary_json),
            "started": now, "completed": now,
        },
    )


def _json(d: dict) -> str:
    import json

    return json.dumps(d)


def today_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()
```

```python
# apps/api/saalr_api/forecast/router.py
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_ml.forecast import vol_forecast

from ..auth import Principal
from . import repo
from .gating import require_ml_forecast

router = APIRouter(prefix="/v1/market", tags=["forecast"])


def _validate(ticker: str, market: str) -> None:
    if not ticker or not ticker.isalpha():
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "unknown ticker"}})
    if market not in ("US",):
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": "unsupported market"}})


@router.get("/vol-forecast")
async def vol_forecast_endpoint(
    request: Request,
    ticker: str = Query(...),
    market: str = Query("US"),
    horizon: int = Query(10, ge=1, le=30),
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    _validate(ticker, market)
    ticker = ticker.upper()
    session, _principal = ctx
    redis = request.app.state.redis
    ttl = request.app.state.vol_forecast_ttl
    key = f"mdq:volfc:v1:{market}:{ticker}:{horizon}"

    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    closes = await repo.load_closes(session, ticker, market)
    try:
        result = vol_forecast(np.asarray(closes, dtype=float), horizon)
    except ValueError as exc:
        raise HTTPException(
            422, {"error": {"code": "INSUFFICIENT_HISTORY", "message": str(exc)}}
        ) from exc

    payload = {
        "ticker": ticker,
        "market": market,
        "as_of": datetime.now(timezone.utc).isoformat(),
        **result,
    }

    await repo.record_validation(
        session,
        model_name="garch",
        market=market,
        cohort_label=f"{ticker}:{repo.today_str()}",
        baseline_name="hv21",
        status="passed" if result["primary_model"] == "garch" else "failed",
        metric_summary_json={**result["validation"], "params": result["params"]},
    )

    await redis.set(key, json.dumps(payload), ex=ttl)
    return payload
```

In `apps/api/saalr_api/main.py`:
- import: `from .forecast.router import router as forecast_router`
- in the lifespan, after `app.state.vol_surface_ttl = ...`: `app.state.vol_forecast_ttl = settings.vol_forecast_cache_ttl_seconds`
- after `app.include_router(strategies_router)` (and the backtests router): `app.include_router(forecast_router)`

> The validation row is committed by `get_principal`'s session transaction on handler return. `record_validation` runs on that (RLS) session, but `model_validation_runs` is non-RLS so the tenant GUC is irrelevant and the `saalr_app` grant from 0001 applies.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_vol_forecast.py -v` (env exported, Redis up)
Expected: PASS (3). If the 200 test fails on cache-key collisions across runs, note the test seeds fresh bars each run and the key includes ticker+horizon; flush is not required because the payload is deterministic per seed. If `np` import in the router is flagged unused by ruff, keep it (it is used by `np.asarray`).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/forecast apps/api/saalr_api/main.py packages/core/saalr_core/config.py tests/integration/test_vol_forecast.py
git add apps/api/pyproject.toml packages/core/saalr_core/config.py apps/api/saalr_api/forecast apps/api/saalr_api/main.py tests/integration/test_vol_forecast.py uv.lock
git commit -m "feat(api): GET /v1/market/vol-forecast (GARCH, ml_forecast-gated, cached, validated)"
```

---

## Task 5: Full gate

**Files:** none (verification only). Redis up + 55432 env exported.

- [ ] **Step 1: ML package + core suites**

Run: `uv run pytest packages/ml/tests packages/core/tests -q`
Expected: all green.

- [ ] **Step 2: API integration (forecast + regression)**

Run: `uv run pytest tests/integration/test_vol_forecast.py tests/integration/test_market.py tests/integration/test_strategies.py -q`
Expected: green (the new endpoint + the existing market/strategies endpoints unaffected). If a broad `uv run pytest tests/integration` is attempted and errors importing a worker package, restrict to the API/forecast files (worker integration tests need their `--package` flag, unrelated to this slice).

- [ ] **Step 3: Lint**

Run: `uvx ruff check packages/ml apps/api/saalr_api/forecast`
Expected: clean.

- [ ] **Step 4: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "chore(ml): GARCH vol-forecast slice — suite + lint green"
```

---

## Self-review notes (addressed)

- **Spec coverage:** GARCH fit/forecast/CI (T1), HV21 + walk-forward honesty (T2), orchestrator with the honest primary/alternative shape (T3), the gated+cached endpoint + `model_validation_runs` persistence + insufficient-history 422 (T4), gate (T5). The `ml_forecast` gate, Redis cache, and `as_of` are all in T4.
- **Grant:** verified — no migration needed (`0001` line 290 grants `saalr_app` on all tables; `model_validation_runs` is non-RLS). T4's integration test proves the insert works as `saalr_app`.
- **Units:** returns scaled ×100 throughout the ML package; `annualize` = `sqrt(var*252)` because the ×100 scaling cancels the ×100 percent conversion. `vol_forecast` consumes raw closes and does the diff/log/scale internally; the router passes raw closes.
- **Determinism:** all ML tests seed `np.random.default_rng`; `simulate_ci` takes a `seed`. No `Date.now`/wall-clock in the pure layer.
- **Type consistency:** `GarchParams(omega,alpha,beta,mu)`; `conditional_variance -> (sigma2, resid)`; `forecast_var(params,last_sigma2,last_resid2,horizon)`; `walk_forward -> WalkForward(garch_mae,hv21_mae,lift,primary,holdout_days)`; `vol_forecast -> dict` with keys consumed verbatim by the router. The router maps `primary_model=="garch"` → validation `status="passed"`.
- **Install path:** `saalr-ml` is a dep of `saalr-api` (a root dep), so it installs in the root env → `uv run pytest` imports `saalr_ml` and the API without `--package`.
