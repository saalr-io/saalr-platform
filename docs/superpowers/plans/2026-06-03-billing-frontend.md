# Billing Frontend (B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing 402 upgrade nudges into a real Stripe Checkout flow — a `/app/billing` page (current plan + Free/Pro/Premium upgrade + manage-billing), success/cancel handling, and nudge wiring — over the B1 endpoints.

**Architecture:** A `src/features/billing/` feature + `src/lib/billing.ts` client (with a mockable `redirectTo`) over B1's `GET /subscription`, `POST /subscription/upgrade`, `POST /subscription/portal`. A shared `src/lib/tiers.ts` (DRY with the marketing landing). Two tiny B1 backend touch-ups (`has_customer` flag + `:5173` redirect defaults). Client-only `/app` routes (no SSG impact).

**Tech Stack:** React 18 + TypeScript (strict), Tailwind, TanStack Query, react-router 6, Vitest + @testing-library/react. Backend: FastAPI + DB on 55432.

**Spec:** `docs/superpowers/specs/2026-06-03-billing-frontend-design.md`

**Conventions:** web tests via `npm run typecheck && npm run lint && npm run test:run` from `apps/web`. Backend tests via `ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/saalr APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr uv run pytest ...`. Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Never touch root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`. Theme tokens only (no raw Tailwind colors); no inline `style={{}}` (use `[animation-delay:..]`-style arbitrary classes).

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/saalr_api/billing/service.py` (modify) | `get_subscription` += `has_customer` |
| `packages/core/saalr_core/config.py` (modify) | billing redirect defaults → `:5173` |
| `tests/integration/test_billing.py` (modify) | assert `has_customer` |
| `apps/web/src/lib/tiers.ts` (create) | shared `TierName`/`TIER_RANK`/`TierCard`/`TIERS` |
| `apps/web/src/features/marketing/copy.ts` (modify) | re-export `TIERS`/`TierCard` from `lib/tiers` |
| `apps/web/src/lib/billing.ts` (create) | client: getSubscription/startUpgrade/openPortal + `redirectTo` |
| `apps/web/src/auth/AuthContext.tsx` (modify) | expose `refresh()` |
| `apps/web/src/features/billing/hooks.ts` (create) | useSubscription / useUpgrade / usePortal |
| `apps/web/src/features/billing/PlanCards.tsx` (create) | the three plan cards |
| `apps/web/src/pages/Billing.tsx` (create) | `/app/billing` page |
| `apps/web/src/pages/BillingSuccess.tsx` (create) | poll-until-flip success page |
| `apps/web/src/pages/BillingCancel.tsx` (create) | cancel page |
| `apps/web/src/app/Router.tsx` (modify) | billing routes |
| `apps/web/src/components/Sidebar.tsx` (modify) | "Billing" nav item |
| `apps/web/src/components/Topbar.tsx` (modify) | tier chip → Link |
| `apps/web/src/features/academy/ModuleReader.tsx` (modify) | upgrade Link in `UpgradeNudge` |
| `apps/web/src/features/academy/AskAssistant.tsx` (modify) | upgrade Link in the entitlement nudge |
| `apps/web/src/features/research/PremiumGate.tsx` (modify) | upgrade Link |
| `+ *.test.ts(x)` per new unit | tests |

---

## Task 1: Backend touch-ups (`has_customer` + `:5173` defaults)

**Files:**
- Modify: `apps/api/saalr_api/billing/service.py`
- Modify: `packages/core/saalr_core/config.py`
- Test: `tests/integration/test_billing.py`

- [ ] **Step 1: Add the failing test.** APPEND to `tests/integration/test_billing.py`:

```python
async def test_get_subscription_reports_has_customer(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine, "hc@acme.com")
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert (await service.get_subscription(s, tenant_id))["has_customer"] is False
        await repo.set_customer_id(s, tenant_id, "cus_hc")
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert (await service.get_subscription(s, tenant_id))["has_customer"] is True
```

- [ ] **Step 2: Run to verify failure.** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run pytest tests/integration/test_billing.py::test_get_subscription_reports_has_customer -q` → FAIL (KeyError `has_customer`).

- [ ] **Step 3: Implement `has_customer`.** In `apps/api/saalr_api/billing/service.py` `get_subscription`, add the flag (it already has `session` + `tenant_id`):

```python
async def get_subscription(session: AsyncSession, tenant_id: UUID) -> dict:
    row = await repo.get_subscription(session, tenant_id)
    tier = row.tier if row else "free"
    return {
        "tier": tier,
        "status": row.status if row else "active",
        "current_period_end": row.current_period_end.isoformat() if row else None,
        "cancel_at_period_end": bool(row.cancel_at_period_end) if row else False,
        "entitlements": entitlements_for(tier),
        "has_customer": await repo.get_customer_id(session, tenant_id) is not None,
    }
```

- [ ] **Step 4: Bump the redirect defaults.** In `packages/core/saalr_core/config.py`, change the three billing URL defaults from `:5174` to `:5173`:

```python
    billing_success_url: str = "http://localhost:5173/app/billing/success"
    billing_cancel_url: str = "http://localhost:5173/app/billing/cancel"
    billing_portal_return_url: str = "http://localhost:5173/app/billing"
```

- [ ] **Step 5: Run to verify pass.** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run pytest tests/integration/test_billing.py -q` → all pass. `uv run ruff check apps/api/saalr_api/billing packages/core/saalr_core/config.py` → clean.

- [ ] **Step 6: Commit.**
```bash
git add apps/api/saalr_api/billing/service.py packages/core/saalr_core/config.py tests/integration/test_billing.py
git commit -m "feat(billing): GET /subscription has_customer flag + :5173 redirect defaults

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Shared `lib/tiers.ts` (DRY refactor)

**Files:**
- Create: `apps/web/src/lib/tiers.ts`
- Create: `apps/web/src/lib/tiers.test.ts`
- Modify: `apps/web/src/features/marketing/copy.ts`

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/lib/tiers.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { TIERS, TIER_RANK } from './tiers'

describe('tiers', () => {
  it('exposes the three tiers in order with lowercase keys', () => {
    expect(TIERS.map((t) => t.key)).toEqual(['free', 'pro', 'premium'])
    expect(TIERS.map((t) => t.name)).toEqual(['Free', 'Pro', 'Premium'])
  })
  it('ranks free < pro < premium', () => {
    expect(TIER_RANK.free).toBeLessThan(TIER_RANK.pro)
    expect(TIER_RANK.pro).toBeLessThan(TIER_RANK.premium)
  })
  it('quotes no dollar prices', () => {
    const text = TIERS.flatMap((t) => [t.tagline, ...t.features]).join(' ')
    expect(text).not.toContain('$')
  })
})
```

- [ ] **Step 2: Run to verify failure.** From `apps/web`: `npx vitest run src/lib/tiers.test.ts` → FAIL (module missing).

- [ ] **Step 3: Create `apps/web/src/lib/tiers.ts`** (the feature copy is moved verbatim from `marketing/copy.ts`):

```typescript
// Shared plan definitions — the single source of truth for the marketing landing
// (Tiers.tsx) and the in-app billing page (PlanCards.tsx). No prices: Stripe Checkout
// is the price source of truth.

export type TierName = 'free' | 'pro' | 'premium'

export const TIER_RANK: Record<TierName, number> = { free: 0, pro: 1, premium: 2 }

export interface TierCard {
  key: TierName
  name: string
  tagline: string
  features: string[]
  highlight?: boolean
}

export const TIERS: TierCard[] = [
  {
    key: 'free',
    name: 'Free',
    tagline: 'Learn and build.',
    features: [
      'Strategy builder & payoff analysis',
      'OptionsAcademy lessons',
      'Strategy explainers',
    ],
  },
  {
    key: 'pro',
    name: 'Pro',
    tagline: 'Live market data & models.',
    features: [
      'Live options chains & IV surface',
      'GARCH vol forecasts & Monte-Carlo POP',
      'Grounded Q&A assistant',
      'Everything in Free',
    ],
    highlight: true,
  },
  {
    key: 'premium',
    name: 'Premium',
    tagline: 'The full research desk.',
    features: [
      'Multi-agent Research Agent notes',
      'Higher run & rate limits',
      'Everything in Pro',
    ],
  },
]
```

- [ ] **Step 4: Re-point `marketing/copy.ts`.** In `apps/web/src/features/marketing/copy.ts`, DELETE the local `TierCard` interface and the local `TIERS` const, and replace them with a re-export (place it where `TIERS` was). Keep everything else (`HERO`, `FEATURES`, `CAPABILITIES`, `FOOTER_LINKS`, `DISCLAIMER`) unchanged:

```typescript
export { TIERS, type TierCard } from '../../lib/tiers'
```

- [ ] **Step 5: Run to verify pass.** From `apps/web`: `npx vitest run src/lib/tiers.test.ts src/features/marketing` → all pass (the marketing `Tiers.test.tsx` + `copy.test.ts` still import `TIERS` via `./copy` and are unaffected). `npm run typecheck` → clean.

- [ ] **Step 6: Commit.**
```bash
git add apps/web/src/lib/tiers.ts apps/web/src/lib/tiers.test.ts apps/web/src/features/marketing/copy.ts
git commit -m "refactor(web): extract shared lib/tiers (DRY marketing + billing)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `lib/billing.ts` client + `redirectTo`

**Files:**
- Create: `apps/web/src/lib/billing.ts`
- Test: `apps/web/src/lib/billing.test.ts`

- [ ] **Step 1: Write the failing tests.** Create `apps/web/src/lib/billing.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getSubscription, startUpgrade, openPortal, EntitlementError } from './billing'

describe('billing client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('getSubscription GETs /subscription', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      tier: 'free', status: 'active', current_period_end: null,
      cancel_at_period_end: false, entitlements: {}, has_customer: false,
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const s = await getSubscription()
    expect(String(fetchMock.mock.calls[0][0])).toContain('/subscription')
    expect(s.tier).toBe('free')
    expect(s.has_customer).toBe(false)
  })

  it('startUpgrade POSTs the tier and returns checkout_url', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ checkout_url: 'https://stripe/c/1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const r = await startUpgrade('pro')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(String(url)).toContain('/subscription/upgrade')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ tier: 'pro' })
    expect(r.checkout_url).toBe('https://stripe/c/1')
  })

  it('openPortal POSTs and returns portal_url', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ portal_url: 'https://stripe/p/1' }), { status: 200 })))
    expect((await openPortal()).portal_url).toBe('https://stripe/p/1')
  })

  it('402 throws EntitlementError with the code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: { error: { code: 'FEATURE_UNAVAILABLE' } } }),
        { status: 402 })))
    const err = await startUpgrade('pro').catch((e) => e)
    expect(err).toBeInstanceOf(EntitlementError)
    expect((err as EntitlementError).code).toBe('FEATURE_UNAVAILABLE')
  })
})
```

- [ ] **Step 2: Run to verify failure.** From `apps/web`: `npx vitest run src/lib/billing.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement `apps/web/src/lib/billing.ts`:**

```typescript
import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError } from './strategies'
import type { TierName } from './tiers'

export { EntitlementError }

export interface Subscription {
  tier: TierName
  status: string
  current_period_end: string | null
  cancel_at_period_end: boolean
  entitlements: Record<string, boolean | number>
  has_customer: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (res.status === 401) {
    setToken(null)
    throw new Error('unauthorized')
  }
  if (res.status === 402) {
    const body = await res.json().catch(() => ({}))
    throw new EntitlementError(body?.detail?.error?.code ?? 'ENTITLEMENT_REQUIRED')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail?.error?.code ?? `request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export function getSubscription(): Promise<Subscription> {
  return request('/subscription')
}

export function startUpgrade(tier: 'pro' | 'premium'): Promise<{ checkout_url: string }> {
  return request('/subscription/upgrade', { method: 'POST', body: JSON.stringify({ tier }) })
}

export function openPortal(): Promise<{ portal_url: string }> {
  return request('/subscription/portal', { method: 'POST' })
}

// Full-page navigation to Stripe — isolated so tests can spy on it without navigating.
export function redirectTo(url: string): void {
  window.location.assign(url)
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/lib/billing.test.ts` → 4 passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/lib/billing.ts apps/web/src/lib/billing.test.ts
git commit -m "feat(web): billing API client + redirectTo helper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Expose `AuthContext.refresh()`

**Files:**
- Modify: `apps/web/src/auth/AuthContext.tsx`
- Test: `apps/web/src/auth/AuthContext.test.tsx` (append)

- [ ] **Step 1: Write the failing test.** APPEND a test to `apps/web/src/auth/AuthContext.test.tsx` (it already mocks the auth api + renders a consumer; mirror its existing pattern). Add a consumer that reads `refresh` and assert it's a function:

```typescript
it('exposes a refresh() on the context', async () => {
  let ctx: ReturnType<typeof useAuth> | null = null
  function Probe() { ctx = useAuth(); return null }
  render(<AuthProvider><Probe /></AuthProvider>)
  await waitFor(() => expect(ctx).not.toBeNull())
  expect(typeof ctx!.refresh).toBe('function')
})
```
(Ensure `useAuth`, `AuthProvider`, `render`, `waitFor` are imported as the existing tests do.)

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/auth/AuthContext.test.tsx` → FAIL (`refresh` is not on the value / typecheck error).

- [ ] **Step 3: Implement.** In `apps/web/src/auth/AuthContext.tsx`:
  - Add `refresh: () => Promise<void>` to the `AuthContextValue` interface.
  - In `DevAuthProvider`, the internal `refresh` callback already exists — add it to the provider value:
    ```typescript
    return (
      <AuthContext.Provider value={{ status, me, login, requestLink, completeLink, logout, refresh }}>
        {children}
      </AuthContext.Provider>
    )
    ```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/auth/AuthContext.test.tsx` → all pass. `npm run typecheck` → clean.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/auth/AuthContext.tsx apps/web/src/auth/AuthContext.test.tsx
git commit -m "feat(web): expose AuthContext.refresh() for post-checkout tier reload

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Billing hooks

**Files:**
- Create: `apps/web/src/features/billing/hooks.ts`
- Test: `apps/web/src/features/billing/hooks.test.tsx`

Note: hooks import the billing module as a NAMESPACE (`import * as billing`) and call `billing.redirectTo(...)` / `billing.startUpgrade(...)` so tests can `vi.spyOn(billing, 'redirectTo')` (property access is resolved at call time).

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/features/billing/hooks.test.tsx`:

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import * as billing from '../../lib/billing'
import { useUpgrade } from './hooks'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

function UpgradeProbe() {
  const up = useUpgrade()
  return <button onClick={() => up.mutate('pro')}>go</button>
}

describe('billing hooks', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('useUpgrade redirects to the checkout url', async () => {
    vi.spyOn(billing, 'startUpgrade').mockResolvedValue({ checkout_url: 'https://stripe/c/9' })
    const redirect = vi.spyOn(billing, 'redirectTo').mockImplementation(() => {})
    render(wrap(<UpgradeProbe />))
    fireEvent.click(screen.getByText('go'))
    await waitFor(() => expect(redirect).toHaveBeenCalledWith('https://stripe/c/9'))
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/features/billing/hooks.test.tsx` → FAIL (module missing).

- [ ] **Step 3: Implement `apps/web/src/features/billing/hooks.ts`:**

```typescript
import { useMutation, useQuery } from '@tanstack/react-query'
import * as billing from '../../lib/billing'

export function useSubscription() {
  return useQuery({ queryKey: ['subscription'], queryFn: billing.getSubscription, retry: false })
}

export function useUpgrade() {
  return useMutation({
    mutationFn: (tier: 'pro' | 'premium') => billing.startUpgrade(tier),
    onSuccess: (r) => billing.redirectTo(r.checkout_url),
  })
}

export function usePortal() {
  return useMutation({
    mutationFn: () => billing.openPortal(),
    onSuccess: (r) => billing.redirectTo(r.portal_url),
  })
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/features/billing/hooks.test.tsx` → 1 passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/features/billing/hooks.ts apps/web/src/features/billing/hooks.test.tsx
git commit -m "feat(web): billing hooks (useSubscription/useUpgrade/usePortal)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: PlanCards

**Files:**
- Create: `apps/web/src/features/billing/PlanCards.tsx`
- Test: `apps/web/src/features/billing/PlanCards.test.tsx`

PlanCards takes `current: TierName` and `highlight?: TierName`. For each tier: if `tier.key === current` → "Current plan" (disabled); if `TIER_RANK[tier.key] > TIER_RANK[current]` → "Upgrade" (calls `useUpgrade().mutate(tier.key)` — only pro/premium are ever > current); else (lower) → no action. The `highlight` tier gets an accent ring.

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/features/billing/PlanCards.test.tsx`:

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import * as billing from '../../lib/billing'
import { PlanCards } from './PlanCards'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('PlanCards', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('marks the current tier and offers upgrades for higher tiers', () => {
    render(wrap(<PlanCards current="free" />))
    expect(screen.getByTestId('plan-free').textContent).toContain('Current plan')
    expect(screen.getByTestId('plan-pro').querySelector('button')!.textContent).toContain('Upgrade')
    expect(screen.getByTestId('plan-premium').querySelector('button')!.textContent).toContain('Upgrade')
  })

  it('upgrading calls the client then redirects', async () => {
    vi.spyOn(billing, 'startUpgrade').mockResolvedValue({ checkout_url: 'https://stripe/c/x' })
    const redirect = vi.spyOn(billing, 'redirectTo').mockImplementation(() => {})
    render(wrap(<PlanCards current="free" />))
    fireEvent.click(screen.getByTestId('plan-pro').querySelector('button')!)
    await waitFor(() => expect(billing.startUpgrade).toHaveBeenCalledWith('pro'))
    await waitFor(() => expect(redirect).toHaveBeenCalledWith('https://stripe/c/x'))
  })

  it('a Pro user sees Pro as current and only Premium upgradeable', () => {
    render(wrap(<PlanCards current="pro" />))
    expect(screen.getByTestId('plan-pro').textContent).toContain('Current plan')
    expect(screen.queryByTestId('plan-free')!.querySelector('button')).toBeNull()
    expect(screen.getByTestId('plan-premium').querySelector('button')!.textContent).toContain('Upgrade')
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/features/billing/PlanCards.test.tsx` → FAIL.

- [ ] **Step 3: Implement `apps/web/src/features/billing/PlanCards.tsx`:**

```typescript
import { TIERS, TIER_RANK, type TierName } from '../../lib/tiers'
import { useUpgrade } from './hooks'

export function PlanCards({ current, highlight }: { current: TierName; highlight?: TierName }) {
  const upgrade = useUpgrade()
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {TIERS.map((t) => {
        const isCurrent = t.key === current
        const isUpgrade = TIER_RANK[t.key] > TIER_RANK[current]
        const ring = (highlight ?? 'pro') === t.key && !isCurrent
        return (
          <div
            key={t.key}
            data-testid={`plan-${t.key}`}
            className={`relative flex flex-col rounded-lg border bg-panel p-5 ${
              ring ? 'border-accent' : 'border-line'
            }`}
          >
            <h3 className="font-mono text-sm uppercase tracking-[0.18em] text-txt">{t.name}</h3>
            <p className="mt-1 text-sm text-txtDim">{t.tagline}</p>
            <ul className="mt-4 space-y-2 text-sm text-txtDim">
              {t.features.map((f) => (
                <li key={f} className="flex gap-2">
                  <span aria-hidden className="font-mono text-pos">✓</span>
                  {f}
                </li>
              ))}
            </ul>
            <div className="mt-5">
              {isCurrent ? (
                <span
                  className="inline-block rounded-md border border-pos/30 px-4 py-2 text-xs text-pos"
                  data-testid={`plan-${t.key}-current`}
                >
                  Current plan
                </span>
              ) : isUpgrade ? (
                <button
                  onClick={() => upgrade.mutate(t.key as 'pro' | 'premium')}
                  disabled={upgrade.isPending}
                  className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-50"
                >
                  {upgrade.isPending ? 'Starting…' : `Upgrade to ${t.name}`}
                </button>
              ) : null}
            </div>
            {upgrade.isError && isUpgrade && (
              <p className="mt-2 text-[11px] text-neg" data-testid={`plan-${t.key}-error`}>
                {upgrade.error?.message === 'FEATURE_UNAVAILABLE'
                  ? 'Billing isn’t available right now.'
                  : 'Couldn’t start checkout — try again.'}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
```

Note: billing-unavailable arrives as a plain `Error('FEATURE_UNAVAILABLE')` (the 503 path of the shared `request()` wrapper — only a 402 throws `EntitlementError`, and upgrade isn't entitlement-gated), so we branch on `error.message`, not the error type.

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/features/billing/PlanCards.test.tsx` → 3 passed. `npm run lint` → clean.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/features/billing/PlanCards.tsx apps/web/src/features/billing/PlanCards.test.tsx
git commit -m "feat(web): billing PlanCards (current plan + upgrade buttons)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Billing page

**Files:**
- Create: `apps/web/src/pages/Billing.tsx`
- Test: `apps/web/src/pages/Billing.test.tsx`

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/pages/Billing.test.tsx`:

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as billing from '../lib/billing'
import { Billing } from './Billing'

function wrap(ui: React.ReactNode, path = '/billing') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const SUB = (over = {}) => ({
  tier: 'free', status: 'active', current_period_end: null,
  cancel_at_period_end: false, entitlements: {}, has_customer: false, ...over,
})

describe('Billing page', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('shows the current plan and no manage button without a customer', async () => {
    vi.spyOn(billing, 'getSubscription').mockResolvedValue(SUB() as never)
    render(wrap(<Billing />))
    await waitFor(() => expect(screen.getByTestId('current-plan').textContent).toMatch(/free/i))
    expect(screen.queryByTestId('manage-billing')).toBeNull()
  })

  it('shows Manage billing when a customer exists and opens the portal', async () => {
    vi.spyOn(billing, 'getSubscription').mockResolvedValue(
      SUB({ tier: 'pro', status: 'active', has_customer: true }) as never)
    vi.spyOn(billing, 'openPortal').mockResolvedValue({ portal_url: 'https://stripe/p/2' })
    const redirect = vi.spyOn(billing, 'redirectTo').mockImplementation(() => {})
    render(wrap(<Billing />))
    const btn = await screen.findByTestId('manage-billing')
    fireEvent.click(btn)
    await waitFor(() => expect(redirect).toHaveBeenCalledWith('https://stripe/p/2'))
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/pages/Billing.test.tsx` → FAIL.

- [ ] **Step 3: Implement `apps/web/src/pages/Billing.tsx`:**

```typescript
import { useSearchParams } from 'react-router-dom'
import { PlanCards } from '../features/billing/PlanCards'
import { useSubscription, usePortal } from '../features/billing/hooks'
import type { TierName } from '../lib/tiers'

function fmtDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : ''
}

export function Billing() {
  const { data, isLoading } = useSubscription()
  const portal = usePortal()
  const [params] = useSearchParams()
  const highlight = (params.get('plan') as TierName | null) ?? undefined
  const current = (data?.tier ?? 'free') as TierName

  return (
    <div className="animate-fadeUp space-y-6">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Billing</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Plans &amp; billing</h2>
        {!isLoading && data && (
          <p className="mt-2 text-sm text-txtDim" data-testid="current-plan">
            Current plan: <span className="text-txt">{current}</span>
            {data.status !== 'active' ? ` (${data.status})` : ''}
            {data.current_period_end
              ? data.cancel_at_period_end
                ? ` · cancels ${fmtDate(data.current_period_end)}`
                : current !== 'free'
                  ? ` · renews ${fmtDate(data.current_period_end)}`
                  : ''
              : ''}
          </p>
        )}
      </div>

      <PlanCards current={current} highlight={highlight} />

      {data?.has_customer && (
        <div>
          <button
            data-testid="manage-billing"
            onClick={() => portal.mutate()}
            disabled={portal.isPending}
            className="rounded-md border border-line px-4 py-2 text-xs text-txtDim transition hover:border-accent hover:text-txt disabled:opacity-50"
          >
            {portal.isPending ? 'Opening…' : 'Manage billing'}
          </button>
          {portal.isError && (
            <span className="ml-3 text-[11px] text-neg" data-testid="manage-error">
              Couldn’t open the billing portal — try again.
            </span>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/pages/Billing.test.tsx` → 2 passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/pages/Billing.tsx apps/web/src/pages/Billing.test.tsx
git commit -m "feat(web): /app/billing page (current plan + manage billing)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Success + Cancel pages

**Files:**
- Create: `apps/web/src/pages/BillingSuccess.tsx`
- Create: `apps/web/src/pages/BillingCancel.tsx`
- Test: `apps/web/src/pages/BillingSuccess.test.tsx`

`BillingSuccess` polls `getSubscription` via `useQuery` with `refetchInterval`. It records the tier at first successful load; once a later poll returns a tier that is non-free AND differs from the initial free state (or simply a non-free tier), it stops polling, calls `auth.refresh()`, and shows the confirmation. A bounded attempt count (~10 × 2s ≈ 20s) drives the timeout branch.

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/pages/BillingSuccess.test.tsx`:

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as billing from '../lib/billing'
import { BillingSuccess } from './BillingSuccess'

const refresh = vi.fn(async () => {})
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ refresh }) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const SUB = (tier: string) => ({
  tier, status: 'active', current_period_end: null,
  cancel_at_period_end: false, entitlements: {}, has_customer: true,
})

describe('BillingSuccess', () => {
  beforeEach(() => { vi.restoreAllMocks(); refresh.mockClear() })

  it('confirms once the tier flips and refreshes the session', async () => {
    const get = vi.spyOn(billing, 'getSubscription')
      .mockResolvedValueOnce(SUB('free') as never)
      .mockResolvedValue(SUB('pro') as never)
    render(wrap(<BillingSuccess />))
    await waitFor(() => expect(screen.getByTestId('billing-confirmed').textContent).toMatch(/pro/i),
      { timeout: 5000 })
    expect(refresh).toHaveBeenCalled()
    expect(get).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/pages/BillingSuccess.test.tsx` → FAIL.

- [ ] **Step 3: Implement `apps/web/src/pages/BillingSuccess.tsx`:**

```typescript
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getSubscription } from '../lib/billing'
import { useAuth } from '../auth/AuthContext'

const MAX_POLLS = 10  // ~20s at 2s intervals

export function BillingSuccess() {
  const auth = useAuth()
  const [polls, setPolls] = useState(0)
  const confirmedRef = useRef(false)

  const flipped = (tier: string | undefined) => tier !== undefined && tier !== 'free'

  const { data } = useQuery({
    queryKey: ['subscription', 'success'],
    queryFn: getSubscription,
    retry: false,
    refetchInterval: (q) =>
      flipped(q.state.data?.tier) || polls >= MAX_POLLS ? false : 2000,
  })

  useEffect(() => {
    setPolls((n) => (flipped(data?.tier) ? n : n + 1))
  }, [data])

  useEffect(() => {
    if (flipped(data?.tier) && !confirmedRef.current) {
      confirmedRef.current = true
      void auth.refresh()
    }
  }, [data, auth])

  const confirmed = flipped(data?.tier)
  const timedOut = !confirmed && polls >= MAX_POLLS

  return (
    <div className="animate-fadeUp mx-auto max-w-md py-16 text-center">
      {confirmed ? (
        <>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-pos">// Welcome aboard</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight" data-testid="billing-confirmed">
            You’re on {data!.tier} 🎉
          </h2>
          <p className="mt-2 text-sm text-txtDim">Your plan is active. Everything’s unlocked.</p>
          <Link to="/" className="mt-6 inline-block rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-canvas">
            Go to the app
          </Link>
        </>
      ) : timedOut ? (
        <>
          <h2 className="text-xl font-semibold tracking-tight">Payment received</h2>
          <p className="mt-2 text-sm text-txtDim" data-testid="billing-processing">
            Your plan will update shortly. This can take a few seconds.
          </p>
          <Link to="/billing" className="mt-6 inline-block rounded-md border border-line px-5 py-2.5 text-sm text-txt">
            Back to billing
          </Link>
        </>
      ) : (
        <p className="text-sm text-txtDim" data-testid="billing-waiting">Confirming your subscription…</p>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Implement `apps/web/src/pages/BillingCancel.tsx`:**

```typescript
import { Link } from 'react-router-dom'

export function BillingCancel() {
  return (
    <div className="animate-fadeUp mx-auto max-w-md py-16 text-center">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-txtFaint">// Checkout canceled</p>
      <h2 className="mt-3 text-xl font-semibold tracking-tight">No charge was made</h2>
      <p className="mt-2 text-sm text-txtDim">You can pick a plan whenever you’re ready.</p>
      <Link to="/billing" className="mt-6 inline-block rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-canvas">
        Back to billing
      </Link>
    </div>
  )
}
```

- [ ] **Step 5: Run to verify pass.** `npx vitest run src/pages/BillingSuccess.test.tsx` → 1 passed. `npm run lint` → clean.

- [ ] **Step 6: Commit.**
```bash
git add apps/web/src/pages/BillingSuccess.tsx apps/web/src/pages/BillingCancel.tsx apps/web/src/pages/BillingSuccess.test.tsx
git commit -m "feat(web): billing success (poll-until-flip) + cancel pages

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Wire routes, nav, and the nudges

**Files:**
- Modify: `apps/web/src/app/Router.tsx`
- Modify: `apps/web/src/components/Sidebar.tsx`
- Modify: `apps/web/src/components/Topbar.tsx`
- Modify: `apps/web/src/features/academy/ModuleReader.tsx`
- Modify: `apps/web/src/features/academy/AskAssistant.tsx`
- Modify: `apps/web/src/features/research/PremiumGate.tsx`
- Test: `apps/web/src/features/research/PremiumGate.test.tsx` (+ extend academy tests)

- [ ] **Step 1: Add the routes.** In `apps/web/src/app/Router.tsx`, add imports `import { Billing } from '../pages/Billing'`, `import { BillingSuccess } from '../pages/BillingSuccess'`, `import { BillingCancel } from '../pages/BillingCancel'`, and three routes inside the authed `<Route element={<RequireAuth><AppShell/></RequireAuth>}>` block:
```tsx
        <Route path="billing" element={<Billing />} />
        <Route path="billing/success" element={<BillingSuccess />} />
        <Route path="billing/cancel" element={<BillingCancel />} />
```

- [ ] **Step 2: Sidebar item.** In `apps/web/src/components/Sidebar.tsx`, add `['/billing', 'Billing']` to the `System` section's `items` array (so it sits with System Status):
```tsx
  { label: 'System', items: [['/billing', 'Billing'], ['/system', 'System Status']] },
```

- [ ] **Step 3: Topbar tier chip → Link.** In `apps/web/src/components/Topbar.tsx`, wrap the existing tier badge `<span>…{cap(me?.tier ?? 'free')}…</span>` in a react-router `<Link to="/billing">` (add `import { Link } from 'react-router-dom'` at the top). Keep the existing classes on the inner span; the Link adds `title="Manage plan"`.

- [ ] **Step 4: Wire the academy `UpgradeNudge`.** In `apps/web/src/features/academy/ModuleReader.tsx`, add `import { Link } from 'react-router-dom'` and, inside `UpgradeNudge` (after the existing copy), add:
```tsx
      <Link
        to="/billing?plan=pro"
        data-testid="nudge-upgrade"
        className="mt-4 inline-block rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90"
      >
        Upgrade to Pro
      </Link>
```

- [ ] **Step 5: Wire the `AskAssistant` nudge.** In `apps/web/src/features/academy/AskAssistant.tsx`, add `import { Link } from 'react-router-dom'` and, inside the `isEntitlement` nudge block (after the "Upgrade to unlock…" paragraph), add the same `<Link to="/billing?plan=pro" data-testid="ask-upgrade-link" …>Upgrade to Pro</Link>`.

- [ ] **Step 6: Wire `PremiumGate` + its test.** Replace the static "contact your account team" line in `apps/web/src/features/research/PremiumGate.tsx` with an upgrade Link. First update the test — create/replace `apps/web/src/features/research/PremiumGate.test.tsx`:
```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PremiumGate } from './PremiumGate'

describe('PremiumGate', () => {
  it('links to the billing page to upgrade to Premium', () => {
    render(<MemoryRouter><PremiumGate /></MemoryRouter>)
    const link = screen.getByRole('link', { name: /upgrade to premium/i })
    expect(link).toHaveAttribute('href', '/billing?plan=premium')
  })
})
```
Then implement: add `import { Link } from 'react-router-dom'` and replace the final `<p>…contact your account team…</p>` with:
```tsx
      <Link
        to="/billing?plan=premium"
        className="mt-5 inline-block rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-canvas transition hover:opacity-90"
      >
        Upgrade to Premium
      </Link>
```

- [ ] **Step 7: Run to verify.** From `apps/web`: `npm run typecheck` → clean; `npx vitest run src/features/research/PremiumGate.test.tsx` → 1 passed. The existing academy `ModuleReader`/`AskAssistant` tests render those components — if they render the nudge path WITHOUT a router, the new `<Link>` will throw ("useHref ... outside a <Router>"). Check `ModuleReader.test.tsx` / `AskAssistant.test.tsx`: if a test exercises the upgrade-nudge branch, wrap that render in `<MemoryRouter>`. Update those wrappers as needed, then `npm run test:run` → all green.

- [ ] **Step 8: Commit.**
```bash
git add apps/web/src/app/Router.tsx apps/web/src/components/Sidebar.tsx apps/web/src/components/Topbar.tsx apps/web/src/features/academy/ModuleReader.tsx apps/web/src/features/academy/AskAssistant.tsx apps/web/src/features/research/PremiumGate.tsx apps/web/src/features/research/PremiumGate.test.tsx
# also add any academy test files you had to wrap in MemoryRouter
git commit -m "feat(web): wire billing routes, nav, and the 402 upgrade nudges

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Final gate

- [ ] **Step 1: Web gate.** From `apps/web`: `npm run typecheck` (clean), `npm run lint` (clean), `npm run test:run` (all pass — expect ~+15 billing/tier tests on top of the existing suite), `npm run build` (still prerenders 17 docs; `/app/billing*` are client-only so no SSG change).
- [ ] **Step 2: Backend gate.** `ADMIN_DATABASE_URL=... APP_DATABASE_URL=... uv run pytest tests/integration/test_billing.py -q` → all pass (incl. `has_customer`).
- [ ] **Step 3: Manual smoke (optional, documented).** With `STRIPE_*` test keys set + the API + web dev server running, log in → `/app/billing` → Upgrade to Pro → Stripe test checkout → returns to `/app/billing/success` → tier flips to pro. Note in the existing `docs/runbooks/billing.md` that B2 is the UI entry (a one-line addition).

---

## Notes for the executor
- **Router context in tests:** any component using `<Link>`/`useSearchParams`/`useNavigate` must be rendered inside `<MemoryRouter>` in tests (see the wrap helpers above). This is the most likely cause of a green-unit-but-red-suite if an existing academy/research test renders the nudge branch.
- **`redirectTo` mockability:** hooks call `billing.redirectTo`/`billing.startUpgrade` via a namespace import so `vi.spyOn(billing, 'redirectTo')` works; do NOT switch to a named import or the spies won't bind.
- **No SSG impact:** all new routes are under the client-only `/app` SPA; the public Vike build is unaffected.
- **Theme tokens only:** `accent/canvas/txt/txtDim/txtFaint/line/panel/pos/neg`; no raw Tailwind colors (a reviewer will reject `red-*` etc.).
