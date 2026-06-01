# Monte-Carlo POP (ML slice B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `POST /v1/strategies/montecarlo` — a vectorized GBM Monte-Carlo that returns POP, EV, and a P&L histogram for a strategy's legs, with σ sourced from the slice-A GARCH forecast (Pro-gated via `ml_forecast`) or an explicit override.

**Architecture:** A pure numpy engine in `saalr_ml/montecarlo.py`; a shared `forecast/service.py::get_or_compute_forecast` extracted from the forecast router (so both endpoints reuse the cached, honest σ); a new `apps/api/saalr_api/montecarlo/` feature composing bars (spot) + GARCH (σ) + FRED (rate) + the legs (horizon).

**Tech Stack:** Python 3.12, numpy, FastAPI, SQLAlchemy 2.0 async, redis.asyncio, pydantic, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-06-01-montecarlo-pop-design.md`

**Conventions / facts (verified):**
- `from __future__ import annotations` at the top of every module.
- `saalr-ml` already depends on numpy and on `saalr-core`; it's a root + `saalr-api` dep so `uv run pytest` imports it. Strategy types: `saalr_core.strategies.types` — `OptionLeg(option_type, side, strike, expiry, qty, entry_price)`, `EquityLeg(side, qty, entry_price)`, `CashLeg(amount)`, `Side.sign` (+1/−1), `OptionType.CALL/PUT`, `OPTION_MULTIPLIER=100`. `expiry` is a `YYYY-MM-DD` string.
- Core scalar payoff to cross-check against: `saalr_core.strategies.payoff._leg_pnl_at_expiry(leg, s)`; helpers `spot_grid`, `expiration_curve`, `profit_intervals`; lognormal POP `saalr_core.strategies.pop.probability_of_profit(spot, atm_iv, t_years, rate, div_yield, profit_intervals)`.
- Reuse `StrategyConfigIn` from `apps/api/saalr_api/strategies/schemas.py` (has `.to_domain() -> StrategyConfig`; requires ≥1 leg).
- Gate: reuse `apps/api/saalr_api/forecast/gating.py::require_ml_forecast` (402 `ENTITLEMENT_ML_FORECAST_REQUIRES_PRO`).
- Forecast pieces: `forecast/repo.py::load_closes(session, symbol, market, lookback_days=900) -> list[float]` (ordered by ts; non-RLS bars) and `record_validation(...)`; the GARCH cache key is `mdq:volfc:v1:{market}:{ticker}:{horizon}`; `vol_forecast(np.array(closes), horizon)` raises `ValueError` on `<250`. `app.state` has `redis`, `sessionmaker`, `vol_forecast_ttl`, `rate_provider`.
- Rate: `curve = await app.state.rate_provider.get_curve()`; `curve.rate_for(t_years) -> float`.
- Integration env: Postgres on 55432, Redis on 6379. Export before pytest:
  ```bash
  export ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr"
  export APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr"
  ```
- Pro upgrade in tests: `tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]`, then `UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t` (users has no tenant_id column).

---

## Task 1: Monte-Carlo engine (`saalr_ml/montecarlo.py`)

**Files:**
- Create: `packages/ml/saalr_ml/montecarlo.py`
- Test: `packages/ml/tests/test_montecarlo.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/ml/tests/test_montecarlo.py
import numpy as np

from saalr_core.strategies.payoff import (
    _leg_pnl_at_expiry,
    expiration_curve,
    profit_intervals,
    spot_grid,
)
from saalr_core.strategies.pop import probability_of_profit
from saalr_core.strategies.types import OptionLeg, OptionType, Side
from saalr_ml.montecarlo import monte_carlo_pop, sentiment_adjusted_drift, strategy_pnl


def _long_call(strike=100.0, expiry="2025-06-01", entry=2.5):
    return OptionLeg(OptionType.CALL, Side.BUY, strike, expiry, 1, entry)


def test_vectorized_payoff_matches_core_scalar():
    legs = [
        _long_call(100.0, entry=3.0),
        OptionLeg(OptionType.CALL, Side.SELL, 110.0, "2025-06-01", 1, 1.0),
    ]
    prices = np.array([80.0, 100.0, 105.0, 110.0, 130.0])
    vec = strategy_pnl(legs, prices)
    for i, s in enumerate(prices):
        scalar = sum(_leg_pnl_at_expiry(leg, float(s)) for leg in legs)
        assert abs(float(vec[i]) - scalar) < 1e-9


def test_long_call_pop_matches_lognormal_closed_form():
    spot, sigma, t, rate = 100.0, 0.25, 30 / 365, 0.05
    legs = [_long_call(100.0, entry=2.5)]
    mc = monte_carlo_pop(legs, spot, t, sigma, rate, paths=50000, seed=0)
    curve = expiration_curve(legs, spot_grid(legs, spot))
    ln = probability_of_profit(spot, sigma, t, rate, 0.0, profit_intervals(curve))
    assert abs(mc["pop"] - ln["pop"]) < 0.02   # MC sampling error at 50k paths is ~0.002


def test_histogram_determinism_and_bounds():
    legs = [_long_call(entry=2.5)]
    a = monte_carlo_pop(legs, 100.0, 30 / 365, 0.25, 0.05, paths=10000, seed=1)
    b = monte_carlo_pop(legs, 100.0, 30 / 365, 0.25, 0.05, paths=10000, seed=1)
    assert a["pop"] == b["pop"] and a["ev"] == b["ev"]          # deterministic per seed
    assert sum(a["histogram"]["counts"]) == 10000
    assert len(a["histogram"]["bin_edges"]) == 101              # bins + 1
    assert 0.0 <= a["pop"] <= 1.0
    assert a["model"] == "gbm_mc" and a["approximate"] is True


def test_sentiment_drift_raises_long_call_pop():
    legs = [_long_call(entry=2.5)]
    spot, sigma, t, rate = 100.0, 0.25, 30 / 365, 0.05
    base = monte_carlo_pop(legs, spot, t, sigma, rate, drift_adjust=0.0, paths=50000, seed=2)
    up = monte_carlo_pop(
        legs, spot, t, sigma, rate,
        drift_adjust=sentiment_adjusted_drift(0.8, sigma, t), paths=50000, seed=2,
    )
    down = monte_carlo_pop(
        legs, spot, t, sigma, rate,
        drift_adjust=sentiment_adjusted_drift(-0.8, sigma, t), paths=50000, seed=2,
    )
    assert up["pop"] > base["pop"] > down["pop"]


def test_rejects_nonpositive_inputs():
    legs = [_long_call(entry=2.5)]
    for bad in [dict(spot=0.0), dict(t_years=0.0), dict(sigma=0.0)]:
        kw = dict(spot=100.0, t_years=30 / 365, sigma=0.25, rate=0.05)
        kw.update(bad)
        try:
            monte_carlo_pop(legs, kw["spot"], kw["t_years"], kw["sigma"], kw["rate"])
            assert False, "expected ValueError"
        except ValueError:
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/ml/tests/test_montecarlo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_ml.montecarlo'`.

- [ ] **Step 3: Write the engine**

```python
# packages/ml/saalr_ml/montecarlo.py
from __future__ import annotations

import numpy as np

from saalr_core.strategies.types import (
    OPTION_MULTIPLIER,
    CashLeg,
    EquityLeg,
    OptionLeg,
    OptionType,
)


def _leg_pnl_vec(leg, terminal: np.ndarray) -> np.ndarray:
    """Vectorized per-leg expiry P&L over an array of terminal prices.
    Mirrors saalr_core.strategies.payoff._leg_pnl_at_expiry (kept in sync by a test)."""
    if isinstance(leg, OptionLeg):
        if leg.option_type is OptionType.CALL:
            intrinsic = np.maximum(terminal - leg.strike, 0.0)
        else:
            intrinsic = np.maximum(leg.strike - terminal, 0.0)
        entry = leg.entry_price or 0.0
        return leg.side.sign * (intrinsic - entry) * OPTION_MULTIPLIER * leg.qty
    if isinstance(leg, EquityLeg):
        entry = leg.entry_price or 0.0
        return leg.side.sign * (terminal - entry) * leg.qty
    if isinstance(leg, CashLeg):
        return np.zeros_like(terminal)
    raise TypeError(f"unknown leg type {type(leg)}")


def strategy_pnl(legs, terminal: np.ndarray) -> np.ndarray:
    total = np.zeros_like(terminal)
    for leg in legs:
        total = total + _leg_pnl_vec(leg, terminal)
    return total


def sentiment_adjusted_drift(sentiment: float, sigma: float, t_years: float) -> float:
    """LLD §4.4: shift drift by ±0.5σ√t at sentiment extremes."""
    return float(sentiment * 0.5 * sigma * np.sqrt(t_years))


def monte_carlo_pop(
    legs,
    spot: float,
    t_years: float,
    sigma: float,
    rate: float,
    div_yield: float = 0.0,
    drift_adjust: float = 0.0,
    paths: int = 10000,
    seed: int = 0,
    hist_bins: int = 100,
) -> dict:
    """GBM Monte-Carlo of expiry P&L. Returns POP, EV, a P&L histogram, and percentiles."""
    if spot <= 0 or t_years <= 0 or sigma <= 0:
        raise ValueError("spot, t_years and sigma must be positive")
    rng = np.random.default_rng(seed)
    drift = (rate - div_yield - 0.5 * sigma**2) * t_years + drift_adjust
    diffusion = sigma * np.sqrt(t_years)
    z = rng.standard_normal(paths)
    terminal = spot * np.exp(drift + diffusion * z)
    pnl = strategy_pnl(legs, terminal)
    counts, edges = np.histogram(pnl, bins=hist_bins)
    return {
        "pop": float(np.mean(pnl > 0)),
        "ev": float(np.mean(pnl)),
        "paths": int(paths),
        "histogram": {
            "counts": [int(c) for c in counts],
            "bin_edges": [float(e) for e in edges],
        },
        "percentiles": {
            "p5": float(np.percentile(pnl, 5)),
            "p50": float(np.percentile(pnl, 50)),
            "p95": float(np.percentile(pnl, 95)),
        },
        "max_profit_observed": float(np.max(pnl)),
        "max_loss_observed": float(np.min(pnl)),
        "model": "gbm_mc",
        "approximate": True,
        "seed": int(seed),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/ml/tests/test_montecarlo.py -v`
Expected: PASS (5). The lognormal cross-check should pass comfortably at 50k paths; if it's marginal, raise `paths` to 100000 (do NOT widen the 0.02 tolerance — a tight match validates the engine).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/ml/saalr_ml/montecarlo.py packages/ml/tests/test_montecarlo.py
git add packages/ml/saalr_ml/montecarlo.py packages/ml/tests/test_montecarlo.py
git commit -m "feat(ml): Monte-Carlo POP engine (vectorized GBM, payoff cross-checked)"
```

---

## Task 2: Extract `get_or_compute_forecast` (shared service, behaviour-neutral)

**Files:**
- Create: `apps/api/saalr_api/forecast/service.py`
- Modify: `apps/api/saalr_api/forecast/router.py` (call the service)

- [ ] **Step 1: Write the service (extracted verbatim from the router's current body)**

```python
# apps/api/saalr_api/forecast/service.py
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from saalr_ml.forecast import vol_forecast

from . import repo


async def get_or_compute_forecast(
    redis, sessionmaker, session, ticker: str, market: str, horizon: int, ttl: int
) -> dict:
    """Return the GARCH vol-forecast payload for (ticker, market, horizon): a Redis cache
    read, else compute via vol_forecast (raises ValueError on <250 closes — the caller maps
    it to 422), persist a model_validation_runs row in its own committed session, and cache.
    Shared by the forecast endpoint and the Monte-Carlo endpoint."""
    key = f"mdq:volfc:v1:{market}:{ticker}:{horizon}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    closes = await repo.load_closes(session, ticker, market)
    result = vol_forecast(np.asarray(closes, dtype=float), horizon)

    payload = {
        "ticker": ticker,
        "market": market,
        "as_of": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    async with sessionmaker() as vsession, vsession.begin():
        await repo.record_validation(
            vsession,
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

- [ ] **Step 2: Refactor the router to call the service**

Replace the body of `vol_forecast_endpoint` in `apps/api/saalr_api/forecast/router.py` so the file becomes:

```python
# apps/api/saalr_api/forecast/router.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from . import service
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
    try:
        return await service.get_or_compute_forecast(
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

- [ ] **Step 3: Verify the forecast endpoint is unchanged**

Run (env exported, Redis up):
```bash
uv run pytest tests/integration/test_vol_forecast.py -v
```
Expected: the existing 3 tests still PASS (200 + validation row + cache hit, 402, 422). Then `uvx ruff check apps/api/saalr_api/forecast`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/saalr_api/forecast/service.py apps/api/saalr_api/forecast/router.py
git commit -m "refactor(forecast): extract get_or_compute_forecast service (shared by MC)"
```

---

## Task 3: Monte-Carlo API endpoint (`apps/api/saalr_api/montecarlo/`)

**Files:**
- Create: `apps/api/saalr_api/montecarlo/__init__.py` (empty)
- Create: `apps/api/saalr_api/montecarlo/schemas.py`
- Create: `apps/api/saalr_api/montecarlo/router.py`
- Modify: `apps/api/saalr_api/main.py` (register the router)
- Test: `tests/integration/test_montecarlo.py`

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_montecarlo.py
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
            px = max(1.0, px * (1 + (0.004 if i % 2 else -0.0035)))
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


async def _make_pro(admin_engine, tid):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tid})


def _future_expiry(days=30):
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()


def _long_call_config(underlying="AAPL"):
    return {
        "underlying": underlying,
        "legs": [{"kind": "option", "option_type": "CALL", "side": "BUY",
                  "strike": 100, "expiry": _future_expiry(30), "qty": 1, "entry_price": 2.5}],
    }


async def test_montecarlo_pro_garch_sigma(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)

            r = await c.post("/v1/strategies/montecarlo", json={"config": _long_call_config()}, headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert 0.0 <= body["pop"] <= 1.0
            assert body["sigma_source"] == "garch"
            assert body["horizon_days"] == 30
            assert sum(body["histogram"]["counts"]) == body["paths"]
            assert "ev" in body and "spot" in body


async def test_montecarlo_sigma_override(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-ovr@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=5)  # too few for GARCH, but spot is fine

            r = await c.post(
                "/v1/strategies/montecarlo",
                json={"config": _long_call_config(), "sigma": 0.3}, headers=h,
            )
            assert r.status_code == 200, r.text
            assert r.json()["sigma_source"] == "override"


async def test_montecarlo_free_tier_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-free@x.com"}
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.post("/v1/strategies/montecarlo", json={"config": _long_call_config()}, headers=h)
            assert r.status_code == 402


async def test_montecarlo_no_option_legs_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-noexp@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            cfg = {"underlying": "AAPL", "legs": [{"kind": "equity", "side": "BUY", "qty": 100}]}
            r = await c.post("/v1/strategies/montecarlo", json={"config": cfg}, headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "VALIDATION_NO_EXPIRY"


async def test_montecarlo_no_bars_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:mc-nobars@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            async with admin_engine.begin() as conn:
                await conn.execute(text("DELETE FROM bars WHERE symbol='ZZZZ'"))
            r = await c.post(
                "/v1/strategies/montecarlo",
                json={"config": _long_call_config("ZZZZ")}, headers=h,
            )
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "INSUFFICIENT_HISTORY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_montecarlo.py -v` (env exported, Redis up)
Expected: FAIL — 404 on the route / ModuleNotFoundError on `saalr_api.montecarlo`.

- [ ] **Step 3: Write the schemas + router, register in main**

```python
# apps/api/saalr_api/montecarlo/schemas.py
from __future__ import annotations

from pydantic import BaseModel, Field

from ..strategies.schemas import StrategyConfigIn


class MonteCarloRequest(BaseModel):
    config: StrategyConfigIn
    market: str = "US"
    sigma: float | None = Field(default=None, gt=0)
    paths: int = Field(default=10000, ge=1, le=200000)
    seed: int = 0
```

```python
# apps/api/saalr_api/montecarlo/router.py
from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.strategies.types import OptionLeg
from saalr_ml.montecarlo import monte_carlo_pop

from ..auth import Principal
from ..forecast import repo as forecast_repo
from ..forecast import service as forecast_service
from ..forecast.gating import require_ml_forecast
from .schemas import MonteCarloRequest

router = APIRouter(prefix="/v1/strategies", tags=["montecarlo"])


def _err(code: str, msg: str, status: int = 422) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message": msg}})


@router.post("/montecarlo")
async def montecarlo(
    body: MonteCarloRequest,
    request: Request,
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    session, _principal = ctx
    config = body.config.to_domain()
    legs = config.legs
    underlying = config.underlying.upper()
    market = body.market
    if market not in ("US",):
        raise _err("VALIDATION_INVALID_PARAMETER", "unsupported market", 400)

    today = datetime.now(timezone.utc).date()
    option_expiries = [date.fromisoformat(leg.expiry) for leg in legs if isinstance(leg, OptionLeg)]
    if not option_expiries:
        raise _err("VALIDATION_NO_EXPIRY", "strategy has no option legs with an expiry")
    days = (min(option_expiries) - today).days
    if days < 1:
        raise _err("VALIDATION_NO_EXPIRY", "nearest option expiry is not in the future")
    t_years = days / 365.0

    closes = await forecast_repo.load_closes(session, underlying, market)
    if not closes:
        raise _err("INSUFFICIENT_HISTORY", f"no bars for {underlying}")
    spot = closes[-1]

    if body.sigma is not None:
        sigma = float(body.sigma)
        sigma_source = "override"
    else:
        try:
            payload = await forecast_service.get_or_compute_forecast(
                request.app.state.redis,
                request.app.state.sessionmaker,
                session,
                underlying,
                market,
                days,
                request.app.state.vol_forecast_ttl,
            )
        except ValueError as exc:
            raise _err("INSUFFICIENT_HISTORY", str(exc)) from exc
        sigma = float(np.mean(payload["primary_forecast"])) / 100.0
        sigma_source = "garch"

    curve = await request.app.state.rate_provider.get_curve()
    rate = curve.rate_for(t_years) if t_years > 0 else 0.0

    result = monte_carlo_pop(legs, spot, t_years, sigma, rate, paths=body.paths, seed=body.seed)
    return {
        **result,
        "underlying": underlying,
        "market": market,
        "spot": spot,
        "sigma": sigma,
        "sigma_source": sigma_source,
        "horizon_days": days,
        "rate": rate,
    }
```

In `apps/api/saalr_api/main.py`: add `from .montecarlo.router import router as montecarlo_router` and `app.include_router(montecarlo_router)` (after the forecast router).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_montecarlo.py -v`
Expected: PASS (5). The GARCH-sigma test seeds 300 bars (≥250); the override test seeds only 5 (GARCH skipped, spot from the last bar).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/montecarlo apps/api/saalr_api/main.py tests/integration/test_montecarlo.py
git add apps/api/saalr_api/montecarlo apps/api/saalr_api/main.py tests/integration/test_montecarlo.py
git commit -m "feat(api): POST /v1/strategies/montecarlo (GARCH-sigma GBM POP/EV/histogram)"
```

---

## Task 4: Full gate

**Files:** none (verification only). Redis up + 55432 env exported.

- [ ] **Step 1: ML + core suites**

Run: `uv run pytest packages/ml/tests packages/core/tests -q`
Expected: all green.

- [ ] **Step 2: API integration (MC + forecast regression + strategies)**

Run: `uv run pytest tests/integration/test_montecarlo.py tests/integration/test_vol_forecast.py tests/integration/test_strategies.py -q`
Expected: green (MC + the forecast endpoint unaffected by the service extraction + strategies unaffected).

- [ ] **Step 3: Lint**

Run: `uvx ruff check packages/ml apps/api/saalr_api/montecarlo apps/api/saalr_api/forecast`
Expected: clean.

- [ ] **Step 4: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "chore(ml): Monte-Carlo POP slice — suite + lint green"
```

---

## Self-review notes (addressed)

- **Spec coverage:** engine with GBM + vectorized payoff + histogram + sentiment hook (T1), the shared `get_or_compute_forecast` extraction reused by MC (T2), the gated endpoint composing spot/σ/rate/horizon + all four error paths (T3), gate (T4). The vectorized-payoff cross-check (T1) and the lognormal POP cross-validation (T1) are both present.
- **Behaviour-neutral refactor:** T2 moves the router body verbatim into the service; the forecast tests (T2 Step 3) are the guard. The router keeps `_validate` + gating + the 422 mapping.
- **Type/units consistency:** `monte_carlo_pop(legs, spot, t_years, sigma, rate, div_yield, drift_adjust, paths, seed, hist_bins)` matches the router call; σ from GARCH = `mean(primary_forecast)/100` (percent→decimal); `Side.sign` and `OPTION_MULTIPLIER` mirror the core scalar payoff; `rate_for(t_years)` per the existing rate provider. Histogram `counts` sum to `paths`, `bin_edges` length `bins+1`.
- **Gating reuse:** MC reuses `require_ml_forecast` (no new entitlement). No tenant/RLS write on the MC path (it's a pure compute; only `get_or_compute_forecast` writes a non-RLS validation row in its own session).
- **Ordering:** expiry/legs validated before the bars load; bars (spot) before σ; σ before rate; all 422s raised before the compute.
