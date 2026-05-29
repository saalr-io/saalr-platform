# Greeks calculator + vol surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a vendor-independent Black-Scholes-Merton options engine plus two Pro-gated API endpoints (`/v1/market/iv-surface`, `/v1/market/chain`) backed by live Massive data and a FRED tenor-matched risk-free curve, persisting fetched chains into TimescaleDB.

**Architecture:** A pure-math engine (`saalr_core/pricing/`, stdlib only) computes price/Greeks/IV. A vendor-I/O layer (`saalr_core/marketdata/`) wraps Massive (chains) and FRED (rates) behind protocols, quarantining all vendor JSON. A thin API layer (`saalr_api/market/`) authenticates, gates on the `vol_surface` entitlement, orchestrates fetch→compute→persist→cache, and shapes responses. Pure parsing/math is unit-tested offline against fixtures; live calls are exercised only by env-gated smoke tests.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (asyncpg), Redis, httpx (new core dep), pytest/pytest-asyncio. BSM uses stdlib `math` only (no numpy/scipy).

**Spec:** `docs/superpowers/specs/2026-05-30-greeks-vol-surface-design.md`

---

## File structure

```
packages/core/saalr_core/pricing/
  __init__.py            # re-exports public types + BSMModel
  types.py               # OptionKind, OptionParams, Greeks, ContractGreeks
  greeks.py              # _d1_d2, _norm_cdf/_norm_pdf, price, delta, gamma, vega, theta, rho
  model.py               # PricingModel Protocol, BSMModel
  iv.py                  # implied_vol (Newton + bisection)
  surface.py             # build_surface
packages/core/saalr_core/marketdata/
  __init__.py
  types.py               # RawContract, RawChain, YieldCurve
  provider.py            # MarketDataProvider, RiskFreeRateProvider Protocols
  massive.py             # parse_snapshot (pure), MassiveProvider
  rates.py               # parse_observations (pure), FredRateProvider
packages/core/saalr_core/config.py            # MODIFY: add 4 settings
packages/core/pyproject.toml                  # MODIFY: add httpx
packages/core/tests/                          # NEW unit tests (pricing + marketdata parsing)
  test_pricing_greeks.py
  test_pricing_iv.py
  test_pricing_surface.py
  test_marketdata_rates.py
  test_marketdata_massive.py
  fixtures/massive_snapshot.json
  fixtures/massive_snapshot_page2.json
  fixtures/fred_dgs3mo.json
apps/api/saalr_api/market/
  __init__.py
  gating.py              # require_vol_surface dependency
  snapshots.py           # persist_chain (upsert into options_chain_snapshots)
  service.py             # MarketService: fetch -> compute -> persist -> cache
  router.py              # APIRouter(prefix="/v1/market")
apps/api/saalr_api/main.py                    # MODIFY: construct providers in lifespan, include router
apps/api/pyproject.toml                       # MODIFY: ensure httpx available (via saalr-core)
.env.example                                  # MODIFY: new keys
tests/integration/test_market.py              # NEW API integration tests
tests/integration/test_market_smoke.py        # NEW env-gated live smoke tests
scripts/orchestrate.ps1                       # MODIFY: append slice tasks (optional autonomous run)
```

---

## Task 1: Config + dependency for the slice

**Files:**
- Modify: `packages/core/saalr_core/config.py`
- Modify: `packages/core/pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add settings**

In `packages/core/saalr_core/config.py`, add these fields to `Settings` (after `web_base_url`):

```python
    # Market data (Greeks/vol surface slice)
    massive_api_key: str | None = None
    fred_api_key: str | None = None
    risk_free_rate_fallback: float = 0.05
    vol_surface_cache_ttl_seconds: int = 21600  # 6h, per HLD
```

- [ ] **Step 2: Add httpx dependency**

In `packages/core/pyproject.toml`, add to `dependencies`:

```toml
  "httpx>=0.27",
```

- [ ] **Step 3: Document env keys**

Append to `.env.example`:

```
# Market data
MASSIVE_API_KEY=
FRED_API_KEY=
RISK_FREE_RATE_FALLBACK=0.05
VOL_SURFACE_CACHE_TTL_SECONDS=21600
```

- [ ] **Step 4: Sync + verify import**

Run: `uv sync`
Run: `uv run python -c "from saalr_core.config import get_settings; print(get_settings().vol_surface_cache_ttl_seconds)"`
Expected: `21600`

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/config.py packages/core/pyproject.toml .env.example uv.lock
git commit -m "feat(market): config + httpx dep for greeks/vol-surface slice"
```

---

## Task 2: Pricing types

**Files:**
- Create: `packages/core/saalr_core/pricing/__init__.py`
- Create: `packages/core/saalr_core/pricing/types.py`

- [ ] **Step 1: Create the package init (empty for now)**

Create `packages/core/saalr_core/pricing/__init__.py`:

```python
```

- [ ] **Step 2: Create types**

Create `packages/core/saalr_core/pricing/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OptionKind(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


@dataclass(frozen=True)
class OptionParams:
    """Inputs to a pricing model. Rates/yields are decimals (0.05 = 5%); t_years in years."""

    spot: float
    strike: float
    t_years: float
    rate: float
    sigma: float
    div_yield: float
    kind: OptionKind


@dataclass(frozen=True)
class Greeks:
    """Per trader conventions: theta per calendar day, vega per 1 vol point (0.01),
    rho per 1 rate point (0.01). delta/gamma are raw."""

    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    iv: float | None = None


@dataclass(frozen=True)
class ContractGreeks:
    """A single option contract: market quote + OUR computed numbers + the VENDOR's."""

    expiry: str  # ISO date YYYY-MM-DD
    strike: float
    kind: OptionKind
    bid: float | None
    ask: float | None
    last: float | None
    volume: int | None
    open_interest: int | None
    ours: Greeks
    vendor_iv: float | None
    vendor_delta: float | None
    vendor_gamma: float | None
    vendor_theta: float | None
    vendor_vega: float | None
```

- [ ] **Step 3: Verify import**

Run: `uv run python -c "from saalr_core.pricing.types import OptionParams, OptionKind, Greeks, ContractGreeks; print(OptionKind.CALL.value)"`
Expected: `CALL`

- [ ] **Step 4: Commit**

```bash
git add packages/core/saalr_core/pricing/
git commit -m "feat(pricing): option/greeks/contract dataclasses"
```

---

## Task 3: BSM price + put-call parity

**Files:**
- Create: `packages/core/saalr_core/pricing/greeks.py`
- Test: `packages/core/tests/test_pricing_greeks.py`

- [ ] **Step 1: Write failing tests for price + parity**

Create `packages/core/tests/test_pricing_greeks.py`:

```python
import math

from saalr_core.pricing.greeks import price
from saalr_core.pricing.types import OptionKind, OptionParams


def _p(kind, sigma=0.2, t=1.0, r=0.05, q=0.0, s=100.0, k=100.0):
    return OptionParams(spot=s, strike=k, t_years=t, rate=r, sigma=sigma, div_yield=q, kind=kind)


def test_call_price_hull_textbook():
    # Hull: S=42, K=40, r=0.10, sigma=0.20, T=0.5 -> call ~= 4.759
    p = OptionParams(42, 40, 0.5, 0.10, 0.20, 0.0, OptionKind.CALL)
    assert math.isclose(price(p), 4.759, abs_tol=1e-3)


def test_put_price_hull_textbook():
    # Same inputs -> put ~= 0.808
    p = OptionParams(42, 40, 0.5, 0.10, 0.20, 0.0, OptionKind.PUT)
    assert math.isclose(price(p), 0.808, abs_tol=1e-3)


def test_put_call_parity():
    # C - P = S*e^{-qT} - K*e^{-rT}
    c = price(_p(OptionKind.CALL, q=0.02))
    pp = price(_p(OptionKind.PUT, q=0.02))
    lhs = c - pp
    rhs = 100.0 * math.exp(-0.02 * 1.0) - 100.0 * math.exp(-0.05 * 1.0)
    assert math.isclose(lhs, rhs, abs_tol=1e-9)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd packages/core && uv run pytest tests/test_pricing_greeks.py -q`
Expected: FAIL with `ModuleNotFoundError`/`ImportError` for `price`.

- [ ] **Step 3: Implement price + normal helpers**

Create `packages/core/saalr_core/pricing/greeks.py`:

```python
from __future__ import annotations

import math

from .types import Greeks, OptionKind, OptionParams

_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _d1_d2(p: OptionParams) -> tuple[float, float]:
    vt = p.sigma * math.sqrt(p.t_years)
    d1 = (math.log(p.spot / p.strike) + (p.rate - p.div_yield + 0.5 * p.sigma**2) * p.t_years) / vt
    return d1, d1 - vt


def price(p: OptionParams) -> float:
    d1, d2 = _d1_d2(p)
    disc_q = math.exp(-p.div_yield * p.t_years)
    disc_r = math.exp(-p.rate * p.t_years)
    if p.kind is OptionKind.CALL:
        return p.spot * disc_q * _norm_cdf(d1) - p.strike * disc_r * _norm_cdf(d2)
    return p.strike * disc_r * _norm_cdf(-d2) - p.spot * disc_q * _norm_cdf(-d1)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/core && uv run pytest tests/test_pricing_greeks.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/pricing/greeks.py packages/core/tests/test_pricing_greeks.py
git commit -m "feat(pricing): BSM price + put-call parity"
```

---

## Task 4: BSM Greeks (verified against finite differences)

**Files:**
- Modify: `packages/core/saalr_core/pricing/greeks.py`
- Modify: `packages/core/tests/test_pricing_greeks.py`

- [ ] **Step 1: Add failing finite-difference tests**

Append to `packages/core/tests/test_pricing_greeks.py`:

```python
from saalr_core.pricing.greeks import greeks
from dataclasses import replace


def _fd(p, attr, h, fn):
    up = replace(p, **{attr: getattr(p, attr) + h})
    dn = replace(p, **{attr: getattr(p, attr) - h})
    return (fn(up) - fn(dn)) / (2 * h)


def test_delta_matches_fd():
    p = _p(OptionKind.CALL, q=0.01)
    g = greeks(p)
    assert math.isclose(g.delta, _fd(p, "spot", 1e-4, price), abs_tol=1e-4)


def test_gamma_matches_fd():
    p = _p(OptionKind.CALL, q=0.01)
    g = greeks(p)
    fd2 = (price(replace(p, spot=p.spot + 1e-2)) - 2 * price(p) + price(replace(p, spot=p.spot - 1e-2))) / 1e-4
    assert math.isclose(g.gamma, fd2, abs_tol=1e-3)


def test_vega_matches_fd_per_vol_point():
    p = _p(OptionKind.CALL, q=0.01)
    g = greeks(p)
    raw = _fd(p, "sigma", 1e-4, price)  # dPrice/dSigma (per 1.0)
    assert math.isclose(g.vega, raw / 100.0, abs_tol=1e-4)


def test_theta_matches_fd_per_day():
    p = _p(OptionKind.PUT, q=0.01)
    g = greeks(p)
    # dPrice/dT is sensitivity to increasing maturity; theta is decay = -that, per day
    dprice_dT = _fd(p, "t_years", 1e-4, price)
    assert math.isclose(g.theta, -dprice_dT / 365.0, abs_tol=1e-3)


def test_rho_matches_fd_per_rate_point():
    p = _p(OptionKind.CALL, q=0.01)
    g = greeks(p)
    raw = _fd(p, "rate", 1e-5, price)  # dPrice/dRate (per 1.0)
    assert math.isclose(g.rho, raw / 100.0, abs_tol=1e-3)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd packages/core && uv run pytest tests/test_pricing_greeks.py -q`
Expected: FAIL — `greeks` not defined.

- [ ] **Step 3: Implement greeks()**

Append to `packages/core/saalr_core/pricing/greeks.py`:

```python
def greeks(p: OptionParams) -> Greeks:
    d1, d2 = _d1_d2(p)
    disc_q = math.exp(-p.div_yield * p.t_years)
    disc_r = math.exp(-p.rate * p.t_years)
    sqrt_t = math.sqrt(p.t_years)
    pdf_d1 = _norm_pdf(d1)

    gamma = disc_q * pdf_d1 / (p.spot * p.sigma * sqrt_t)
    vega_raw = p.spot * disc_q * pdf_d1 * sqrt_t  # per 1.0 sigma
    common_theta = -(p.spot * disc_q * pdf_d1 * p.sigma) / (2 * sqrt_t)

    if p.kind is OptionKind.CALL:
        delta = disc_q * _norm_cdf(d1)
        theta_year = (
            common_theta
            - p.rate * p.strike * disc_r * _norm_cdf(d2)
            + p.div_yield * p.spot * disc_q * _norm_cdf(d1)
        )
        rho_raw = p.strike * p.t_years * disc_r * _norm_cdf(d2)  # per 1.0 rate
    else:
        delta = -disc_q * _norm_cdf(-d1)
        theta_year = (
            common_theta
            + p.rate * p.strike * disc_r * _norm_cdf(-d2)
            - p.div_yield * p.spot * disc_q * _norm_cdf(-d1)
        )
        rho_raw = -p.strike * p.t_years * disc_r * _norm_cdf(-d2)

    return Greeks(
        price=price(p),
        delta=delta,
        gamma=gamma,
        theta=theta_year / 365.0,
        vega=vega_raw / 100.0,
        rho=rho_raw / 100.0,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/core && uv run pytest tests/test_pricing_greeks.py -q`
Expected: all passed (3 + 5).

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/pricing/greeks.py packages/core/tests/test_pricing_greeks.py
git commit -m "feat(pricing): BSM greeks verified vs finite differences"
```

---

## Task 5: PricingModel interface + BSMModel

**Files:**
- Create: `packages/core/saalr_core/pricing/model.py`
- Modify: `packages/core/saalr_core/pricing/__init__.py`
- Test: extend `packages/core/tests/test_pricing_greeks.py`

- [ ] **Step 1: Add failing test for the model wrapper**

Append to `packages/core/tests/test_pricing_greeks.py`:

```python
from saalr_core.pricing.model import BSMModel


def test_bsm_model_delegates():
    m = BSMModel()
    p = _p(OptionKind.CALL)
    assert m.name == "bsm"
    assert math.isclose(m.price(p), price(p), abs_tol=1e-12)
    assert math.isclose(m.greeks(p).delta, greeks(p).delta, abs_tol=1e-12)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd packages/core && uv run pytest tests/test_pricing_greeks.py::test_bsm_model_delegates -q`
Expected: FAIL — `model` import error.

- [ ] **Step 3: Implement model.py**

Create `packages/core/saalr_core/pricing/model.py`:

```python
from __future__ import annotations

from typing import Protocol

from . import greeks as _g
from . import iv as _iv
from .types import Greeks, OptionParams


class PricingModel(Protocol):
    name: str

    def price(self, p: OptionParams) -> float: ...
    def greeks(self, p: OptionParams) -> Greeks: ...
    def implied_vol(self, market_price: float, p: OptionParams) -> float | None: ...


class BSMModel:
    name = "bsm"

    def price(self, p: OptionParams) -> float:
        return _g.price(p)

    def greeks(self, p: OptionParams) -> Greeks:
        return _g.greeks(p)

    def implied_vol(self, market_price: float, p: OptionParams) -> float | None:
        return _iv.implied_vol(market_price, p)
```

> Note: `model.py` imports `iv`, created in Task 6. If executing strictly in order, do Task 6 before running this module's `implied_vol` path; `price`/`greeks` work immediately.

- [ ] **Step 4: Update package exports**

Replace `packages/core/saalr_core/pricing/__init__.py` with:

```python
from .model import BSMModel, PricingModel
from .types import ContractGreeks, Greeks, OptionKind, OptionParams

__all__ = [
    "BSMModel",
    "PricingModel",
    "ContractGreeks",
    "Greeks",
    "OptionKind",
    "OptionParams",
]
```

- [ ] **Step 5: Commit** (run after Task 6 so imports resolve)

```bash
git add packages/core/saalr_core/pricing/model.py packages/core/saalr_core/pricing/__init__.py
git commit -m "feat(pricing): PricingModel protocol + BSMModel"
```

---

## Task 6: Implied volatility solver

**Files:**
- Create: `packages/core/saalr_core/pricing/iv.py`
- Test: `packages/core/tests/test_pricing_iv.py`

- [ ] **Step 1: Write failing tests**

Create `packages/core/tests/test_pricing_iv.py`:

```python
import math

from saalr_core.pricing.greeks import price
from saalr_core.pricing.iv import implied_vol
from saalr_core.pricing.types import OptionKind, OptionParams


def _params(sigma, kind=OptionKind.CALL, s=100.0, k=100.0, t=0.5, r=0.03, q=0.0):
    return OptionParams(s, k, t, r, sigma, q, kind)


def test_round_trip_atm():
    p = _params(0.25)
    mkt = price(p)
    assert math.isclose(implied_vol(mkt, p), 0.25, abs_tol=1e-4)


def test_round_trip_deep_otm_uses_bisection():
    p = _params(0.6, k=160.0)  # far OTM call, low vega -> Newton struggles
    mkt = price(p)
    iv = implied_vol(mkt, p)
    assert iv is not None and math.isclose(iv, 0.6, abs_tol=1e-3)


def test_below_intrinsic_returns_none():
    p = _params(0.25, kind=OptionKind.CALL, s=120.0, k=100.0)
    intrinsic = 120.0 * math.exp(-0.0 * 0.5) - 100.0 * math.exp(-0.03 * 0.5)
    assert implied_vol(intrinsic - 1.0, p) is None


def test_expired_returns_none():
    p = _params(0.25, t=0.0)
    assert implied_vol(5.0, p) is None


def test_non_positive_price_returns_none():
    p = _params(0.25)
    assert implied_vol(0.0, p) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd packages/core && uv run pytest tests/test_pricing_iv.py -q`
Expected: FAIL — `iv` import error.

- [ ] **Step 3: Implement the solver**

Create `packages/core/saalr_core/pricing/iv.py`:

```python
from __future__ import annotations

import math
from dataclasses import replace

from .greeks import _norm_pdf, price
from .types import OptionKind, OptionParams

_LO, _HI = 1e-4, 5.0
_MAX_ITER = 100
_TOL = 1e-6


def _vega_raw(p: OptionParams) -> float:
    vt = p.sigma * math.sqrt(p.t_years)
    d1 = (math.log(p.spot / p.strike) + (p.rate - p.div_yield + 0.5 * p.sigma**2) * p.t_years) / vt
    return p.spot * math.exp(-p.div_yield * p.t_years) * _norm_pdf(d1) * math.sqrt(p.t_years)


def implied_vol(market_price: float, p: OptionParams) -> float | None:
    """Return implied volatility, or None when uncomputable (honest failure)."""
    if p.t_years <= 0 or market_price <= 0 or p.spot <= 0 or p.strike <= 0:
        return None

    disc_q = math.exp(-p.div_yield * p.t_years)
    disc_r = math.exp(-p.rate * p.t_years)
    fwd = p.spot * disc_q
    if p.kind is OptionKind.CALL:
        lo_bound, hi_bound = max(0.0, fwd - p.strike * disc_r), fwd
    else:
        lo_bound, hi_bound = max(0.0, p.strike * disc_r - fwd), p.strike * disc_r
    if market_price < lo_bound - _TOL or market_price > hi_bound + _TOL:
        return None  # violates no-arbitrage bounds

    def diff(sigma: float) -> float:
        return price(replace(p, sigma=sigma)) - market_price

    # Newton-Raphson, seeded at 0.2
    sigma = 0.2
    for _ in range(_MAX_ITER):
        f = diff(sigma)
        if abs(f) < _TOL:
            return sigma
        v = _vega_raw(replace(p, sigma=sigma))
        if v < 1e-8:
            break  # vega too small -> hand off to bisection
        step = f / v
        nxt = sigma - step
        if nxt <= _LO or nxt >= _HI or math.isnan(nxt):
            break
        sigma = nxt

    # Bisection fallback on [_LO, _HI]
    lo, hi = _LO, _HI
    flo = diff(lo)
    fhi = diff(hi)
    if flo * fhi > 0:
        return None  # no sign change -> no root in range
    for _ in range(_MAX_ITER):
        mid = 0.5 * (lo + hi)
        fm = diff(mid)
        if abs(fm) < _TOL:
            return mid
        if flo * fm < 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)
```

- [ ] **Step 4: Run IV + model tests**

Run: `cd packages/core && uv run pytest tests/test_pricing_iv.py tests/test_pricing_greeks.py -q`
Expected: all passed.

- [ ] **Step 5: Commit (covers Task 5 + 6 imports)**

```bash
git add packages/core/saalr_core/pricing/iv.py packages/core/saalr_core/pricing/model.py packages/core/saalr_core/pricing/__init__.py packages/core/tests/test_pricing_iv.py packages/core/tests/test_pricing_greeks.py
git commit -m "feat(pricing): implied-vol solver (newton + bisection) + model wiring"
```

---

## Task 7: Vol surface assembly

**Files:**
- Create: `packages/core/saalr_core/pricing/surface.py`
- Test: `packages/core/tests/test_pricing_surface.py`

- [ ] **Step 1: Write failing test**

Create `packages/core/tests/test_pricing_surface.py`:

```python
from datetime import date

from saalr_core.pricing.surface import build_surface
from saalr_core.pricing.types import ContractGreeks, Greeks, OptionKind


def _cg(expiry, strike, kind, iv):
    g = Greeks(price=1.0, delta=0.5, gamma=0.0, theta=0.0, vega=0.0, rho=0.0, iv=iv)
    return ContractGreeks(
        expiry=expiry, strike=strike, kind=kind, bid=1.0, ask=1.1, last=1.05,
        volume=10, open_interest=20, ours=g, vendor_iv=iv, vendor_delta=None,
        vendor_gamma=None, vendor_theta=None, vendor_vega=None,
    )


def test_build_surface_groups_and_sorts():
    contracts = [
        _cg("2026-06-21", 190, OptionKind.CALL, 0.24),
        _cg("2026-06-21", 180, OptionKind.CALL, 0.26),
        _cg("2026-06-21", 180, OptionKind.PUT, 0.27),
        _cg("2026-07-19", 185, OptionKind.CALL, 0.22),
    ]
    out = build_surface(contracts, as_of=date(2026, 5, 30))
    assert [e["expiry"] for e in out] == ["2026-06-21", "2026-07-19"]
    june = out[0]
    assert june["days_to_expiry"] == 22
    assert [s["strike"] for s in june["strikes"]] == [180, 190]
    assert june["strikes"][0]["iv_call"] == 0.26
    assert june["strikes"][0]["iv_put"] == 0.27
    assert june["strikes"][1]["iv_put"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd packages/core && uv run pytest tests/test_pricing_surface.py -q`
Expected: FAIL — `surface` import error.

- [ ] **Step 3: Implement build_surface**

Create `packages/core/saalr_core/pricing/surface.py`:

```python
from __future__ import annotations

from datetime import date

from .types import ContractGreeks, OptionKind


def build_surface(contracts: list[ContractGreeks], as_of: date) -> list[dict]:
    """Fold contracts into the LLD §5.2 expiries[] -> strikes[] shape, using OUR iv."""
    by_expiry: dict[str, dict[float, dict]] = {}
    for c in contracts:
        strikes = by_expiry.setdefault(c.expiry, {})
        cell = strikes.setdefault(c.strike, {"strike": c.strike, "iv_call": None, "iv_put": None})
        if c.kind is OptionKind.CALL:
            cell["iv_call"] = c.ours.iv
        else:
            cell["iv_put"] = c.ours.iv

    out = []
    for expiry in sorted(by_expiry):
        dte = (date.fromisoformat(expiry) - as_of).days
        strikes = [by_expiry[expiry][k] for k in sorted(by_expiry[expiry])]
        out.append({"expiry": expiry, "days_to_expiry": dte, "strikes": strikes})
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/core && uv run pytest tests/test_pricing_surface.py -q`
Expected: passed.

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/pricing/surface.py packages/core/tests/test_pricing_surface.py
git commit -m "feat(pricing): vol-surface assembly into §5.2 shape"
```

---

## Task 8: Market-data types + provider protocols

**Files:**
- Create: `packages/core/saalr_core/marketdata/__init__.py`
- Create: `packages/core/saalr_core/marketdata/types.py`
- Create: `packages/core/saalr_core/marketdata/provider.py`

- [ ] **Step 1: Create types**

Create `packages/core/saalr_core/marketdata/__init__.py`:

```python
```

Create `packages/core/saalr_core/marketdata/types.py`:

```python
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

from saalr_core.pricing.types import OptionKind


@dataclass(frozen=True)
class RawContract:
    expiry: str  # YYYY-MM-DD
    strike: float
    kind: OptionKind
    bid: float | None
    ask: float | None
    last: float | None
    volume: int | None
    open_interest: int | None
    vendor_iv: float | None
    vendor_delta: float | None
    vendor_gamma: float | None
    vendor_theta: float | None
    vendor_vega: float | None


@dataclass(frozen=True)
class RawChain:
    underlying: str
    market: str
    as_of: str  # RFC3339
    spot: float
    div_yield: float
    contracts: list[RawContract]


@dataclass(frozen=True)
class YieldCurve:
    curve_date: str  # YYYY-MM-DD
    points: list[tuple[float, float]] = field(default_factory=list)  # (t_years, rate_decimal), sorted

    def rate_for(self, t_years: float) -> float:
        pts = self.points
        if not pts:
            raise ValueError("empty yield curve")
        if t_years <= pts[0][0]:
            return pts[0][1]
        if t_years >= pts[-1][0]:
            return pts[-1][1]
        ts = [t for t, _ in pts]
        i = bisect_left(ts, t_years)
        t0, r0 = pts[i - 1]
        t1, r1 = pts[i]
        return r0 + (r1 - r0) * (t_years - t0) / (t1 - t0)
```

- [ ] **Step 2: Create provider protocols**

Create `packages/core/saalr_core/marketdata/provider.py`:

```python
from __future__ import annotations

from typing import Protocol

from .types import RawChain, YieldCurve


class MarketDataProvider(Protocol):
    async def get_option_chain(self, ticker: str, market: str) -> RawChain: ...


class RiskFreeRateProvider(Protocol):
    async def get_curve(self) -> YieldCurve: ...


class ProviderError(Exception):
    """Raised when an upstream market-data provider is unreachable or returns an error."""
```

- [ ] **Step 3: Verify import**

Run: `uv run python -c "from saalr_core.marketdata.types import YieldCurve; c=YieldCurve('2026-05-30',[(0.25,0.04),(1.0,0.045)]); print(round(c.rate_for(0.5),5))"`
Expected: `0.0425`

- [ ] **Step 4: Commit**

```bash
git add packages/core/saalr_core/marketdata/
git commit -m "feat(marketdata): raw chain/curve types + provider protocols"
```

---

## Task 9: FRED risk-free rate provider

**Files:**
- Modify: `packages/core/saalr_core/marketdata/rates.py` (create)
- Test: `packages/core/tests/test_marketdata_rates.py`
- Fixture: `packages/core/tests/fixtures/fred_dgs3mo.json`

- [ ] **Step 1: Create the fixture**

Create `packages/core/tests/fixtures/fred_dgs3mo.json`:

```json
{
  "observations": [
    {"date": "2026-05-27", "value": "."},
    {"date": "2026-05-28", "value": "5.10"},
    {"date": "2026-05-29", "value": "."}
  ]
}
```

- [ ] **Step 2: Write failing tests (pure parsing + curve build)**

Create `packages/core/tests/test_marketdata_rates.py`:

```python
import json
import pathlib

from saalr_core.marketdata.rates import latest_observation, build_curve

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_latest_observation_skips_placeholders():
    data = json.loads((FIX / "fred_dgs3mo.json").read_text())
    obs_date, value = latest_observation(data)
    assert obs_date == "2026-05-28"
    assert value == 0.0510  # percent -> decimal


def test_build_curve_sorts_and_converts():
    raw = {"DGS1MO": ("2026-05-28", 0.0500), "DGS1": ("2026-05-28", 0.0460)}
    curve = build_curve(raw)
    assert curve.curve_date == "2026-05-28"
    assert curve.points[0][0] < curve.points[1][0]
    assert curve.points[0] == (1 / 12, 0.05)
```

- [ ] **Step 3: Run to verify failure**

Run: `cd packages/core && uv run pytest tests/test_marketdata_rates.py -q`
Expected: FAIL — `rates` import error.

- [ ] **Step 4: Implement rates.py**

Create `packages/core/saalr_core/marketdata/rates.py`:

```python
from __future__ import annotations

import logging

import httpx

from .types import YieldCurve

_logger = logging.getLogger("saalr.marketdata.rates")
_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED constant-maturity series -> tenor in years
_SERIES: dict[str, float] = {
    "DGS1MO": 1 / 12,
    "DGS3MO": 0.25,
    "DGS6MO": 0.5,
    "DGS1": 1.0,
    "DGS2": 2.0,
}


def latest_observation(payload: dict) -> tuple[str, float] | None:
    """Most-recent non-placeholder observation as (date, decimal_rate), or None."""
    for obs in reversed(payload.get("observations", [])):
        v = obs.get("value", ".")
        if v not in (".", "", None):
            return obs["date"], float(v) / 100.0
    return None


def build_curve(series: dict[str, tuple[str, float]]) -> YieldCurve:
    """series: series_id -> (date, decimal_rate). Returns a sorted YieldCurve."""
    points = sorted((_SERIES[sid], rate) for sid, (_d, rate) in series.items())
    curve_date = max(d for _d_unused, (d, _r) in series.items()) if series else ""
    return YieldCurve(curve_date=curve_date, points=points)


class FredRateProvider:
    def __init__(self, api_key: str | None, fallback_rate: float) -> None:
        self._api_key = api_key
        self._fallback = fallback_rate

    def _fallback_curve(self, reason: str) -> YieldCurve:
        _logger.warning("FRED unavailable (%s); using flat fallback %.4f", reason, self._fallback)
        return YieldCurve(curve_date="", points=[(1 / 12, self._fallback), (2.0, self._fallback)])

    async def get_curve(self) -> YieldCurve:
        if not self._api_key:
            return self._fallback_curve("no api key")
        series: dict[str, tuple[str, float]] = {}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for sid in _SERIES:
                    r = await client.get(
                        _FRED_URL,
                        params={
                            "series_id": sid,
                            "api_key": self._api_key,
                            "file_type": "json",
                            "sort_order": "asc",
                        },
                    )
                    r.raise_for_status()
                    obs = latest_observation(r.json())
                    if obs is not None:
                        series[sid] = obs
        except httpx.HTTPError as exc:
            return self._fallback_curve(str(exc))
        if not series:
            return self._fallback_curve("no observations")
        return build_curve(series)

    @property
    def source_name(self) -> str:
        return "fred" if self._api_key else "fallback"
```

- [ ] **Step 5: Run to verify pass**

Run: `cd packages/core && uv run pytest tests/test_marketdata_rates.py -q`
Expected: passed.

- [ ] **Step 6: Commit**

```bash
git add packages/core/saalr_core/marketdata/rates.py packages/core/tests/test_marketdata_rates.py packages/core/tests/fixtures/fred_dgs3mo.json
git commit -m "feat(marketdata): FRED rate provider + curve build with fallback"
```

---

## Task 10: Massive provider + pure parse_snapshot

**Files:**
- Create: `packages/core/saalr_core/marketdata/massive.py`
- Test: `packages/core/tests/test_marketdata_massive.py`
- Fixtures: `packages/core/tests/fixtures/massive_snapshot.json`, `massive_snapshot_page2.json`

- [ ] **Step 1: Create fixtures**

Create `packages/core/tests/fixtures/massive_snapshot.json`:

```json
{
  "results": [
    {
      "details": {"contract_type": "call", "strike_price": 180, "expiration_date": "2026-06-21"},
      "last_quote": {"bid": 7.1, "ask": 7.3},
      "day": {"close": 7.2, "volume": 1200},
      "open_interest": 3400,
      "implied_volatility": 0.262,
      "greeks": {"delta": 0.58, "gamma": 0.02, "theta": -0.05, "vega": 0.11}
    },
    {
      "details": {"contract_type": "put", "strike_price": 180, "expiration_date": "2026-06-21"},
      "last_quote": {"bid": 5.0, "ask": 5.2},
      "day": {"close": 5.1, "volume": 800},
      "open_interest": 2100,
      "implied_volatility": 0.271,
      "greeks": {"delta": -0.42, "gamma": 0.02, "theta": -0.04, "vega": 0.11}
    }
  ],
  "next_url": "https://api.massive.com/v3/snapshot/options/AAPL?cursor=PAGE2"
}
```

Create `packages/core/tests/fixtures/massive_snapshot_page2.json`:

```json
{
  "results": [
    {
      "details": {"contract_type": "call", "strike_price": 190, "expiration_date": "2026-06-21"},
      "last_quote": {"bid": 2.1, "ask": 2.3},
      "day": {"close": 2.2, "volume": 500},
      "open_interest": 900,
      "implied_volatility": 0.241,
      "greeks": {"delta": 0.33, "gamma": 0.018, "theta": -0.03, "vega": 0.09}
    }
  ],
  "next_url": null
}
```

- [ ] **Step 2: Write failing parse tests**

Create `packages/core/tests/test_marketdata_massive.py`:

```python
import json
import pathlib

from saalr_core.marketdata.massive import parse_results
from saalr_core.pricing.types import OptionKind

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_parse_results_maps_contracts():
    data = json.loads((FIX / "massive_snapshot.json").read_text())
    contracts = parse_results(data["results"])
    assert len(contracts) == 2
    c = contracts[0]
    assert c.kind is OptionKind.CALL
    assert c.strike == 180
    assert c.expiry == "2026-06-21"
    assert c.bid == 7.1 and c.ask == 7.3
    assert c.last == 7.2
    assert c.volume == 1200 and c.open_interest == 3400
    assert c.vendor_iv == 0.262
    assert c.vendor_delta == 0.58
    assert contracts[1].kind is OptionKind.PUT
```

- [ ] **Step 3: Run to verify failure**

Run: `cd packages/core && uv run pytest tests/test_marketdata_massive.py -q`
Expected: FAIL — `massive` import error.

- [ ] **Step 4: Implement massive.py**

Create `packages/core/saalr_core/marketdata/massive.py`:

```python
from __future__ import annotations

import asyncio

import httpx

from saalr_core.pricing.types import OptionKind

from .provider import ProviderError
from .types import RawChain, RawContract

_BASE = "https://api.massive.com"
_KIND = {"call": OptionKind.CALL, "put": OptionKind.PUT}


def _num(d: dict | None, key: str):
    return None if d is None else d.get(key)


def parse_results(results: list[dict]) -> list[RawContract]:
    """Pure: map Massive option snapshot rows into RawContract (vendor JSON stops here)."""
    out: list[RawContract] = []
    for row in results:
        det = row.get("details", {})
        kind = _KIND.get(det.get("contract_type"))
        if kind is None:
            continue
        quote = row.get("last_quote", {})
        day = row.get("day") or row.get("session") or {}  # legacy "day" / unified "session"
        g = row.get("greeks", {})
        out.append(
            RawContract(
                expiry=det["expiration_date"],
                strike=float(det["strike_price"]),
                kind=kind,
                bid=_num(quote, "bid"),
                ask=_num(quote, "ask"),
                last=_num(day, "close"),
                volume=_num(day, "volume"),
                open_interest=row.get("open_interest"),
                vendor_iv=row.get("implied_volatility"),
                vendor_delta=_num(g, "delta"),
                vendor_gamma=_num(g, "gamma"),
                vendor_theta=_num(g, "theta"),
                vendor_vega=_num(g, "vega"),
            )
        )
    return out


class MassiveProvider:
    def __init__(self, api_key: str | None, *, base_url: str = _BASE) -> None:
        self._api_key = api_key
        self._base = base_url

    async def _get(self, client: httpx.AsyncClient, url: str, params: dict) -> dict:
        for attempt in range(3):
            try:
                r = await client.get(url, params=params)
                if r.status_code in (429, 500, 502, 503):
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ProviderError(str(exc)) from exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ProviderError("exhausted retries")

    async def _spot_and_div(self, client: httpx.AsyncClient, ticker: str) -> tuple[float, float]:
        data = await self._get(
            client, f"{self._base}/v3/reference/tickers/{ticker}",
            {"apiKey": self._api_key},
        )
        res = data.get("results", {})
        # Massive does not always expose spot here; fall back to snapshot last trade.
        snap = await self._get(
            client, f"{self._base}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
            {"apiKey": self._api_key},
        )
        spot = float(snap.get("ticker", {}).get("lastTrade", {}).get("p", 0.0))
        div_yield = float(res.get("dividend_yield") or 0.0)
        return spot, div_yield

    async def get_option_chain(self, ticker: str, market: str) -> RawChain:
        if not self._api_key:
            raise ProviderError("no massive api key configured")
        from datetime import datetime, timezone

        contracts: list[RawContract] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            url = f"{self._base}/v3/snapshot/options/{ticker}"
            params = {"apiKey": self._api_key, "limit": 250}
            while url:
                data = await self._get(client, url, params)
                contracts.extend(parse_results(data.get("results", [])))
                url = data.get("next_url")
                params = {"apiKey": self._api_key}  # next_url already carries cursor
            spot, div_yield = await self._spot_and_div(client, ticker)

        as_of = datetime.now(timezone.utc).isoformat()
        return RawChain(
            underlying=ticker, market=market, as_of=as_of,
            spot=spot, div_yield=div_yield, contracts=contracts,
        )
```

> Note: `datetime.now` is intentionally inside the live method (not pure parsing); it is never hit by offline tests, which call `parse_results` directly or stub the provider.

- [ ] **Step 5: Run to verify pass**

Run: `cd packages/core && uv run pytest tests/test_marketdata_massive.py -q`
Expected: passed.

- [ ] **Step 6: Run the full core suite + lint**

Run: `cd packages/core && uv run pytest -q && cd ../.. && uvx ruff check packages/core/saalr_core`
Expected: all passed, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add packages/core/saalr_core/marketdata/massive.py packages/core/tests/test_marketdata_massive.py packages/core/tests/fixtures/massive_snapshot.json packages/core/tests/fixtures/massive_snapshot_page2.json
git commit -m "feat(marketdata): massive provider + pure parse_results with pagination"
```

---

## Task 11: Entitlement gate dependency

**Files:**
- Create: `apps/api/saalr_api/market/__init__.py`
- Create: `apps/api/saalr_api/market/gating.py`

- [ ] **Step 1: Create package init**

Create `apps/api/saalr_api/market/__init__.py`:

```python
```

- [ ] **Step 2: Implement the gate**

Create `apps/api/saalr_api/market/gating.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal


async def require_vol_surface(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    """Pass through (session, principal) only if the tier has the vol_surface entitlement."""
    _session, principal = ctx
    if not entitlements_for(principal.tier)["vol_surface"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": {
                    "code": "ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO",
                    "message": "vol surface and Greeks require a Pro or Premium plan",
                }
            },
        )
    yield ctx
```

> `get_principal` is an async generator dependency; wrapping it in another async generator keeps its request-scoped session/transaction open for the endpoint body.

- [ ] **Step 3: Verify import**

Run: `uv run python -c "from saalr_api.market.gating import require_vol_surface; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add apps/api/saalr_api/market/__init__.py apps/api/saalr_api/market/gating.py
git commit -m "feat(market): vol_surface entitlement gate (402)"
```

---

## Task 12: Snapshot persistence

**Files:**
- Create: `apps/api/saalr_api/market/snapshots.py`

- [ ] **Step 1: Implement the upsert**

Create `apps/api/saalr_api/market/snapshots.py`:

```python
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.pricing.types import ContractGreeks

_UPSERT = text(
    """
    INSERT INTO options_chain_snapshots
      (ts, underlying, market, expiry, strike, option_type,
       bid, ask, last, volume, open_interest, iv, delta, gamma, theta, vega)
    VALUES
      (:ts, :underlying, :market, :expiry, :strike, :option_type,
       :bid, :ask, :last, :volume, :open_interest, :iv, :delta, :gamma, :theta, :vega)
    ON CONFLICT (underlying, market, expiry, strike, option_type, ts)
    DO UPDATE SET
      bid = EXCLUDED.bid, ask = EXCLUDED.ask, last = EXCLUDED.last,
      volume = EXCLUDED.volume, open_interest = EXCLUDED.open_interest,
      iv = EXCLUDED.iv, delta = EXCLUDED.delta, gamma = EXCLUDED.gamma,
      theta = EXCLUDED.theta, vega = EXCLUDED.vega
    """
)


async def persist_chain(
    session: AsyncSession, underlying: str, market: str, ts: str, contracts: list[ContractGreeks]
) -> None:
    """Upsert our computed chain into the shared (non-tenant) options_chain_snapshots table."""
    if not contracts:
        return
    rows = [
        {
            "ts": ts,
            "underlying": underlying,
            "market": market,
            "expiry": c.expiry,
            "strike": c.strike,
            "option_type": c.kind.value,  # 'CALL' / 'PUT' (allowed by CHECK)
            "bid": c.bid,
            "ask": c.ask,
            "last": c.last,
            "volume": c.volume,
            "open_interest": c.open_interest,
            "iv": c.ours.iv,
            "delta": c.ours.delta,
            "gamma": c.ours.gamma,
            "theta": c.ours.theta,
            "vega": c.ours.vega,
        }
        for c in contracts
    ]
    await session.execute(_UPSERT, rows)
```

> The `option_type` CHECK allows `CALL`/`PUT` (LLD §3.6), so `OptionKind.value` is stored directly. This table has no RLS, so persistence works on any session regardless of `app.current_tenant`.

- [ ] **Step 2: Verify import + SQL parses**

Run: `uv run python -c "from saalr_api.market.snapshots import persist_chain; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps/api/saalr_api/market/snapshots.py
git commit -m "feat(market): persist computed chain into options_chain_snapshots"
```

---

## Task 13: Market service (fetch → compute → persist → cache)

**Files:**
- Create: `apps/api/saalr_api/market/service.py`

- [ ] **Step 1: Implement the service**

Create `apps/api/saalr_api/market/service.py`:

```python
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.marketdata.provider import MarketDataProvider, RiskFreeRateProvider
from saalr_core.marketdata.types import RawChain
from saalr_core.pricing.model import BSMModel
from saalr_core.pricing.surface import build_surface
from saalr_core.pricing.types import ContractGreeks, OptionParams

from .snapshots import persist_chain

_MODEL = BSMModel()


def _mid(c) -> float | None:
    if c.bid is not None and c.ask is not None and c.bid > 0 and c.ask > 0:
        return (c.bid + c.ask) / 2.0
    return c.last if (c.last and c.last > 0) else None


def _compute(chain: RawChain, rate_for, as_of_date: date) -> list[ContractGreeks]:
    out: list[ContractGreeks] = []
    for c in chain.contracts:
        dte = (date.fromisoformat(c.expiry) - as_of_date).days
        t_years = max(dte, 0) / 365.0
        if t_years <= 0:
            continue
        rate = rate_for(t_years)
        base = OptionParams(
            spot=chain.spot, strike=c.strike, t_years=t_years, rate=rate,
            sigma=0.0, div_yield=chain.div_yield, kind=c.kind,
        )
        mkt = _mid(c)
        iv = _MODEL.implied_vol(mkt, base) if mkt else None
        g = _MODEL.greeks(OptionParams(**{**base.__dict__, "sigma": iv})) if iv else None
        from saalr_core.pricing.types import Greeks

        ours = (
            Greeks(price=g.price, delta=g.delta, gamma=g.gamma, theta=g.theta,
                   vega=g.vega, rho=g.rho, iv=iv)
            if g else Greeks(price=mkt or 0.0, delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0, iv=None)
        )
        out.append(
            ContractGreeks(
                expiry=c.expiry, strike=c.strike, kind=c.kind, bid=c.bid, ask=c.ask,
                last=c.last, volume=c.volume, open_interest=c.open_interest, ours=ours,
                vendor_iv=c.vendor_iv, vendor_delta=c.vendor_delta, vendor_gamma=c.vendor_gamma,
                vendor_theta=c.vendor_theta, vendor_vega=c.vendor_vega,
            )
        )
    return out


class MarketService:
    def __init__(self, provider: MarketDataProvider, rates: RiskFreeRateProvider, redis, ttl: int):
        self._provider = provider
        self._rates = rates
        self._redis = redis
        self._ttl = ttl

    async def _computed_chain(self, session: AsyncSession, ticker: str, market: str) -> dict:
        key = f"mdq:chain:{market}:{ticker.upper()}"
        cached = await self._redis.get(key)
        if cached:
            payload = json.loads(cached)
            payload["_cache_hit"] = True
            return payload

        chain = await self._provider.get_option_chain(ticker, market)
        curve = await self._rates.get_curve()
        as_of_date = datetime.fromisoformat(chain.as_of).date()
        contracts = _compute(chain, curve.rate_for, as_of_date)
        await persist_chain(session, ticker.upper(), market, chain.as_of, contracts)

        payload = {
            "ticker": ticker.upper(),
            "market": market,
            "as_of": chain.as_of,
            "spot": chain.spot,
            "risk_free_source": getattr(self._rates, "source_name", "fred"),
            "contracts": [_contract_json(c) for c in contracts],
            "_cache_hit": False,
        }
        await self._redis.set(key, json.dumps(payload), ex=self._ttl)
        return payload

    async def iv_surface(self, session, ticker, market) -> dict:
        payload = await self._computed_chain(session, ticker, market)
        contracts = [_contract_from_json(c) for c in payload["contracts"]]
        as_of_date = datetime.fromisoformat(payload["as_of"]).date()
        return {
            "ticker": payload["ticker"],
            "market": payload["market"],
            "as_of": payload["as_of"],
            "spot": payload["spot"],
            "expiries": build_surface(contracts, as_of_date),
            "data_provider": "massive",
            "model": "bsm",
            "risk_free_source": payload["risk_free_source"],
            "freshness_ms": 0 if not payload["_cache_hit"] else None,
        }

    async def chain(self, session, ticker, market, expiry: str | None) -> dict:
        payload = await self._computed_chain(session, ticker, market)
        rows = payload["contracts"]
        if expiry:
            rows = [r for r in rows if r["expiry"] == expiry]
        return {
            "ticker": payload["ticker"],
            "market": payload["market"],
            "as_of": payload["as_of"],
            "spot": payload["spot"],
            "model": "bsm",
            "risk_free_source": payload["risk_free_source"],
            "contracts": rows,
        }


def _contract_json(c: ContractGreeks) -> dict:
    return {
        "expiry": c.expiry, "strike": c.strike, "type": c.kind.value,
        "bid": c.bid, "ask": c.ask, "last": c.last,
        "volume": c.volume, "open_interest": c.open_interest,
        "ours": {
            "price": c.ours.price, "delta": c.ours.delta, "gamma": c.ours.gamma,
            "theta": c.ours.theta, "vega": c.ours.vega, "rho": c.ours.rho, "iv": c.ours.iv,
        },
        "vendor": {
            "iv": c.vendor_iv, "delta": c.vendor_delta, "gamma": c.vendor_gamma,
            "theta": c.vendor_theta, "vega": c.vendor_vega,
        },
    }


def _contract_from_json(d: dict) -> ContractGreeks:
    from saalr_core.pricing.types import Greeks, OptionKind

    o = d["ours"]
    return ContractGreeks(
        expiry=d["expiry"], strike=d["strike"], kind=OptionKind(d["type"]),
        bid=d["bid"], ask=d["ask"], last=d["last"], volume=d["volume"],
        open_interest=d["open_interest"],
        ours=Greeks(price=o["price"], delta=o["delta"], gamma=o["gamma"], theta=o["theta"],
                    vega=o["vega"], rho=o["rho"], iv=o["iv"]),
        vendor_iv=d["vendor"]["iv"], vendor_delta=d["vendor"]["delta"],
        vendor_gamma=d["vendor"]["gamma"], vendor_theta=d["vendor"]["theta"],
        vendor_vega=d["vendor"]["vega"],
    )
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from saalr_api.market.service import MarketService; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps/api/saalr_api/market/service.py
git commit -m "feat(market): MarketService orchestration (fetch/compute/persist/cache)"
```

---

## Task 14: Router + app wiring

**Files:**
- Create: `apps/api/saalr_api/market/router.py`
- Modify: `apps/api/saalr_api/main.py`

- [ ] **Step 1: Implement the router**

Create `apps/api/saalr_api/market/router.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from saalr_core.marketdata.provider import ProviderError

from .gating import require_vol_surface
from .service import MarketService

router = APIRouter(prefix="/v1/market", tags=["market"])


def _service(request: Request) -> MarketService:
    s = request.app.state
    return MarketService(s.market_provider, s.rate_provider, s.redis, s.vol_surface_ttl)


def _validate(ticker: str, market: str) -> None:
    if not ticker or not ticker.isalpha():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": "unknown ticker"}},
        )
    if market not in ("US",):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": "unsupported market"}},
        )


@router.get("/iv-surface")
async def iv_surface(
    request: Request,
    ticker: str = Query(...),
    market: str = Query("US"),
    ctx: tuple[AsyncSession, Principal] = Depends(require_vol_surface),
) -> dict:
    _validate(ticker, market)
    session, _principal = ctx
    try:
        return await _service(request).iv_surface(session, ticker, market)
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "MARKET_DATA_PROVIDER_UNAVAILABLE", "message": str(exc)}},
        ) from exc


@router.get("/chain")
async def chain(
    request: Request,
    ticker: str = Query(...),
    market: str = Query("US"),
    expiry: str | None = Query(None),
    ctx: tuple[AsyncSession, Principal] = Depends(require_vol_surface),
) -> dict:
    _validate(ticker, market)
    session, _principal = ctx
    try:
        return await _service(request).chain(session, ticker, market, expiry)
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "MARKET_DATA_PROVIDER_UNAVAILABLE", "message": str(exc)}},
        ) from exc
```

- [ ] **Step 2: Wire providers + router into the app**

In `apps/api/saalr_api/main.py`, add imports near the top:

```python
from saalr_core.marketdata.massive import MassiveProvider
from saalr_core.marketdata.rates import FredRateProvider

from .market.router import router as market_router
```

Inside `lifespan`, after the `app.state.redis = ...` line, add:

```python
        app.state.market_provider = MassiveProvider(settings.massive_api_key)
        app.state.rate_provider = FredRateProvider(
            settings.fred_api_key, settings.risk_free_rate_fallback
        )
        app.state.vol_surface_ttl = settings.vol_surface_cache_ttl_seconds
```

After `app = FastAPI(title="Saalr API", lifespan=lifespan)`, add:

```python
    app.include_router(market_router)
```

- [ ] **Step 3: Verify the app boots**

Run: `uv run python -c "from saalr_api.main import create_app; app=create_app(); print([r.path for r in app.routes if 'market' in r.path])"`
Expected: includes `/v1/market/iv-surface` and `/v1/market/chain`.

- [ ] **Step 4: Lint**

Run: `uvx ruff check apps/api/saalr_api/market apps/api/saalr_api/main.py`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps/api/saalr_api/market/router.py apps/api/saalr_api/main.py
git commit -m "feat(market): iv-surface + chain endpoints wired into the app"
```

---

## Task 15: API integration tests

**Files:**
- Create: `tests/integration/test_market.py`

- [ ] **Step 1: Write the integration tests with stubbed providers**

Create `tests/integration/test_market.py`:

```python
import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind


class StubProvider:
    def __init__(self):
        self.calls = 0

    async def get_option_chain(self, ticker, market):
        self.calls += 1
        return RawChain(
            underlying=ticker.upper(), market=market, as_of="2026-05-30T14:30:00+00:00",
            spot=185.0, div_yield=0.005,
            contracts=[
                RawContract("2026-09-19", 180.0, OptionKind.CALL, 9.0, 9.2, 9.1, 100, 500,
                            0.26, 0.58, 0.02, -0.05, 0.11),
                RawContract("2026-09-19", 180.0, OptionKind.PUT, 5.0, 5.2, 5.1, 80, 400,
                            0.27, -0.42, 0.02, -0.04, 0.11),
            ],
        )


class StubRates:
    source_name = "fred"

    async def get_curve(self):
        return YieldCurve("2026-05-29", [(1 / 12, 0.05), (2.0, 0.045)])


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
            {"t": tenant_id},
        )


async def test_iv_surface_requires_pro(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            r = await c.get("/v1/market/iv-surface?ticker=AAPL",
                            headers={"Authorization": "Bearer dev:free@x.com"})
    assert r.status_code == 402
    assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO"


async def test_iv_surface_shape_for_pro(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            r = await c.get("/v1/market/iv-surface?ticker=AAPL", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["spot"] == 185.0
    assert body["data_provider"] == "massive"
    assert body["model"] == "bsm"
    exp = body["expiries"][0]
    assert exp["expiry"] == "2026-09-19"
    strike = exp["strikes"][0]
    assert strike["strike"] == 180.0
    assert strike["iv_call"] is not None and strike["iv_put"] is not None


async def test_chain_persists_and_caches(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("TRUNCATE options_chain_snapshots"))
    app = create_app()
    async with app.router.lifespan_context(app):
        stub = StubProvider()
        app.state.market_provider = stub
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pro2@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await app.state.redis.delete("mdq:chain:US:AAPL")
            r1 = await c.get("/v1/market/chain?ticker=AAPL", headers=h)
            r2 = await c.get("/v1/market/chain?ticker=AAPL", headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert stub.calls == 1  # second call served from cache
    rows = r1.json()["contracts"]
    assert rows[0]["ours"]["iv"] is not None
    assert "vendor" in rows[0]
    async with admin_engine.begin() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM options_chain_snapshots"))).scalar_one()
    assert n == 2


async def test_unknown_ticker_404(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pro3@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            r = await c.get("/v1/market/iv-surface?ticker=123", headers=h)
    assert r.status_code == 404
```

- [ ] **Step 2: Run the integration tests**

Ensure Docker Postgres + Redis are up (see `scripts/start.ps1`).
Run: `uv run pytest tests/integration/test_market.py -q`
Expected: 4 passed.

> If `database "saalr" does not exist`, native Windows PostgreSQL is shadowing the Docker DB on 5432 — stop the native PG service and `docker compose up -d --force-recreate postgres`, then retry.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_market.py
git commit -m "test(market): integration — gating, surface shape, persistence, cache, 404"
```

---

## Task 16: Live smoke tests (env-gated)

**Files:**
- Create: `tests/integration/test_market_smoke.py`

- [ ] **Step 1: Write env-gated smoke tests**

Create `tests/integration/test_market_smoke.py`:

```python
import os

import pytest

from saalr_core.config import get_settings
from saalr_core.marketdata.massive import MassiveProvider
from saalr_core.marketdata.rates import FredRateProvider

_settings = get_settings()

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_LIVE_SMOKE"),
    reason="set RUN_LIVE_SMOKE=1 to run live provider smoke tests",
)


@pytest.mark.skipif(not _settings.massive_api_key, reason="no MASSIVE_API_KEY")
async def test_massive_live_chain():
    chain = await MassiveProvider(_settings.massive_api_key).get_option_chain("AAPL", "US")
    assert chain.spot > 0
    assert len(chain.contracts) > 0


@pytest.mark.skipif(not _settings.fred_api_key, reason="no FRED_API_KEY")
async def test_fred_live_curve():
    curve = await FredRateProvider(_settings.fred_api_key, 0.05).get_curve()
    assert curve.points
    assert 0.0 < curve.rate_for(0.25) < 0.20
```

- [ ] **Step 2: Verify they are skipped without the flag**

Run: `uv run pytest tests/integration/test_market_smoke.py -q`
Expected: 2 skipped.

- [ ] **Step 3: (Manual, local) Run live with real keys**

Run: `RUN_LIVE_SMOKE=1 uv run pytest tests/integration/test_market_smoke.py -q`
Expected: 2 passed (requires real `MASSIVE_API_KEY` with options entitlement + `FRED_API_KEY` in `.env`).

> On PowerShell: `$env:RUN_LIVE_SMOKE=1; uv run pytest tests/integration/test_market_smoke.py -q`

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_market_smoke.py
git commit -m "test(market): env-gated live massive + fred smoke tests"
```

---

## Task 17: Full gate + orchestrator hook

**Files:**
- Modify: `scripts/orchestrate.ps1` (optional — for the autonomous rerun path)

- [ ] **Step 1: Run the entire suite + lint**

Run: `uv run pytest -q`
Expected: all green (live smoke skipped).
Run: `cd packages/core && uv run pytest -q && cd ../..`
Expected: core suite green.
Run: `uvx ruff check packages/core/saalr_core apps/api/saalr_api tests`
Expected: clean.

- [ ] **Step 2: Add a slice task to the orchestrator (optional)**

If you maintain `scripts/orchestrate.ps1` for autonomous reruns, append a function `Invoke-GreeksVolSurface` that runs `uv sync`, the two pytest suites above, and `ruff`, mirroring the existing task functions' fail-fast + logging pattern. (Match the established `function`-per-task dispatch; do not index an ordered dict by int.)

- [ ] **Step 3: Final commit**

```bash
git add scripts/orchestrate.ps1
git commit -m "chore(market): orchestrator task for greeks/vol-surface gates"
```

---

## Self-review checklist (completed)

- **Spec coverage:** engine (T2–T7), Massive adapter (T10), FRED rates (T9), persistence (T12), cache (T13), gating (T11), both endpoints (T14), §5.2 shape (T7/T13/T15), honesty fields `model`/`risk_free_source` (T13/T14), error codes 402/404/400/503 (T11/T14/T15), offline tests + env-gated live smoke (T15/T16). All present.
- **Placeholders:** none — every code step is complete.
- **Type consistency:** `OptionParams`, `Greeks`, `ContractGreeks`, `RawContract`, `RawChain`, `YieldCurve.rate_for`, `BSMModel.{price,greeks,implied_vol}`, `parse_results`, `latest_observation`/`build_curve`, `persist_chain`, `MarketService.{iv_surface,chain}`, `require_vol_surface` are used consistently across tasks.

## Known risks / notes for the implementer

- **Massive spot/dividend endpoints** (`_spot_and_div`) are best-effort; if your plan tier returns spot elsewhere, adjust the snapshot path during the live smoke test. The offline suite never calls it.
- **`_compute` rebuilds `OptionParams` via `__dict__`** to inject the solved sigma — keep `OptionParams` a flat frozen dataclass for this to hold.
- **Redis must be reachable** for integration tests (already used by magic-link). `scripts/start.ps1` brings up Postgres + Redis.
- **options_chain_snapshots is a hypertable** with no RLS; the `TRUNCATE` in the persistence test is safe and scoped to that table.
```
