# Market Regime Engine + Trade Ideas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a rule-based market-regime engine + `GET /v1/market/regime` + an `/app/ideas` screen that classifies a ticker's regime and ranks the 21 templates against it.

**Architecture:** Pure numpy classifier in `saalr-ml`, pure scored recommender in `saalr-core`, an ungated FastAPI endpoint that composes them (enriching with GARCH vol-trend + sentiment only when the principal has `ml_forecast`), and a React `/app/ideas` page whose "Apply" deep-links a built template into the existing strategy builder.

**Tech Stack:** Python 3.12 / numpy / pytest (engine); FastAPI + asyncpg (API); React 18 + TS strict + Tailwind (theme tokens only) + TanStack Query + react-router 6 + Vitest (web).

**Spec:** `docs/superpowers/specs/2026-06-05-regime-engine-trade-ideas-design.md`

**Conventions:** commit footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`; theme tokens only for Tailwind class colors (`text-warn`/`bg-warn` are valid — used in `features/backtests/MetricsPanel.tsx`); double-quote JSX strings; NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`; branch `feat/scaffold-data-layer`; **pnpm/npm — NOT yarn**. Core/ml tests: `uv run pytest <path> -q` (saalr-ml is a root dep — plain `uv run pytest` imports it). Integration tests need Postgres on **55432** (`APP_DATABASE_URL`/`ADMIN_DATABASE_URL` env override); if unavailable locally, they're skipped like other DB-backed tests — the pure-unit tests cover the logic. Web: from `apps/web`, `npx vitest run <file>`; gate `npm run typecheck`/`npm run lint`.

---

## File Structure

- **Create** `packages/ml/saalr_ml/regime.py` — pure classifier: `trend_score`, `direction_label`, `realized_vol`, `realized_vol_percentile`, `vol_label`, `efficiency_ratio`, `momentum_label`, `vol_trend_label`, `classify_regime`.
- **Create** `packages/ml/tests/test_regime.py`.
- **Create** `packages/core/saalr_core/strategies/recommend.py` — pure `recommend(regime, templates)`.
- **Create** `packages/core/tests/test_recommend.py`.
- **Create** `apps/api/saalr_api/regime/__init__.py`, `service.py`, `router.py`.
- **Modify** `packages/core/saalr_core/config.py` — add `regime_cache_ttl_seconds`.
- **Modify** `apps/api/saalr_api/main.py` — import + register `regime_router`; set `app.state.regime_ttl`.
- **Create** `tests/integration/test_regime_api.py`.
- **Create** `apps/web/src/lib/regime.ts`, `apps/web/src/features/ideas/hooks.ts`, `RegimePanel.tsx`, `RecoCard.tsx`, `apps/web/src/pages/Ideas.tsx`, `apps/web/src/pages/Ideas.test.tsx`.
- **Modify** `apps/web/src/app/Router.tsx`, `apps/web/src/components/Sidebar.tsx`, `apps/web/src/pages/Strategies.tsx` (Apply-landing).

---

## Task 1: Pure regime classifier (`saalr_ml/regime.py`)

**Files:** Create `packages/ml/saalr_ml/regime.py`, Test `packages/ml/tests/test_regime.py`.

- [ ] **Step 1: Write the failing test** `packages/ml/tests/test_regime.py`:

```python
import numpy as np
import pytest

from saalr_ml.regime import (
    MIN_CLOSES, classify_regime, direction_label, efficiency_ratio, momentum_label,
    realized_vol_percentile, trend_score, vol_label, vol_trend_label,
)


def _ramp(n=120, step=0.004, start=100.0):
    return [start * (1 + step) ** i for i in range(n)]


def test_steady_uptrend_is_bullish_and_trending():
    c = _ramp()
    assert direction_label(trend_score(c)) in ("bullish", "strong_bullish")
    assert momentum_label(efficiency_ratio(c)) == "trending"


def test_flat_constant_is_neutral_range_bound():
    c = [100.0] * 120
    assert direction_label(trend_score(c)) == "neutral"
    assert momentum_label(efficiency_ratio(c)) == "range_bound"


def test_classify_raises_below_min_closes():
    with pytest.raises(ValueError):
        classify_regime([100.0] * (MIN_CLOSES - 1))


def test_classify_shape_and_headline():
    r = classify_regime(_ramp())
    assert set(r) >= {"direction", "volatility", "momentum", "headline", "last_close", "n_closes"}
    assert r["direction"]["label"] in ("bullish", "strong_bullish")
    assert "·" in r["headline"]
    assert r["n_closes"] == 120


def test_vol_percentile_is_high_when_recent_vol_spikes():
    rng = np.random.default_rng(0)
    calm = list(100 + np.cumsum(rng.normal(0, 0.15, 240)))
    storm = list(calm[-1] + np.cumsum(rng.normal(0, 2.5, 25)))
    _cur, pct = realized_vol_percentile(calm + storm)
    assert vol_label(pct) == "high"


def test_vol_trend_label_thresholds():
    assert vol_trend_label(25.0, 20.0) == "rising"
    assert vol_trend_label(16.0, 20.0) == "falling"
    assert vol_trend_label(20.5, 20.0) == "stable"
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest packages/ml/tests/test_regime.py -q`
Expected: FAIL (module `saalr_ml.regime` does not exist).

- [ ] **Step 3: Create** `packages/ml/saalr_ml/regime.py`:

```python
from __future__ import annotations

import numpy as np

MIN_CLOSES = 60

_DIR_TEXT = {
    "strong_bullish": "well above the 20- and 50-day averages, strong uptrend",
    "bullish": "above the 20- and 50-day averages, rising",
    "neutral": "hovering around the 20- and 50-day averages",
    "bearish": "below the 20- and 50-day averages, falling",
    "strong_bearish": "well below the 20- and 50-day averages, strong downtrend",
}
_DIR_HEAD = {"strong_bullish": "Strong bullish", "bullish": "Bullish", "neutral": "Neutral",
             "bearish": "Bearish", "strong_bearish": "Strong bearish"}
_VOL_HEAD = {"low": "Low vol", "normal": "Normal vol", "high": "High vol"}
_MOM_HEAD = {"trending": "Trending", "range_bound": "Range-bound"}


def trend_score(closes) -> float:
    c = np.asarray(closes, dtype=float)
    sma20 = float(np.mean(c[-20:]))
    sma50 = float(np.mean(c[-50:]))
    price = float(c[-1])
    blend = (np.sign(price - sma20) + np.sign(price - sma50) + np.sign(sma20 - sma50)) / 3.0
    prev20 = float(np.mean(c[-40:-20]))
    slope = (sma20 - prev20) / prev20 if prev20 else 0.0
    slope_c = max(-1.0, min(1.0, slope / 0.10))
    return float(0.4 * blend + 0.6 * slope_c)


def direction_label(t: float) -> str:
    if t >= 0.6:
        return "strong_bullish"
    if t >= 0.2:
        return "bullish"
    if t > -0.2:
        return "neutral"
    if t > -0.6:
        return "bearish"
    return "strong_bearish"


def _rolling_realized_vol(c, window: int = 20):
    logret = np.diff(np.log(c))
    out = []
    for i in range(window, len(logret) + 1):
        w = logret[i - window:i]
        out.append(float(np.std(w, ddof=1) * np.sqrt(252) * 100.0))
    return np.asarray(out, dtype=float)


def realized_vol_percentile(closes, window: int = 20, lookback: int = 252):
    c = np.asarray(closes, dtype=float)
    series = _rolling_realized_vol(c, window)
    if len(series) == 0:
        return 0.0, 1.0
    current = float(series[-1])
    tail = series[-min(lookback, len(series)):]
    pct = float(np.mean(tail <= current))
    return current, pct


def vol_label(pct: float) -> str:
    if pct > 0.66:
        return "high"
    if pct >= 0.33:
        return "normal"
    return "low"


def efficiency_ratio(closes, window: int = 20) -> float:
    c = np.asarray(closes, dtype=float)[-(window + 1):]
    net = abs(float(c[-1] - c[0]))
    path = float(np.sum(np.abs(np.diff(c))))
    return net / path if path else 0.0


def momentum_label(er: float) -> str:
    return "trending" if er >= 0.30 else "range_bound"


def vol_trend_label(garch_mean: float, realized: float) -> str:
    if garch_mean > realized * 1.10:
        return "rising"
    if garch_mean < realized * 0.90:
        return "falling"
    return "stable"


def _headline(d: str, v: str, m: str) -> str:
    return f"{_DIR_HEAD[d]} · {_VOL_HEAD[v]} · {_MOM_HEAD[m]}"


def classify_regime(closes) -> dict:
    c = np.asarray(closes, dtype=float)
    if len(c) < MIN_CLOSES:
        raise ValueError("insufficient history")
    t = trend_score(c)
    d_label = direction_label(t)
    cur_vol, pct = realized_vol_percentile(c)
    v_label = vol_label(pct)
    er = efficiency_ratio(c)
    m_label = momentum_label(er)
    return {
        "direction": {"label": d_label, "score": round(t, 4), "detail": f"price {_DIR_TEXT[d_label]}"},
        "volatility": {
            "label": v_label, "percentile": round(pct, 4), "realized_vol": round(cur_vol, 2),
            "detail": f"20-day realized vol {cur_vol:.1f}%, {round(pct * 100)}th percentile of the past year",
        },
        "momentum": {
            "label": m_label, "efficiency_ratio": round(er, 4),
            "detail": f"directional efficiency {er:.2f} — "
                      f"{'trending' if m_label == 'trending' else 'choppy / range-bound'}",
        },
        "headline": _headline(d_label, v_label, m_label),
        "last_close": round(float(c[-1]), 4),
        "n_closes": int(len(c)),
    }
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest packages/ml/tests/test_regime.py -q`
Expected: PASS (6 tests). If `test_vol_percentile_is_high_when_recent_vol_spikes` is flaky, the seed is fixed (`default_rng(0)`) so it's deterministic; the storm window's realized vol dwarfs the calm history → high.

- [ ] **Step 5: Commit**

```bash
git add packages/ml/saalr_ml/regime.py packages/ml/tests/test_regime.py
git commit -m "feat(ml): rule-based market-regime classifier (trend/vol-percentile/efficiency-ratio)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Pure scored recommender (`saalr_core/strategies/recommend.py`)

**Files:** Create `packages/core/saalr_core/strategies/recommend.py`, Test `packages/core/tests/test_recommend.py`.

- [ ] **Step 1: Write the failing test** `packages/core/tests/test_recommend.py`:

```python
from saalr_core.strategies.recommend import recommend
from saalr_core.strategies.templates import list_templates


def _regime(direction, vol, momentum="range_bound"):
    return {
        "direction": {"label": direction},
        "volatility": {"label": vol},
        "momentum": {"label": momentum},
    }


def test_returns_all_21_with_rationale():
    recs = recommend(_regime("bullish", "normal"), list_templates())
    assert len(recs) == 21
    assert all(r["rationale"] for r in recs)
    assert all({"template_key", "name", "score", "risk", "market_view"} <= set(r) for r in recs)


def test_high_vol_neutral_favors_defined_short_vol():
    recs = recommend(_regime("neutral", "high"), list_templates())
    by = {r["template_key"]: r for r in recs}
    # iron condor (neutral, short_vol, defined) beats the equivalent naked short strangle
    assert by["iron_condor"]["score"] > by["short_strangle"]["score"]
    assert by["iron_condor"]["score"] > by["short_straddle"]["score"]
    top5 = [r["template_key"] for r in recs[:5]]
    assert "iron_condor" in top5 or "iron_butterfly" in top5


def test_strong_bullish_low_vol_tops_a_bullish_structure():
    recs = recommend(_regime("strong_bullish", "low"), list_templates())
    assert recs[0]["market_view"] == "bullish"


def test_deterministic_order():
    a = [r["template_key"] for r in recommend(_regime("bullish", "normal"), list_templates())]
    b = [r["template_key"] for r in recommend(_regime("bullish", "normal"), list_templates())]
    assert a == b
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest packages/core/tests/test_recommend.py -q`
Expected: FAIL (module `saalr_core.strategies.recommend` does not exist).

- [ ] **Step 3: Create** `packages/core/saalr_core/strategies/recommend.py`:

```python
from __future__ import annotations

# How much a template's market_view is worth given the detected direction.
_DIR_POINTS = {
    "strong_bullish": {"bullish": 3, "neutral": 1, "volatile": 1, "bearish": -2},
    "bullish": {"bullish": 3, "neutral": 1, "volatile": 1, "bearish": -2},
    "neutral": {"neutral": 3, "bullish": 1, "bearish": 1, "volatile": 1},
    "bearish": {"bearish": 3, "neutral": 1, "volatile": 1, "bullish": -2},
    "strong_bearish": {"bearish": 3, "neutral": 1, "volatile": 1, "bullish": -2},
}
# How much a template's vol_view is worth given the detected volatility level.
_VOL_POINTS = {
    "high": {"short_vol": 3, "neutral": 1, "long_vol": -1},
    "low": {"long_vol": 3, "neutral": 1, "short_vol": -1},
    "normal": {"neutral": 2, "short_vol": 1, "long_vol": 1},
}

_DIR_PHRASE = {
    "strong_bullish": "a strong bullish", "bullish": "a bullish", "neutral": "a neutral",
    "bearish": "a bearish", "strong_bearish": "a strong bearish",
}


def _rationale(direction: str, vol: str, has_bonus: bool, risk: str) -> str:
    bits = [f"Fits {_DIR_PHRASE[direction]} view in {vol} vol"]
    if has_bonus:
        bits.append("aligned with momentum")
    bits.append("defined risk" if risk == "defined" else "undefined risk — size carefully")
    return "; ".join(bits) + "."


def recommend(regime: dict, templates: list[dict]) -> list[dict]:
    """Rank templates by how well their tags fit the regime, with a retail-safety bias.

    Pure: `regime` needs only direction/volatility/momentum labels; `templates` is the
    output of templates.list_templates(). Returns every template scored + a rationale,
    sorted by score desc then key asc (deterministic)."""
    direction = regime["direction"]["label"]
    vol = regime["volatility"]["label"]
    momentum = regime["momentum"]["label"]
    dpts = _DIR_POINTS[direction]
    vpts = _VOL_POINTS[vol]

    out = []
    for t in templates:
        dp = dpts.get(t["market_view"], 0)
        vp = vpts.get(t["vol_view"], 0)
        bonus = 0
        if momentum == "trending" and t["market_view"] == "volatile":
            bonus = 1
        elif momentum == "range_bound" and t["market_view"] == "neutral":
            bonus = 1
        penalty = (2 if t["risk"] == "undefined" else 0) + (1 if t["complexity"] == "advanced" else 0)
        score = dp + vp + bonus - penalty
        out.append({
            "template_key": t["key"], "name": t["name"], "score": score,
            "market_view": t["market_view"], "vol_view": t["vol_view"], "net": t["net"],
            "risk": t["risk"], "complexity": t["complexity"],
            "rationale": _rationale(direction, vol, bool(bonus), t["risk"]),
        })
    out.sort(key=lambda r: (-r["score"], r["template_key"]))
    return out
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `uv run pytest packages/core/tests/test_recommend.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/strategies/recommend.py packages/core/tests/test_recommend.py
git commit -m "feat(strategies): scored template recommender (regime tag-match + retail-safety bias)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: API endpoint (`regime/` router + service + wiring)

**Files:** Create `apps/api/saalr_api/regime/__init__.py`, `service.py`, `router.py`; Modify `packages/core/saalr_core/config.py`, `apps/api/saalr_api/main.py`; Test `tests/integration/test_regime_api.py`.

- [ ] **Step 1: Add config field** in `packages/core/saalr_core/config.py` — after the line `vol_forecast_cache_ttl_seconds: int = 21600  # 6h` add:

```python
    regime_cache_ttl_seconds: int = 3600  # 1h — regime recomputes from daily bars
```

- [ ] **Step 2: Create** `apps/api/saalr_api/regime/__init__.py` (empty file).

- [ ] **Step 3: Create** `apps/api/saalr_api/regime/service.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from saalr_core.marketdata.bars import load_closes
from saalr_core.sentiment import repo as sentiment_repo
from saalr_core.strategies.recommend import recommend
from saalr_core.strategies.templates import list_templates
from saalr_ml.forecast import vol_forecast
from saalr_ml.regime import classify_regime, vol_trend_label


async def _premium_signals(session, ticker: str, market: str, closes, realized_vol: float) -> dict:
    vol_trend = {"label": "stable", "available": False, "detail": "needs 250+ daily bars"}
    try:
        fc = vol_forecast(np.asarray(closes, dtype=float), 10)
        garch_mean = float(np.mean(fc["primary_forecast"]))
        vol_trend = {
            "label": vol_trend_label(garch_mean, realized_vol), "available": True,
            "detail": f"GARCH 10-day forecast {garch_mean:.1f}% vs realized {realized_vol:.1f}%",
        }
    except ValueError:
        pass

    srow = await sentiment_repo.latest_sentiment(session, ticker, market)
    if srow is None:
        sentiment = {"label": "neutral", "score": 0.0, "available": False,
                     "n_headlines": 0, "detail": "no recent scored headlines"}
    else:
        sentiment = {
            "label": srow["label"], "score": srow["score"], "available": True,
            "n_headlines": srow["n_headlines"],
            "detail": f"{srow['n_headlines']} headlines, score {srow['score']:+.2f}",
        }
    return {"vol_trend": vol_trend, "sentiment": sentiment}


async def get_or_compute_regime(redis, session, ticker: str, market: str,
                                has_premium: bool, ttl: int) -> dict:
    """Regime + recommendations for (ticker, market). Cache read, else load free bars,
    classify (ValueError <60 closes → caller maps 422), conditionally enrich with the
    premium layer, recommend, cache. Cache key includes the tier so a free read never
    serves premium fields and vice versa."""
    key = f"mdq:regime:v1:{market}:{ticker}:{'premium' if has_premium else 'base'}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    closes = await load_closes(session, ticker, market)
    regime = classify_regime(closes)

    if has_premium:
        regime["premium"] = await _premium_signals(
            session, ticker, market, closes, regime["volatility"]["realized_vol"])
    else:
        regime["premium"] = None
    regime["premium_available"] = has_premium

    recommendations = recommend(regime, list_templates())
    payload = {
        "ticker": ticker, "market": market,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "regime": regime, "recommendations": recommendations, "approximate": True,
    }
    await redis.set(key, json.dumps(payload), ex=ttl)
    return payload
```

- [ ] **Step 4: Create** `apps/api/saalr_api/regime/router.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal
from . import service

router = APIRouter(prefix="/v1/market", tags=["regime"])


def _validate(ticker: str, market: str) -> None:
    if not ticker or not ticker.isalpha():
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "unknown ticker"}})
    if market not in ("US",):
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": "unsupported market"}})


@router.get("/regime")
async def regime_endpoint(
    request: Request,
    ticker: str = Query(...),
    market: str = Query("US"),
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> dict:
    _validate(ticker, market)
    ticker = ticker.upper()
    session, principal = ctx
    has_premium = bool(entitlements_for(principal.tier)["ml_forecast"])
    try:
        return await service.get_or_compute_regime(
            request.app.state.redis, session, ticker, market, has_premium,
            request.app.state.regime_ttl,
        )
    except ValueError as exc:
        raise HTTPException(422, {"error": {"code": "INSUFFICIENT_HISTORY", "message": str(exc)}}) from exc
```

- [ ] **Step 5: Wire into** `apps/api/saalr_api/main.py`:
  1. Next to `from .sentiment.router import router as sentiment_router` add:
     ```python
     from .regime.router import router as regime_router
     ```
  2. After the line `app.state.vol_forecast_ttl = settings.vol_forecast_cache_ttl_seconds` add:
     ```python
     app.state.regime_ttl = settings.regime_cache_ttl_seconds
     ```
  3. After `app.include_router(sentiment_router)` add:
     ```python
     app.include_router(regime_router)
     ```

- [ ] **Step 6: Write the integration test** `tests/integration/test_regime_api.py`:

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
        vol = 0.01
        for i in range(n):
            vol = 0.9 * vol + 0.1 * (0.01 + 0.02 * (i % 7 == 0))
            step = math.sin(i * 0.3) * vol + (0.0008 if i % 2 else -0.0003)
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


async def test_regime_free_tier_base_only(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rg-free@x.com"}
            await c.get("/me", headers=h)
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/regime?ticker=AAPL", headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ticker"] == "AAPL"
            assert body["regime"]["premium_available"] is False
            assert body["regime"]["premium"] is None
            assert body["regime"]["direction"]["label"] in (
                "strong_bullish", "bullish", "neutral", "bearish", "strong_bearish")
            assert len(body["recommendations"]) == 21
            assert "·" in body["regime"]["headline"]


async def test_regime_pro_tier_has_premium_layer(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rg-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "MSFT", n=300)
            r = await c.get("/v1/market/regime?ticker=MSFT", headers=h)
            assert r.status_code == 200, r.text
            prem = r.json()["regime"]["premium"]
            assert prem is not None
            assert "vol_trend" in prem and "sentiment" in prem
            assert prem["vol_trend"]["available"] is True  # 300 bars >= 250


async def test_regime_insufficient_history_is_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rg-thin@x.com"}
            await c.get("/me", headers=h)
            await _seed_bars(admin_engine, "TINY", n=40)  # < 60
            r = await c.get("/v1/market/regime?ticker=TINY", headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "INSUFFICIENT_HISTORY"


async def test_regime_non_alpha_ticker_is_404(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rg-bad@x.com"}
            await c.get("/me", headers=h)
            r = await c.get("/v1/market/regime?ticker=123", headers=h)
            assert r.status_code == 404
```

- [ ] **Step 7: Run the tests**

Run (engine + new API; the integration test needs DB on 55432):
- `uv run pytest packages/ml/tests/test_regime.py packages/core/tests/test_recommend.py -q` → green.
- `uv run pytest tests/integration/test_regime_api.py -q` → green **if** Postgres is on 55432 (override `APP_DATABASE_URL`/`ADMIN_DATABASE_URL`). If the DB isn't available locally, this is expected to error on connection like other DB-backed tests — proceed; the live smoke in the final gate exercises it.

- [ ] **Step 8: Commit**

```bash
git add packages/core/saalr_core/config.py apps/api/saalr_api/regime/ apps/api/saalr_api/main.py tests/integration/test_regime_api.py
git commit -m "feat(api): GET /v1/market/regime — ungated base + premium GARCH/sentiment layer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Web — Trade Ideas screen (`/app/ideas`)

**Files:** Create `apps/web/src/lib/regime.ts`, `apps/web/src/features/ideas/hooks.ts`, `RegimePanel.tsx`, `RecoCard.tsx`, `apps/web/src/pages/Ideas.tsx`, `apps/web/src/pages/Ideas.test.tsx`; Modify `apps/web/src/app/Router.tsx`, `apps/web/src/components/Sidebar.tsx`, `apps/web/src/pages/Strategies.tsx`.

- [ ] **Step 1: Create** `apps/web/src/lib/regime.ts`:

```ts
import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'

export type Direction = 'strong_bullish' | 'bullish' | 'neutral' | 'bearish' | 'strong_bearish'
export type VolLevel = 'low' | 'normal' | 'high'
export type Momentum = 'trending' | 'range_bound'

export interface Signal { label: string; detail: string }
export interface PremiumSignal { label: string; available: boolean; detail: string; score?: number; n_headlines?: number }
export interface PremiumSignals { vol_trend: PremiumSignal; sentiment: PremiumSignal }

export interface Regime {
  direction: Signal & { score: number }
  volatility: Signal & { percentile: number; realized_vol: number }
  momentum: Signal & { efficiency_ratio: number }
  headline: string
  last_close: number
  n_closes: number
  premium_available: boolean
  premium: PremiumSignals | null
}

export interface Recommendation {
  template_key: string
  name: string
  score: number
  market_view: string
  vol_view: string
  net: string
  risk: string
  complexity: string
  rationale: string
}

export interface RegimeResponse {
  ticker: string
  market: string
  as_of: string
  approximate: boolean
  regime: Regime
  recommendations: Recommendation[]
}

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: { ...authHeaders() } })
  if (res.status === 401) {
    setToken(null)
    throw new Error('unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail?.error?.code ?? `request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export function getRegime(ticker: string, market = 'US'): Promise<RegimeResponse> {
  return request(`/v1/market/regime?ticker=${encodeURIComponent(ticker)}&market=${market}`)
}
```

- [ ] **Step 2: Create** `apps/web/src/features/ideas/hooks.ts`:

```ts
import { useQuery } from '@tanstack/react-query'
import { getRegime, type RegimeResponse } from '../../lib/regime'

export function useRegime(ticker: string | null) {
  return useQuery<RegimeResponse>({
    queryKey: ['regime', ticker],
    queryFn: () => getRegime(ticker!),
    enabled: !!ticker,
    retry: false,
  })
}
```

- [ ] **Step 3: Create** `apps/web/src/features/ideas/RegimePanel.tsx`:

```tsx
import type { Regime } from '../../lib/regime'

const PRETTY: Record<string, string> = {
  strong_bullish: 'Strong bullish', bullish: 'Bullish', neutral: 'Neutral',
  bearish: 'Bearish', strong_bearish: 'Strong bearish',
  low: 'Low', normal: 'Normal', high: 'High',
  trending: 'Trending', range_bound: 'Range-bound',
  rising: 'Rising', falling: 'Falling', stable: 'Stable',
}
const pretty = (s: string) => PRETTY[s] ?? s

function Cell({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-3">
      <p className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">{label}</p>
      <p className="mt-1 text-sm font-semibold text-txt">{value}</p>
      <p className="mt-1 text-[11px] leading-snug text-txtDim">{detail}</p>
    </div>
  )
}

export function RegimePanel({ regime }: { regime: Regime }) {
  return (
    <div className="space-y-3" data-testid="regime-panel">
      <p className="text-lg font-semibold tracking-tight" data-testid="regime-headline">{regime.headline}</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Cell label="Direction" value={pretty(regime.direction.label)} detail={regime.direction.detail} />
        <Cell label="Volatility" value={pretty(regime.volatility.label)} detail={regime.volatility.detail} />
        <Cell label="Momentum" value={pretty(regime.momentum.label)} detail={regime.momentum.detail} />
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {regime.premium_available && regime.premium ? (
          <>
            <Cell label="Vol trend · premium" value={pretty(regime.premium.vol_trend.label)} detail={regime.premium.vol_trend.detail} />
            <Cell label="Sentiment · premium" value={pretty(regime.premium.sentiment.label)} detail={regime.premium.sentiment.detail} />
          </>
        ) : (
          <a
            href="/app/billing"
            data-testid="regime-upgrade"
            className="rounded-lg border border-dashed border-line bg-panel2 p-3 text-[11px] text-txtDim transition-colors hover:text-txt sm:col-span-2"
          >
            Unlock GARCH vol-trend + news sentiment with a Pro or Premium plan →
          </a>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create** `apps/web/src/features/ideas/RecoCard.tsx`:

```tsx
import type React from 'react'
import type { Recommendation } from '../../lib/regime'

function Badge({ children, tone }: { children: React.ReactNode; tone?: 'warn' }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide ${
        tone === 'warn' ? 'bg-warn/15 text-warn' : 'border border-lineSoft text-txtFaint'
      }`}
    >
      {children}
    </span>
  )
}

export function RecoCard({
  reco, onApply, applying,
}: {
  reco: Recommendation; onApply: (key: string) => void; applying: boolean
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line bg-panel p-3" data-testid={`reco-${reco.template_key}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium text-txt">{reco.name}</span>
        <span className="tnum font-mono text-[10px] text-txtFaint">score {reco.score}</span>
      </div>
      <p className="text-[11px] leading-snug text-txtDim">{reco.rationale}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge>{reco.net}</Badge>
        <Badge tone={reco.risk === 'undefined' ? 'warn' : undefined}>
          {reco.risk === 'undefined' ? 'undefined risk' : 'defined risk'}
        </Badge>
        <button
          data-testid={`reco-apply-${reco.template_key}`}
          onClick={() => onApply(reco.template_key)}
          disabled={applying}
          className="ml-auto rounded-md bg-accent px-3 py-1 text-[11px] font-medium text-canvas transition hover:opacity-90 disabled:opacity-40"
        >
          {applying ? "Opening…" : "Apply"}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Write the failing page test** `apps/web/src/pages/Ideas.test.tsx`:

```tsx
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Ideas } from './Ideas'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const REGIME = {
  ticker: 'SPY', market: 'US', as_of: 'x', approximate: true,
  regime: {
    direction: { label: 'bullish', score: 0.4, detail: 'rising' },
    volatility: { label: 'normal', percentile: 0.5, realized_vol: 18, detail: 'mid' },
    momentum: { label: 'trending', efficiency_ratio: 0.4, detail: 'trend' },
    headline: 'Bullish · Normal vol · Trending', last_close: 585, n_closes: 800,
    premium_available: false, premium: null,
  },
  recommendations: [
    { template_key: 'bull_put_spread', name: 'Bull Put Spread', score: 7, market_view: 'bullish',
      vol_view: 'short_vol', net: 'credit', risk: 'defined', complexity: 'beginner', rationale: 'Fits a bullish view.' },
  ],
}

function stub() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).includes('/v1/market/regime')) return new Response(JSON.stringify(REGIME), { status: 200 })
    if (String(url).includes('/templates/bull_put_spread/build'))
      return new Response(JSON.stringify({ underlying: 'SPY', legs: [] }), { status: 200 })
    return new Response('{}', { status: 200 })
  }))
}

describe('Ideas', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('shows the regime, recommendations, and an upgrade nudge for free users', async () => {
    stub()
    render(wrap(<Ideas />))
    fireEvent.change(screen.getByTestId('idea-ticker'), { target: { value: 'SPY' } })
    fireEvent.click(screen.getByTestId('idea-go'))
    await waitFor(() => expect(screen.getByTestId('regime-panel')).toBeInTheDocument())
    expect(screen.getByTestId('regime-headline').textContent).toContain('Bullish')
    expect(screen.getByTestId('reco-bull_put_spread')).toBeInTheDocument()
    expect(screen.getByTestId('regime-upgrade')).toBeInTheDocument()
  })

  it('Apply builds the chosen template', async () => {
    stub()
    render(wrap(<Ideas />))
    fireEvent.change(screen.getByTestId('idea-ticker'), { target: { value: 'SPY' } })
    fireEvent.click(screen.getByTestId('idea-go'))
    await screen.findByTestId('reco-apply-bull_put_spread')
    fireEvent.click(screen.getByTestId('reco-apply-bull_put_spread'))
    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls
      expect(calls.some((c) => String(c[0]).includes('/templates/bull_put_spread/build'))).toBe(true)
    })
  })
})
```

- [ ] **Step 6: Run the test, verify it fails**

Run (from `apps/web`): `npx vitest run src/pages/Ideas.test.tsx`
Expected: FAIL (`Ideas` not defined).

- [ ] **Step 7: Create** `apps/web/src/pages/Ideas.tsx`:

```tsx
import type React from 'react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRegime } from '../features/ideas/hooks'
import { RegimePanel } from '../features/ideas/RegimePanel'
import { RecoCard } from '../features/ideas/RecoCard'
import { buildTemplate } from '../lib/strategies'

function defaultExpiry(): string {
  const d = new Date()
  d.setDate(d.getDate() + 35)
  return d.toISOString().slice(0, 10)
}

export function Ideas() {
  const [input, setInput] = useState('')
  const [ticker, setTicker] = useState<string | null>(null)
  const [applyingKey, setApplyingKey] = useState<string | null>(null)
  const q = useRegime(ticker)
  const navigate = useNavigate()
  const data = q.data

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const t = input.trim().toUpperCase()
    if (t) setTicker(t)
  }

  async function apply(key: string) {
    if (!data) return
    setApplyingKey(key)
    try {
      const config = await buildTemplate(key, {
        underlying: data.ticker, expiry: defaultExpiry(), atm_strike: data.regime.last_close,
      })
      navigate('/strategies', { state: { config } })
    } finally {
      setApplyingKey(null)
    }
  }

  const recos = data?.recommendations ?? []

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Trade Ideas</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Regime &amp; ideas</h2>
      </div>

      <form onSubmit={submit} className="flex items-center gap-2">
        <input
          data-testid="idea-ticker"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ticker (e.g. SPY)"
          className="rounded-lg border border-line bg-panel px-3 py-2 font-mono text-sm uppercase text-txt"
        />
        <button data-testid="idea-go" type="submit" className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas hover:opacity-90">
          Analyze
        </button>
      </form>

      {q.isLoading && <p data-testid="idea-loading" className="text-sm text-txtDim">Reading the tape…</p>}
      {q.isError && (
        <p data-testid="idea-error" className="text-sm text-neg">
          {String((q.error as Error).message) === "INSUFFICIENT_HISTORY"
            ? "Not enough price history for this ticker yet."
            : "Couldn’t analyze that ticker."}
        </p>
      )}

      {data && (
        <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]">
          <RegimePanel regime={data.regime} />
          <div className="space-y-2">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtFaint">Recommended for this regime</p>
            {recos.slice(0, 5).map((r) => (
              <RecoCard key={r.template_key} reco={r} onApply={apply} applying={applyingKey === r.template_key} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 8: Add the route** in `apps/web/src/app/Router.tsx` — add `import { Ideas } from '../pages/Ideas'` with the other page imports, and `<Route path="ideas" element={<Ideas />} />` immediately after the `strategies` route line.

- [ ] **Step 9: Add the nav entry** in `apps/web/src/components/Sidebar.tsx` — in the `'Learn & Research'` section's `items` array, add `['/ideas', 'Trade Ideas'],` as the first item (before `['/research', 'Research Agent']`).

- [ ] **Step 10: Apply-landing** in `apps/web/src/pages/Strategies.tsx`:
  1. Change the first import to: `import { useEffect, useState } from 'react'`.
  2. Add `import { useLocation } from 'react-router-dom'` near the top imports.
  3. Inside `Strategies()`, after the existing `useState` hooks (e.g. after `const [saved, setSaved] = useState(false)`), add:
     ```tsx
     const location = useLocation()
     useEffect(() => {
       const incoming = (location.state as { config?: StrategyConfig } | null)?.config
       if (incoming) {
         setConfig(incoming)
         setTab('build')
       }
       // eslint-disable-next-line react-hooks/exhaustive-deps
     }, [location.state])
     ```
     (`StrategyConfig` is already imported in `Strategies.tsx`; if not, add it to the `../lib/strategies` import.)

- [ ] **Step 11: Run the test + gate**

Run (from `apps/web`):
- `npx vitest run src/pages/Ideas.test.tsx` → 2 passed.
- `npm run typecheck` → clean.
- `npm run lint` → clean.

- [ ] **Step 12: Commit**

```bash
git add apps/web/src/lib/regime.ts apps/web/src/features/ideas/ apps/web/src/pages/Ideas.tsx apps/web/src/pages/Ideas.test.tsx apps/web/src/app/Router.tsx apps/web/src/components/Sidebar.tsx apps/web/src/pages/Strategies.tsx
git commit -m "feat(web): Trade Ideas screen (/app/ideas) — regime panel + ranked recommendations + Apply

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Final gate

- [ ] **Step 1: Python** — `uv run pytest packages/ml/tests/test_regime.py packages/core/tests/test_recommend.py packages/core/tests/ -q` → green (regime + recommend + unaffected core). Integration: `uv run pytest tests/integration/test_regime_api.py -q` if Postgres is on 55432.
- [ ] **Step 2: Web** — from `apps/web`: `npm run typecheck && npm run lint && npm run test:run` → green (+~8 tests). `npm run build` → still "47 HTML documents pre-rendered" (`/app/ideas` is client-only).
- [ ] **Step 3 (optional, local stack running): live SPY smoke** — restart the API to pick up the new router (editable install), then `GET /v1/market/regime?ticker=SPY` with a dev token (SPY has 800+ bars): confirm a regime + 21 recommendations come back; with a premium token confirm `regime.premium.vol_trend.available` is true. (See [[local-postgres-port-conflict]] for the 55432 restart override.)

---

## Self-Review notes (for the executor)

- **No circular import:** `recommend.py` lives in `saalr-core` and takes plain dicts; `regime.py` (numpy) lives in `saalr-ml` (which depends on core, not vice-versa); the API service imports both. `saalr-ml` is a root + saalr-api dep, so `uv run pytest` and the API both import it.
- **JSON-safe:** `classify_regime` casts every numpy scalar via `round()`/`float()`/`int()`, so the payload serializes without a custom encoder.
- **Cache key includes the tier** (`:premium`/`:base`) so a free read never serves premium fields and an upgrade is reflected on the next call.
- **Premium degrades, never fails:** GARCH `vol_forecast` raises `ValueError` under 250 closes → `vol_trend.available=false`; a missing sentiment row → `sentiment.available=false`. Neither aborts the request.
- **Apply handoff:** `Ideas` builds the `StrategyConfig` (existing `buildTemplate` endpoint) and passes it via `navigate('/strategies', { state: { config } })`; `Strategies` reads `location.state.config` once on mount and loads it into the builder. Refreshing `/strategies` loses the state (acceptable for a deep-link).
- **Recommender scoring is unit-pinned:** for a high-vol neutral regime, iron condor/iron butterfly (neutral+short_vol, defined) outscore the naked short straddle/strangle (same fit − 3 safety penalty), which is the retail-safety bias the spec requires.
- **Endpoint is ungated** (`get_principal`, not `require_*`); the premium branch keys off `entitlements_for(tier)["ml_forecast"]` (Pro + Premium).
