# Billing & Growth Update — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Gate/advertise the new features (price_forecast=Premium, news_sentiment=Pro+), add a Monthly/Annual billing toggle with an annual discount badge, and add a compliant marketing-audience export.

**Architecture:** Part A extends `Entitlements` + adds two gates and per-panel frontend gating + plan copy. Part B threads an `interval` through the existing Stripe-checkout path and adds annual price IDs. Part C is one migration (columns + a `marketing_audience` view), a CSV export script, and a public `/unsubscribe` endpoint.

**Tech Stack:** Python 3.12 (FastAPI, SQLAlchemy, Alembic/psycopg2), React 18 + TS + Vitest (pnpm), Postgres on **55432** (Docker).

**Spec:** `docs/superpowers/specs/2026-06-06-billing-growth-design.md`

**Test commands:**
- core unit: `python -m pytest packages/core/tests/<f> -q`
- api integration (DB+Redis up): prefix with `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0"`
- web: `pnpm -C apps/web test -- run <f>`; typecheck `pnpm -C apps/web typecheck`
- migrations: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" uv run alembic upgrade head`

Commit footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Don't touch `.env`, root `.gitignore`, `tools/equity-screener`, `.omc`.

---

# Part A — New entitlements + gating + frontend + copy

### Task A1: Entitlements + tier mapping

**Files:** Modify `packages/core/saalr_core/tiers.py`; Create `packages/core/tests/test_tiers.py`

- [ ] **Step 1: Write `packages/core/tests/test_tiers.py`:**
```python
from saalr_core.tiers import Entitlements, entitlements_for


def test_price_forecast_is_premium_only():
    assert entitlements_for("premium")["price_forecast"] is True
    assert entitlements_for("pro")["price_forecast"] is False
    assert entitlements_for("free")["price_forecast"] is False


def test_news_sentiment_is_pro_plus():
    assert entitlements_for("pro")["news_sentiment"] is True
    assert entitlements_for("premium")["news_sentiment"] is True
    assert entitlements_for("free")["news_sentiment"] is False


def test_ml_forecast_mapping_unchanged():
    assert entitlements_for("pro")["ml_forecast"] is True
    assert entitlements_for("free")["ml_forecast"] is False


def test_unknown_tier_falls_back_to_free():
    assert entitlements_for("bogus") == entitlements_for("free")


def test_positional_construction_still_works():
    # the two new fields have defaults, so legacy positional construction must not break
    e = Entitlements(False, False, False, False, 0)
    assert e.price_forecast is False and e.news_sentiment is False
```

- [ ] **Step 2: Run → FAIL** `python -m pytest packages/core/tests/test_tiers.py -q` (KeyError/TypeError).

- [ ] **Step 3: Edit `packages/core/saalr_core/tiers.py`** to exactly:
```python
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Entitlements:
    live_chains: bool
    vol_surface: bool
    ml_forecast: bool
    research_agent: bool
    brokers: int
    price_forecast: bool = False
    news_sentiment: bool = False


TIERS: dict[str, Entitlements] = {
    "free": Entitlements(False, False, False, False, 0,
                         price_forecast=False, news_sentiment=False),
    "pro": Entitlements(True, True, True, False, 2,
                        price_forecast=False, news_sentiment=True),
    "premium": Entitlements(True, True, True, True, 4,
                            price_forecast=True, news_sentiment=True),
}


def entitlements_for(tier: str) -> dict:
    """Return the entitlement set for a tier as a plain dict (falls back to free)."""
    return asdict(TIERS.get(tier, TIERS["free"]))
```

- [ ] **Step 4: Run → PASS** `python -m pytest packages/core/tests/test_tiers.py packages/core/tests/test_billing_reducer.py -q`.

- [ ] **Step 5: Commit**
```bash
git add packages/core/saalr_core/tiers.py packages/core/tests/test_tiers.py
git commit -m "feat(tiers): price_forecast (Premium) + news_sentiment (Pro+) entitlements"
```

---

### Task A2: Gating — new gates + endpoint swaps

**Files:** Modify `apps/api/saalr_api/forecast/gating.py`, `apps/api/saalr_api/forecast/router.py`, `apps/api/saalr_api/sentiment/router.py`

- [ ] **Step 1: Add the two gates to `forecast/gating.py`** (after the existing `require_ml_forecast`; reuse its imports):
```python
async def require_price_forecast(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    _session, principal = ctx
    if not entitlements_for(principal.tier)["price_forecast"]:
        raise HTTPException(
            status_code=402,
            detail={"error": {"code": "ENTITLEMENT_PRICE_FORECAST_REQUIRES_PREMIUM",
                              "message": "AI price forecasts require a Premium plan"}},
        )
    yield ctx


async def require_news_sentiment(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    _session, principal = ctx
    if not entitlements_for(principal.tier)["news_sentiment"]:
        raise HTTPException(
            status_code=402,
            detail={"error": {"code": "ENTITLEMENT_NEWS_SENTIMENT_REQUIRES_PRO",
                              "message": "news sentiment requires a Pro or Premium plan"}},
        )
    yield ctx
```

- [ ] **Step 2: Swap the price-forecast endpoint gate** in `forecast/router.py`: change the import `from .gating import require_ml_forecast` to `from .gating import require_ml_forecast, require_price_forecast`, and in `price_forecast_endpoint` change its dependency `Depends(require_ml_forecast)` → `Depends(require_price_forecast)`. **Leave `vol_forecast_endpoint` on `require_ml_forecast`.**

- [ ] **Step 3: Swap the sentiment endpoint gate** in `sentiment/router.py`: change `from ..forecast.gating import require_ml_forecast` → `from ..forecast.gating import require_news_sentiment`, and the `get_sentiment` dependency `Depends(require_ml_forecast)` → `Depends(require_news_sentiment)`.

- [ ] **Step 4: Sanity import** `python -c "import saalr_api.forecast.router, saalr_api.sentiment.router; print('ok')"`. `ruff check apps/api/saalr_api/forecast/gating.py apps/api/saalr_api/forecast/router.py apps/api/saalr_api/sentiment/router.py`.

- [ ] **Step 5: Commit**
```bash
git add apps/api/saalr_api/forecast/gating.py apps/api/saalr_api/forecast/router.py apps/api/saalr_api/sentiment/router.py
git commit -m "feat(api): gate price-forecast on Premium, sentiment on news_sentiment"
```

---

### Task A3: Re-gating integration tests

**Files:** Modify `tests/integration/test_price_forecast.py`, `tests/integration/test_vol_forecast.py` (sentiment), or add `tests/integration/test_sentiment_gating.py`

- [ ] **Step 1: Update `tests/integration/test_price_forecast.py`.** Add a `_make_premium` helper next to `_make_pro`:
```python
async def _make_premium(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='premium' WHERE tenant_id=:t"), {"t": tenant_id})
```
Change `test_price_forecast_pro_returns_all_models` to use **premium** (rename to `_premium_`), calling `_make_premium`. Add a new test that **Pro is now 402**:
```python
async def test_price_forecast_pro_is_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pf-pro2@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            await _seed_bars(admin_engine, "AAPL", n=300)
            r = await c.get("/v1/market/price-forecast?ticker=AAPL&horizon=5", headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_PRICE_FORECAST_REQUIRES_PREMIUM"
```
(Keep the free→402 test; its code is now `ENTITLEMENT_PRICE_FORECAST_REQUIRES_PREMIUM` — update that assertion too.)

- [ ] **Step 2: Add a sentiment-gating test** — create `tests/integration/test_sentiment_gating.py`:
```python
import httpx
from sqlalchemy import text
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_sentiment_free_is_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.get("/v1/market/sentiment?ticker=AAPL", headers={"Authorization": "Bearer dev:sg-free@x.com"})
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_NEWS_SENTIMENT_REQUIRES_PRO"


async def test_sentiment_pro_is_200(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:sg-pro@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            async with admin_engine.begin() as conn:
                await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"), {"t": tid})
            r = await c.get("/v1/market/sentiment?ticker=AAPL", headers=h)
            assert r.status_code == 200 and r.json()["ticker"] == "AAPL"
```

- [ ] **Step 3: Run** (flush Redis first to drop any cached price-forecast):
```
docker exec docker-redis-1 redis-cli FLUSHALL
APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" python -m pytest tests/integration/test_price_forecast.py tests/integration/test_sentiment_gating.py -q
```
Expected: all pass.

- [ ] **Step 4: Commit**
```bash
git add tests/integration/test_price_forecast.py tests/integration/test_sentiment_gating.py
git commit -m "test(api): price-forecast=Premium, sentiment=Pro+ gating"
```

---

### Task A4: Plan-card copy

**Files:** Modify `apps/web/src/lib/tiers.ts`; Test `apps/web/src/lib/tiers.test.ts` (create)

- [ ] **Step 1: Write `apps/web/src/lib/tiers.test.ts`:**
```ts
import { describe, it, expect } from 'vitest'
import { TIERS } from './tiers'

const feats = (k: string) => TIERS.find((t) => t.key === k)!.features.join(' | ')

describe('plan copy', () => {
  it('premium headlines AI price forecasts', () => {
    expect(feats('premium')).toMatch(/ARIMA & LSTM/i)
  })
  it('pro lists HAR vol forecasts and news sentiment', () => {
    expect(feats('pro')).toMatch(/HAR/)
    expect(feats('pro')).toMatch(/sentiment/i)
  })
  it('free mentions in-app help', () => {
    expect(feats('free')).toMatch(/help/i)
  })
})
```

- [ ] **Step 2: Run → FAIL** `pnpm -C apps/web test -- run src/lib/tiers.test.ts`.

- [ ] **Step 3: Edit the `features` arrays in `apps/web/src/lib/tiers.ts`:**
```ts
// free.features:
    features: [
      'Strategy builder & payoff analysis',
      'OptionsAcademy lessons',
      'In-app help on every model & strategy',
    ],
// pro.features:
    features: [
      'Live options chains & IV surface',
      'GARCH & HAR vol forecasts · Monte-Carlo POP',
      'News sentiment',
      'Grounded Q&A assistant',
      'Everything in Free',
    ],
// premium.features:
    features: [
      'AI price forecasts (ARIMA & LSTM)',
      'Multi-agent Research Agent notes',
      'Higher run & rate limits',
      'Everything in Pro',
    ],
```

- [ ] **Step 4: Run → PASS** that test + the existing `PlanCards.test.tsx`/`Billing.test.tsx`:
`pnpm -C apps/web test -- run src/lib/tiers.test.ts src/features/billing src/pages/Billing`. Fix any existing test that asserted exact old bullet text.

- [ ] **Step 5: Commit**
```bash
git add apps/web/src/lib/tiers.ts apps/web/src/lib/tiers.test.ts
git commit -m "feat(web): plan copy — price forecasts, HAR, sentiment, in-app help"
```

---

### Task A5: Per-panel gating in Models (price panel → Premium upsell for Pro)

**Files:** Modify `apps/web/src/pages/Models.tsx`; Modify `apps/web/src/pages/Models.test.tsx`

Context: `Models.tsx` currently has `const entitled = me?.entitlements?.ml_forecast === true`, returns `<ModelsGate/>` when not entitled, wires `const priceQ = usePriceForecast(entitled ? ticker : '', horizon, entitled)`, includes `priceQ.error instanceof EntitlementError` in the page-level guard, and renders `{priceQ.data && <PriceForecastPanel forecast={priceQ.data} />}`.

- [ ] **Step 1: Edit `Models.tsx`:**
  (a) Add below the `entitled` line: `const priceEntitled = me?.entitlements?.price_forecast === true`.
  (b) Change the price query to gate on `priceEntitled`: `const priceQ = usePriceForecast(priceEntitled ? ticker : '', horizon, priceEntitled)`.
  (c) **Remove** `|| priceQ.error instanceof EntitlementError` from the `if (... ) return <ModelsGate />` guard (so a Pro user is never whole-page gated by the price panel).
  (d) Replace the price render block with a gated version:
```tsx
          {priceEntitled ? (
            <>
              {priceQ.data && <PriceForecastPanel forecast={priceQ.data} />}
              {priceQ.isLoading && ticker && (
                <div className="animate-pulse rounded-lg border border-line bg-panel2 py-16" data-testid="price-loading" />
              )}
            </>
          ) : (
            <Link to="/billing" data-testid="price-upsell"
              className="block rounded-lg border border-accent/40 bg-accent/5 p-4 text-sm text-txtDim hover:bg-accent/10">
              📈 <span className="font-medium text-txt">AI price forecasts (ARIMA &amp; LSTM)</span> are a Premium feature. Upgrade →
            </Link>
          )}
```
  Ensure `Link` is imported from `react-router-dom` (add if missing).

- [ ] **Step 2: Update `Models.test.tsx`.** The existing suite sets `mockMe = { entitlements: { ml_forecast: true } }`. Add tests:
```tsx
  it('shows the price upsell for a Pro user (ml_forecast but not price_forecast)', async () => {
    mockMe = { entitlements: { ml_forecast: true, price_forecast: false } }
    // …render Models, load a ticker as the existing tests do…
    expect(await screen.findByTestId('price-upsell')).toBeInTheDocument()
  })
  it('renders the price panel for Premium (price_forecast true)', async () => {
    mockMe = { entitlements: { ml_forecast: true, price_forecast: true } }
    // …render + load ticker; mock the price-forecast fetch to return a PriceForecast…
    // expect a price-forecast-panel (or no upsell)
    expect(screen.queryByTestId('price-upsell')).toBeNull()
  })
```
Mirror the existing test's render/mock setup (it already mocks `useAuth`/fetch). Keep existing assertions working — they don't set `price_forecast`, so those mockMe objects now imply `price_forecast` falsy → the upsell shows, which is correct; adjust any existing assertion that expected the price panel to instead expect the upsell, OR add `price_forecast: true` to that fixture.

- [ ] **Step 3: Run** `pnpm -C apps/web test -- run src/pages/Models` then `pnpm -C apps/web typecheck`. Both green.

- [ ] **Step 4: Commit**
```bash
git add apps/web/src/pages/Models.tsx apps/web/src/pages/Models.test.tsx
git commit -m "feat(web): price panel is Premium — Pro sees an upgrade card, page not gated"
```

**Checkpoint:** Part A complete. Restart the dev API later so `/me` serves the two new entitlement keys (note for the founder; do not restart without asking).

---

# Part B — Monthly/Annual toggle

### Task B1: Config + service price selection

**Files:** Modify `packages/core/saalr_core/config.py`, `apps/api/saalr_api/billing/service.py`; Test `apps/api/saalr_api/billing/` via `tests/integration/test_billing.py` or a unit test `packages/core/tests` — use a pure unit test here.

- [ ] **Step 1: Add annual price IDs to `config.py`** (next to the existing stripe price settings):
```python
    stripe_price_pro_annual: str | None = None
    stripe_price_premium_annual: str | None = None
```

- [ ] **Step 2: Write a failing unit test** `apps/api/saalr_api/billing/test_price_selection.py` (or `packages/core/tests/test_billing_price_selection.py`). Use a tiny fake settings + a fake provider to capture the chosen price:
```python
import pytest
from dataclasses import dataclass
from saalr_api.billing import service


@dataclass
class _S:
    stripe_price_pro: str = "pm"
    stripe_price_premium: str = "pmx"
    stripe_price_pro_annual: str | None = "pa"
    stripe_price_premium_annual: str | None = "pax"
    billing_success_url: str = "s"
    billing_cancel_url: str = "c"


class _Prov:
    def __init__(self): self.price_id = None
    async def ensure_customer(self, **k): return "cus_1"
    async def create_checkout_session(self, *, price_id, **k):
        self.price_id = price_id
        return "https://checkout"


class _Repo:
    async def get_customer_id(self, *a, **k): return "cus_1"
    async def set_customer_id(self, *a, **k): return None


@pytest.mark.parametrize("tier,interval,expected", [
    ("pro", "monthly", "pm"), ("pro", "annual", "pa"),
    ("premium", "monthly", "pmx"), ("premium", "annual", "pax"),
])
async def test_start_upgrade_picks_price(monkeypatch, tier, interval, expected):
    monkeypatch.setattr(service, "repo", _Repo())
    prov = _Prov()
    await service.start_upgrade(None, prov, _S(), __import__("uuid").uuid4(), "e@x.com", tier, interval)
    assert prov.price_id == expected


async def test_annual_falls_back_to_monthly_when_unset(monkeypatch):
    monkeypatch.setattr(service, "repo", _Repo())
    prov = _Prov()
    s = _S(stripe_price_pro_annual=None)
    await service.start_upgrade(None, prov, s, __import__("uuid").uuid4(), "e@x.com", "pro", "annual")
    assert prov.price_id == "pm"


def test_price_map_contains_all_four():
    m = service._price_map(_S())
    assert m == {"pm": "pro", "pmx": "premium", "pa": "pro", "pax": "premium"}
```

- [ ] **Step 3: Run → FAIL.**

- [ ] **Step 4: Edit `service.py`.** Replace `_price_map` and `start_upgrade`:
```python
def _price_map(settings) -> dict[str, str]:
    out = {}
    for pid in (settings.stripe_price_pro, settings.stripe_price_pro_annual):
        if pid:
            out[pid] = "pro"
    for pid in (settings.stripe_price_premium, settings.stripe_price_premium_annual):
        if pid:
            out[pid] = "premium"
    return out


def _price_id(settings, tier: str, interval: str) -> str:
    if tier == "pro":
        monthly, annual = settings.stripe_price_pro, settings.stripe_price_pro_annual
    else:
        monthly, annual = settings.stripe_price_premium, settings.stripe_price_premium_annual
    if interval == "annual" and annual:
        return annual
    return monthly


async def start_upgrade(session, provider, settings, tenant_id, email, tier,
                        interval: str = "monthly") -> dict:
    price_id = _price_id(settings, tier, interval)
    existing = await repo.get_customer_id(session, tenant_id)
    customer_id = await provider.ensure_customer(
        tenant_id=str(tenant_id), email=email, existing_id=existing)
    if customer_id != existing:
        await repo.set_customer_id(session, tenant_id, customer_id)
    url = await provider.create_checkout_session(
        customer_id=customer_id, price_id=price_id, tenant_id=str(tenant_id),
        trial_days=14 if tier == "pro" else 0,
        success_url=settings.billing_success_url, cancel_url=settings.billing_cancel_url)
    return {"checkout_url": url}
```
(Keep the existing `AsyncSession`/UUID type hints on the signature if you prefer; the test passes `None` for session, which is fine since the fake repo ignores it.)

- [ ] **Step 5: Run → PASS** the new test. `ruff check` the two files.

- [ ] **Step 6: Commit**
```bash
git add packages/core/saalr_core/config.py apps/api/saalr_api/billing/service.py apps/api/saalr_api/billing/test_price_selection.py
git commit -m "feat(billing): annual price IDs + (tier,interval) price selection"
```

---

### Task B2: Request schema + router pass-through

**Files:** Modify `apps/api/saalr_api/billing/schemas.py`, `apps/api/saalr_api/billing/router.py`; Test `tests/integration/test_billing.py` (extend)

- [ ] **Step 1: Edit `schemas.py`:**
```python
from typing import Literal
from pydantic import BaseModel


class UpgradeRequest(BaseModel):
    tier: Literal["pro", "premium"]
    interval: Literal["monthly", "annual"] = "monthly"
```

- [ ] **Step 2: Edit `router.py` `upgrade`** — pass the interval through:
```python
        out = await service.start_upgrade(session, provider, settings,
                                          principal.tenant_id, principal.email,
                                          body.tier, body.interval)
```

- [ ] **Step 3: Extend `tests/integration/test_billing.py`** with a 422-on-bad-interval check and an annual-accepted check. Mirror the file's existing client/fixture setup; assert `POST /subscription/upgrade {"tier":"pro","interval":"weekly"}` → 422, and `{"tier":"premium","interval":"annual"}` is accepted (or 503/502 if billing isn't configured in that test env — match how the existing upgrade test asserts). If the existing test runs without a payment provider, assert the 422 validation case only (validation happens before provider lookup).

- [ ] **Step 4: Run** the billing integration test with env vars; green. `ruff check` both files.

- [ ] **Step 5: Commit**
```bash
git add apps/api/saalr_api/billing/schemas.py apps/api/saalr_api/billing/router.py tests/integration/test_billing.py
git commit -m "feat(billing): accept interval on /subscription/upgrade"
```

---

### Task B3: Frontend toggle + checkout wiring

**Files:** Modify `apps/web/src/lib/billing.ts`, `apps/web/src/features/billing/hooks.ts`, `apps/web/src/features/billing/PlanCards.tsx`; Modify `apps/web/src/features/billing/PlanCards.test.tsx`

- [ ] **Step 1: Edit `lib/billing.ts`:**
```ts
export type Interval = 'monthly' | 'annual'

export function startUpgrade(tier: 'pro' | 'premium', interval: Interval = 'monthly'): Promise<{ checkout_url: string }> {
  return request('/subscription/upgrade', { method: 'POST', body: JSON.stringify({ tier, interval }) })
}
```

- [ ] **Step 2: Edit `features/billing/hooks.ts` `useUpgrade`:**
```ts
import type { Interval } from '../../lib/billing'

export function useUpgrade() {
  return useMutation({
    mutationFn: ({ tier, interval }: { tier: 'pro' | 'premium'; interval: Interval }) =>
      billing.startUpgrade(tier, interval),
    onSuccess: (r) => billing.redirectTo(r.checkout_url),
  })
}
```

- [ ] **Step 3: Write failing test additions in `PlanCards.test.tsx`** — a Monthly/Annual toggle that drives the upgrade interval and shows the annual badge:
```tsx
  it('defaults to monthly and upgrades monthly', async () => {
    const spy = vi.spyOn(billing, 'startUpgrade').mockResolvedValue({ checkout_url: 'x' })
    render(wrap(<PlanCards current="free" />))
    fireEvent.click(screen.getByRole('button', { name: /Upgrade to Pro/i }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('pro', 'monthly'))
  })

  it('annual toggle shows the discount badge and upgrades annually', async () => {
    const spy = vi.spyOn(billing, 'startUpgrade').mockResolvedValue({ checkout_url: 'x' })
    render(wrap(<PlanCards current="free" />))
    fireEvent.click(screen.getByTestId('billing-interval-annual'))
    expect(screen.getAllByTestId('annual-badge').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /Upgrade to Premium/i }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('premium', 'annual'))
  })
```
(Use the test file's existing `wrap`/imports; import `* as billing from '../../lib/billing'` if not already. The existing `useUpgrade` is invoked inside PlanCards, which calls `billing.startUpgrade` — so spying on `startUpgrade` captures the args.)

- [ ] **Step 4: Run → FAIL.**

- [ ] **Step 5: Edit `PlanCards.tsx`** — add interval state, a toggle, the badge, and pass interval to `upgrade.mutate`:
```tsx
import { useState } from 'react'
import { TIERS, TIER_RANK, type TierName } from '../../lib/tiers'
import { useUpgrade } from './hooks'
import type { Interval } from '../../lib/billing'

export function PlanCards({ current, highlight }: { current: TierName; highlight?: TierName }) {
  const upgrade = useUpgrade()
  const [interval, setInterval] = useState<Interval>('monthly')
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1 text-xs" role="group" aria-label="Billing interval">
        {(['monthly', 'annual'] as Interval[]).map((iv) => (
          <button key={iv} data-testid={`billing-interval-${iv}`} onClick={() => setInterval(iv)}
            className={`rounded-full px-3 py-1 ${interval === iv ? 'bg-accent text-canvas' : 'text-txtDim hover:text-txt'}`}>
            {iv === 'monthly' ? 'Monthly' : 'Annual'}
          </button>
        ))}
        {interval === 'annual' && <span className="ml-2 text-[11px] text-pos">2 months free</span>}
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {TIERS.map((t) => {
          const isCurrent = t.key === current
          const isUpgrade = TIER_RANK[t.key] > TIER_RANK[current]
          const ring = (highlight ?? 'pro') === t.key && !isCurrent
          return (
            <div key={t.key} data-testid={`plan-${t.key}`}
              className={`relative flex flex-col rounded-lg border bg-panel p-5 ${ring ? 'border-accent' : 'border-line'}`}>
              <h3 className="font-mono text-sm uppercase tracking-[0.18em] text-txt">{t.name}</h3>
              <p className="mt-1 text-sm text-txtDim">{t.tagline}</p>
              {interval === 'annual' && t.key !== 'free' && (
                <span data-testid="annual-badge" className="mt-2 inline-block w-fit rounded bg-pos/15 px-2 py-0.5 text-[11px] text-pos">
                  Save 17% · 2 months free
                </span>
              )}
              <ul className="mt-4 space-y-2 text-sm text-txtDim">
                {t.features.map((f) => (
                  <li key={f} className="flex gap-2"><span aria-hidden className="font-mono text-pos">✓</span>{f}</li>
                ))}
              </ul>
              <div className="mt-5">
                {isCurrent ? (
                  <span className="inline-block rounded-md border border-pos/30 px-4 py-2 text-xs text-pos" data-testid={`plan-${t.key}-current`}>Current plan</span>
                ) : isUpgrade ? (
                  <button onClick={() => upgrade.mutate({ tier: t.key as 'pro' | 'premium', interval })}
                    disabled={upgrade.isPending}
                    className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-50">
                    {upgrade.isPending ? 'Starting…' : `Upgrade to ${t.name}`}
                  </button>
                ) : null}
              </div>
              {upgrade.isError && isUpgrade && (
                <p className="mt-2 text-[11px] text-neg" data-testid={`plan-${t.key}-error`}>
                  {upgrade.error?.message === 'FEATURE_UNAVAILABLE' ? "Billing isn’t available right now." : "Couldn’t start checkout — try again."}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Run → PASS** `pnpm -C apps/web test -- run src/features/billing src/pages/Billing` and `pnpm -C apps/web typecheck`. (The existing PlanCards tests that called `upgrade.mutate('pro')` shape now go through the UI buttons — if a prior test asserted `startUpgrade` was called with a bare string, update it to `('pro','monthly')`.)

- [ ] **Step 7: Commit**
```bash
git add apps/web/src/lib/billing.ts apps/web/src/features/billing/hooks.ts apps/web/src/features/billing/PlanCards.tsx apps/web/src/features/billing/PlanCards.test.tsx
git commit -m "feat(web): Monthly/Annual billing toggle + annual discount badge"
```

---

# Part C — Marketing audience

### Task C1: Migration — columns + `marketing_audience` view

**Files:** Create `infra/migrations/versions/0013_marketing_audience.py`; Test `tests/integration/test_marketing_audience.py`

- [ ] **Step 1: Create the migration** `infra/migrations/versions/0013_marketing_audience.py` (mirror `0012`'s `op.execute` style):
```python
"""marketing audience: opt-in, unsubscribe token, audience view

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-06
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users ADD COLUMN marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE users ADD COLUMN unsubscribe_token UUID NOT NULL DEFAULT gen_random_uuid();
        CREATE UNIQUE INDEX idx_users_unsubscribe_token ON users(unsubscribe_token);

        CREATE VIEW marketing_audience AS
          SELECT u.email,
                 u.email_verified_at,
                 u.created_at,
                 u.marketing_opt_in,
                 u.unsubscribe_token,
                 COALESCE(s.tier, 'free') AS tier,
                 EXISTS (SELECT 1 FROM strategies st   WHERE st.tenant_id = m.tenant_id) AS has_strategy,
                 EXISTS (SELECT 1 FROM orders o        WHERE o.tenant_id  = m.tenant_id) AS has_traded,
                 EXISTS (SELECT 1 FROM backtests b     WHERE b.tenant_id  = m.tenant_id) AS has_backtest,
                 EXISTS (SELECT 1 FROM user_progress p WHERE p.tenant_id  = m.tenant_id) AS has_progress
          FROM users u
          JOIN memberships m ON m.user_id = u.user_id
          LEFT JOIN subscriptions s ON s.tenant_id = m.tenant_id AND s.status IN ('active','trialing');
        GRANT SELECT ON marketing_audience TO saalr_app;
    """)


def downgrade() -> None:
    op.execute("""
        DROP VIEW IF EXISTS marketing_audience;
        DROP INDEX IF EXISTS idx_users_unsubscribe_token;
        ALTER TABLE users DROP COLUMN IF EXISTS unsubscribe_token;
        ALTER TABLE users DROP COLUMN IF EXISTS marketing_opt_in;
    """)
```
Note: `gen_random_uuid()` is built into Postgres 13+. If the migration errors with "function gen_random_uuid() does not exist", prepend `CREATE EXTENSION IF NOT EXISTS pgcrypto;` to the upgrade SQL.

- [ ] **Step 2: Apply it** `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" uv run alembic upgrade head`. Expected: `Running upgrade 0012 -> 0013`.

- [ ] **Step 3: Round-trip check** — downgrade then upgrade:
```
ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" uv run alembic downgrade -1
ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" uv run alembic upgrade head
```
Both succeed.

- [ ] **Step 4: Write `tests/integration/test_marketing_audience.py`** — the view exists and reflects engagement. Bootstrap a user via `/me`, then read the view via the admin engine:
```python
import httpx
from sqlalchemy import text
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_marketing_audience_view_lists_user(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            await c.get("/me", headers={"Authorization": "Bearer dev:aud1@x.com"})
    async with admin_engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT email, tier, marketing_opt_in, has_strategy FROM marketing_audience WHERE email=:e"),
            {"e": "aud1@x.com"})).mappings().first()
    assert row is not None
    assert row["tier"] == "free" and row["marketing_opt_in"] is False
    assert row["has_strategy"] is False
```

- [ ] **Step 5: Run** with env vars; green.

- [ ] **Step 6: Commit**
```bash
git add infra/migrations/versions/0013_marketing_audience.py tests/integration/test_marketing_audience.py
git commit -m "feat(db): marketing opt-in/unsubscribe columns + marketing_audience view"
```

---

### Task C2: CSV export script

**Files:** Create `scripts/export_audience.py`; Test `scripts/test_export_audience.py` (or `tests/unit/`)

- [ ] **Step 1: Write `scripts/test_export_audience.py`** for the pure segment→WHERE helper + CSV writer:
```python
import io
from scripts.export_audience import segment_where, write_csv


def test_segment_where_clauses():
    assert segment_where("all") == ""
    assert "email_verified_at IS NOT NULL" in segment_where("verified")
    assert "marketing_opt_in" in segment_where("opted-in")
    assert "has_strategy" in segment_where("engaged")


def test_write_csv_emits_header_and_rows():
    buf = io.StringIO()
    write_csv(buf, [{"email": "a@b.com", "tier": "free", "verified": True,
                     "opted_in": False, "has_strategy": True, "has_traded": False,
                     "has_backtest": False, "has_progress": False}])
    out = buf.getvalue()
    assert out.splitlines()[0].startswith("email,tier,verified")
    assert "a@b.com" in out
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `scripts/export_audience.py`:**
```python
"""Export the marketing audience to CSV (admin/superuser DB connection).

Usage: ADMIN_DATABASE_URL=... python -m scripts.export_audience --segment verified --out audience.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_FIELDS = ["email", "tier", "verified", "opted_in",
           "has_strategy", "has_traded", "has_backtest", "has_progress"]


def segment_where(segment: str) -> str:
    if segment == "verified":
        return "WHERE email_verified_at IS NOT NULL"
    if segment == "opted-in":
        return "WHERE marketing_opt_in"
    if segment == "engaged":
        return "WHERE has_strategy OR has_traded OR has_backtest OR has_progress"
    return ""  # all


def write_csv(buf, rows: list[dict]) -> None:
    w = csv.DictWriter(buf, fieldnames=_FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)


async def _fetch(url: str, segment: str) -> list[dict]:
    engine = create_async_engine(url)
    try:
        sql = (
            "SELECT email, tier, (email_verified_at IS NOT NULL) AS verified, "
            "marketing_opt_in AS opted_in, has_strategy, has_traded, has_backtest, has_progress "
            f"FROM marketing_audience {segment_where(segment)} ORDER BY created_at DESC"
        )
        async with engine.connect() as conn:
            rows = (await conn.execute(text(sql))).mappings().all()
        return [dict(r) for r in rows]
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="export_audience")
    p.add_argument("--segment", choices=["all", "verified", "engaged", "opted-in"], default="verified")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url:
        raise SystemExit("ADMIN_DATABASE_URL is required")
    rows = asyncio.run(_fetch(url, args.segment))
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            write_csv(f, rows)
        print(f"wrote {len(rows)} rows to {args.out}")
    else:
        write_csv(sys.stdout, rows)


if __name__ == "__main__":
    main()
```
Ensure `scripts/` is importable as a package for the test (add an empty `scripts/__init__.py` if the repo's other scripts/tests need it; if `scripts/` isn't on the path in pytest, place the test under `tests/unit/test_export_audience.py` and import via the module path the repo uses — check an existing script test first).

- [ ] **Step 4: Run → PASS** the helper test. `ruff check scripts/export_audience.py`.

- [ ] **Step 5: Smoke the real export** (optional, prints to stdout):
```
ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" python -m scripts.export_audience --segment all | head
```
Expected: a CSV header + the dev users.

- [ ] **Step 6: Commit**
```bash
git add scripts/export_audience.py scripts/test_export_audience.py
git commit -m "feat(scripts): one-command marketing-audience CSV export"
```

---

### Task C3: Public unsubscribe endpoint

**Files:** Create `apps/api/saalr_api/marketing/__init__.py`, `apps/api/saalr_api/marketing/router.py`; Modify `apps/api/saalr_api/main.py`; Test `tests/integration/test_unsubscribe.py`

- [ ] **Step 1: Write `tests/integration/test_unsubscribe.py`:**
```python
import httpx
from sqlalchemy import text
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_unsubscribe_flips_opt_in_and_is_idempotent(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            await c.get("/me", headers={"Authorization": "Bearer dev:unsub@x.com"})
        # opt the user in, capture their token
        async with admin_engine.begin() as conn:
            await conn.execute(text("UPDATE users SET marketing_opt_in=true WHERE email='unsub@x.com'"))
            tok = (await conn.execute(text("SELECT unsubscribe_token FROM users WHERE email='unsub@x.com'"))).scalar_one()
        async with _client(app) as c:
            r1 = await c.get(f"/unsubscribe?token={tok}")
            r2 = await c.get(f"/unsubscribe?token={tok}")  # idempotent
            bad = await c.get("/unsubscribe?token=00000000-0000-0000-0000-000000000000")
    assert r1.status_code == 200 and r1.json()["unsubscribed"] is True
    assert r2.status_code == 200
    assert bad.status_code == 200  # neutral, no enumeration
    async with admin_engine.begin() as conn:
        opt = (await conn.execute(text("SELECT marketing_opt_in FROM users WHERE email='unsub@x.com'"))).scalar_one()
    assert opt is False
```

- [ ] **Step 2: Run → FAIL** (route missing → 404).

- [ ] **Step 3: Implement `apps/api/saalr_api/marketing/router.py`** (uses the admin/app sessionmaker directly; `users` isn't tenant-GUC scoped for this update, so run it via the app sessionmaker with an autocommit block — the `users` table's update by token doesn't depend on RLS tenant context because it's keyed by the globally-unique token, but `users` may be RLS-free; verify: if the UPDATE returns 0 rows under RLS, use `request.app.state.sessionmaker` which connects as `saalr_app` — `users` is NOT in the RLS TENANT_SCOPED list, so a plain UPDATE works):
```python
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

router = APIRouter(tags=["marketing"])


@router.get("/unsubscribe")
async def unsubscribe(request: Request, token: str = Query(...)) -> dict:
    # Neutral response regardless of token validity (no user enumeration).
    try:
        tok = str(UUID(token))
    except ValueError:
        return {"unsubscribed": True}
    sm = request.app.state.sessionmaker
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE users SET marketing_opt_in = FALSE WHERE unsubscribe_token = :t"),
            {"t": tok},
        )
    return {"unsubscribed": True}
```
Create an empty `apps/api/saalr_api/marketing/__init__.py`.

- [ ] **Step 4: Mount in `main.py`** — add `from .marketing.router import router as marketing_router` with the other router imports, and `app.include_router(marketing_router)` with the other `include_router` calls.

- [ ] **Step 5: Run → PASS** the unsubscribe test with env vars. If the UPDATE affects 0 rows (RLS), confirm `users` is not RLS-forced (it isn't — only `TENANT_SCOPED` tables are) — the test asserting `opt_in is False` will catch a failure. `ruff check` the new files + `main.py`.

- [ ] **Step 6: Commit**
```bash
git add apps/api/saalr_api/marketing/__init__.py apps/api/saalr_api/marketing/router.py apps/api/saalr_api/main.py tests/integration/test_unsubscribe.py
git commit -m "feat(api): public /unsubscribe endpoint (idempotent, no enumeration)"
```

---

## Final verification
- [ ] `python -m pytest packages/core/tests/test_tiers.py scripts/test_export_audience.py -q` and the touched integration tests (price-forecast, sentiment gating, billing, marketing_audience, unsubscribe) with env vars — all green.
- [ ] `pnpm -C apps/web test -- run src/lib src/features/billing src/pages` + `pnpm -C apps/web typecheck` — green/clean.
- [ ] Final code-reviewer over the whole diff.
- [ ] superpowers:finishing-a-development-branch (do NOT push until asked).
- [ ] Note to founder: restart the dev API to serve the new `/me` entitlement keys; set `STRIPE_PRICE_PRO_ANNUAL`/`STRIPE_PRICE_PREMIUM_ANNUAL` in `.env` (matching the ~17%/2-months-free Stripe annual prices) to activate annual checkout; run `python -m scripts.export_audience --segment verified --out audience.csv` to pull the survey list.

## Self-review notes
- **Spec coverage:** A→ Tasks A1–A5; B→ B1–B3; C→ C1–C3. ✅
- **Type consistency:** `entitlements_for(...)["price_forecast"]`/`["news_sentiment"]` (A1) match the gate keys (A2), the integration error codes (A3), and the frontend `me.entitlements.price_forecast` gate (A5). `start_upgrade(...interval)` (B1) matches `body.interval` (B2) and `startUpgrade(tier, interval)` / `useUpgrade({tier,interval})` (B3). `marketing_audience` columns (C1) match the export SELECT (C2) and the view test. ✅
- **Frontend types:** entitlements is a loose `Record<string, boolean|number>` — no interface change; existing fixtures stay valid (missing keys read falsy → upsell shows, which A5 tests assert). ✅
- **Breaking change** (Pro loses price panel) localized to A2/A3/A5 with the pro=402 test. ✅
