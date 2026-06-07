# Markets & Vol Frontend (AN-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `Markets & Vol` placeholder with a ticker-driven terminal: a pivoted options-chain table + an IV smile/term-structure visualization, over `/v1/market/{iv-surface,chain}`.

**Architecture:** A `src/features/markets/` feature + `src/lib/market.ts` client. The iv-surface fetch is the backbone (expiry list + both curves); the chain is fetched per selected expiry. `vol_surface`-gated (pre-checked via `me.entitlements`). Pure presentational components (ChainTable, IvCurves, MarketsGate) + a `Markets` page that wires hooks + tabs. Client-only `/app` route (no SSG impact).

**Tech Stack:** React 18 + TS (strict), Tailwind (theme tokens only), TanStack Query, react-router 6, custom SVG (no chart lib), Vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-06-04-markets-vol-frontend-design.md`

**Conventions:** from `apps/web`: tests `npx vitest run <files>`; gate `npm run typecheck && npm run lint && npm run test:run`. Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. NEVER touch root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`. Theme tokens only (`accent/canvas/txt/txtDim/txtFaint/line/panel/panel2/pos/neg/warn`); no raw Tailwind colors; no inline `style={{}}`; double-quote JSX strings containing apostrophes.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/web/src/lib/market.ts` (create) | client `getIvSurface`/`getChain` + types |
| `apps/web/src/features/markets/ChainTable.tsx` (create) | pivoted calls\|strike\|puts table |
| `apps/web/src/features/markets/IvCurves.tsx` (create) | smile + term-structure SVGs |
| `apps/web/src/features/markets/MarketsGate.tsx` (create) | vol_surface upgrade nudge |
| `apps/web/src/features/markets/hooks.ts` (create) | useIvSurface / useChain |
| `apps/web/src/pages/Markets.tsx` (create) | the `/app/markets` page |
| `apps/web/src/app/Router.tsx` (modify) | swap placeholder → `<Markets/>` |
| `+ *.test.ts(x)` | tests |

---

## Task 1: `lib/market.ts` client + types

**Files:** Create `apps/web/src/lib/market.ts`, `apps/web/src/lib/market.test.ts`.

- [ ] **Step 1: Write the failing tests.** Create `apps/web/src/lib/market.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getIvSurface, getChain, EntitlementError } from './market'

describe('market client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('getIvSurface GETs /v1/market/iv-surface with the ticker', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ticker: 'SPY', spot: 1, expiries: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const s = await getIvSurface('SPY')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/v1/market/iv-surface?ticker=SPY')
    expect(s.ticker).toBe('SPY')
  })

  it('getChain passes the expiry param', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ticker: 'SPY', spot: 1, contracts: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await getChain('SPY', '2026-12-18')
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('/v1/market/chain?ticker=SPY')
    expect(url).toContain('expiry=2026-12-18')
  })

  it('402 throws EntitlementError with the code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO' } } }),
        { status: 402 })))
    const err = await getIvSurface('SPY').catch((e) => e)
    expect(err).toBeInstanceOf(EntitlementError)
    expect((err as EntitlementError).code).toBe('ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO')
  })
})
```

- [ ] **Step 2: Run to verify failure.** From `apps/web`: `npx vitest run src/lib/market.test.ts` → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/lib/market.ts`:

```typescript
import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError } from './strategies'

export { EntitlementError }

export interface Greeks {
  price: number
  delta: number
  gamma: number
  theta: number
  vega: number
  rho: number
  iv: number
}

export interface IvStrike { strike: number; calls: Greeks; puts: Greeks }
export interface IvExpiry { expiry: string; strikes: IvStrike[] }

export interface IvSurface {
  ticker: string
  market: string
  as_of: string
  spot: number
  expiries: IvExpiry[]
  data_provider: string
  model: string
  risk_free_source: string
  freshness_ms: number
}

export interface Contract {
  expiry: string
  strike: number
  type: 'CALL' | 'PUT'
  bid: number
  ask: number
  last: number
  volume: number
  open_interest: number
  ours: Greeks
  vendor: { iv: number; delta: number; gamma: number; theta: number; vega: number }
}

export interface Chain {
  ticker: string
  market: string
  as_of: string
  spot: number
  model: string
  risk_free_source: string
  contracts: Contract[]
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: { ...authHeaders() } })
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

export function getIvSurface(ticker: string): Promise<IvSurface> {
  return get(`/v1/market/iv-surface?ticker=${encodeURIComponent(ticker)}`)
}

export function getChain(ticker: string, expiry: string): Promise<Chain> {
  return get(`/v1/market/chain?ticker=${encodeURIComponent(ticker)}&expiry=${encodeURIComponent(expiry)}`)
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/lib/market.test.ts` → 3 passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/lib/market.ts apps/web/src/lib/market.test.ts
git commit -m "feat(web): market API client (iv-surface + chain)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: ChainTable (pivoted calls | strike | puts)

**Files:** Create `apps/web/src/features/markets/ChainTable.tsx`, `apps/web/src/features/markets/ChainTable.test.tsx`.

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/features/markets/ChainTable.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChainTable } from './ChainTable'
import type { Contract, Greeks } from '../../lib/market'

const G = (iv: number): Greeks => ({ price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv })
const C = (strike: number, type: 'CALL' | 'PUT', iv: number): Contract => ({
  expiry: '2026-12-18', strike, type, bid: 1, ask: 1.2, last: 1.1, volume: 10, open_interest: 99,
  ours: G(iv), vendor: { iv: iv - 0.001, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1 },
})

describe('ChainTable', () => {
  it('pivots a call and a put at the same strike onto one row', () => {
    render(<ChainTable contracts={[C(100, 'CALL', 0.2), C(100, 'PUT', 0.25)]} spot={101} />)
    const row = screen.getByTestId('chain-row-100')
    expect(row.textContent).toContain('20.0%')  // call iv
    expect(row.textContent).toContain('25.0%')  // put iv
  })

  it('highlights the ATM strike (nearest spot)', () => {
    render(<ChainTable contracts={[C(95, 'CALL', 0.2), C(100, 'CALL', 0.2)]} spot={101} />)
    expect(screen.getByTestId('chain-row-100')).toHaveAttribute('data-atm', 'true')
    expect(screen.getByTestId('chain-row-95')).not.toHaveAttribute('data-atm', 'true')
  })

  it('shows an empty message when there are no contracts', () => {
    render(<ChainTable contracts={[]} spot={100} />)
    expect(screen.getByTestId('chain-empty')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/features/markets/ChainTable.test.tsx` → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/features/markets/ChainTable.tsx`:

```typescript
import type { Contract } from '../../lib/market'

interface Row { strike: number; call?: Contract; put?: Contract }

function pivot(contracts: Contract[]): Row[] {
  const byStrike = new Map<number, Row>()
  for (const c of contracts) {
    const row = byStrike.get(c.strike) ?? { strike: c.strike }
    if (c.type === 'CALL') row.call = c
    else row.put = c
    byStrike.set(c.strike, row)
  }
  return [...byStrike.values()].sort((a, b) => a.strike - b.strike)
}

function nearestStrike(rows: Row[], spot: number): number | null {
  if (rows.length === 0) return null
  return rows.reduce((best, r) =>
    Math.abs(r.strike - spot) < Math.abs(best - spot) ? r.strike : best, rows[0].strike)
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
const g3 = (v: number) => v.toFixed(3)
const px = (v: number) => v.toFixed(2)

// One side's cells in display order. For puts we render the same set; the header mirrors visually.
function sideCells(c: Contract | undefined) {
  if (!c) return ['—', '—', '—', '—', '—', '—', '—', '—', '—', '—', '—']
  return [
    g3(c.ours.delta), g3(c.ours.gamma), g3(c.ours.theta), g3(c.ours.vega), g3(c.ours.rho),
    pct(c.ours.iv), px(c.bid), px(c.ask), px(c.last), String(c.volume), String(c.open_interest),
  ]
}

const COLS = ['Δ', 'Γ', 'Θ', 'V', 'ρ', 'IV', 'Bid', 'Ask', 'Last', 'Vol', 'OI']

export function ChainTable({ contracts, spot }: { contracts: Contract[]; spot: number }) {
  const rows = pivot(contracts)
  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-txtFaint" data-testid="chain-empty">No chain for this expiry.</p>
  }
  const atm = nearestStrike(rows, spot)
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="tnum w-full min-w-[860px] font-mono text-[11px]" data-testid="chain-table">
        <thead>
          <tr className="border-b border-line text-txtFaint">
            <th colSpan={11} className="px-2 py-1 text-left uppercase tracking-wider text-pos">Calls</th>
            <th className="px-2 py-1 text-center">Strike</th>
            <th colSpan={11} className="px-2 py-1 text-right uppercase tracking-wider text-neg">Puts</th>
          </tr>
          <tr className="border-b border-line text-[9px] text-txtFaint">
            {COLS.map((c, i) => <th key={`c${i}`} className="px-2 py-1 text-right">{c}</th>)}
            <th className="px-2 py-1 text-center">—</th>
            {COLS.map((c, i) => <th key={`p${i}`} className="px-2 py-1 text-right">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const isAtm = r.strike === atm
            return (
              <tr
                key={r.strike}
                data-testid={`chain-row-${r.strike}`}
                data-atm={isAtm ? 'true' : undefined}
                className={`border-b border-lineSoft ${isAtm ? 'bg-accent/10' : ''}`}
              >
                {sideCells(r.call).map((v, i) => (
                  <td key={`c${i}`} className="px-2 py-1 text-right text-txtDim">{v}</td>
                ))}
                <td className="px-2 py-1 text-center font-semibold text-txt">{r.strike}</td>
                {sideCells(r.put).map((v, i) => (
                  <td key={`p${i}`} className="px-2 py-1 text-right text-txtDim">{v}</td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/features/markets/ChainTable.test.tsx` → 3 passed. `npm run lint` → clean.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/features/markets/ChainTable.tsx apps/web/src/features/markets/ChainTable.test.tsx
git commit -m "feat(web): pivoted options-chain table (calls | strike | puts, full greeks)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: IvCurves (smile + term-structure SVGs)

**Files:** Create `apps/web/src/features/markets/IvCurves.tsx`, `apps/web/src/features/markets/IvCurves.test.tsx`.

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/features/markets/IvCurves.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { IvCurves } from './IvCurves'
import type { IvSurface, Greeks } from '../../lib/market'

const G = (iv: number): Greeks => ({ price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv })

const SURFACE: IvSurface = {
  ticker: 'SPY', market: 'US', as_of: 'x', spot: 100, data_provider: 'massive', model: 'bsm',
  risk_free_source: 'fred', freshness_ms: 0,
  expiries: [
    { expiry: '2026-07-17', strikes: [
      { strike: 95, calls: G(0.22), puts: G(0.24) },
      { strike: 100, calls: G(0.20), puts: G(0.21) },
      { strike: 105, calls: G(0.23), puts: G(0.25) }] },
    { expiry: '2026-08-21', strikes: [
      { strike: 100, calls: G(0.26), puts: G(0.27) }] },
  ],
}

describe('IvCurves', () => {
  it('renders the smile and term-structure charts', () => {
    render(<IvCurves surface={SURFACE} expiry="2026-07-17" />)
    expect(screen.getByTestId('iv-smile')).toBeInTheDocument()
    expect(screen.getByTestId('iv-term-structure')).toBeInTheDocument()
    // smile has a call polyline with 3 strikes
    expect(screen.getByTestId('iv-smile-calls').getAttribute('points')!.trim().split(' ').length).toBe(3)
    // term structure has a point per expiry (2)
    expect(screen.getByTestId('iv-term-line').getAttribute('points')!.trim().split(' ').length).toBe(2)
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/features/markets/IvCurves.test.tsx` → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/features/markets/IvCurves.tsx`:

```typescript
import type { IvSurface, IvExpiry } from '../../lib/market'

const W = 360
const H = 180
const PAD = 30

function scaler(min: number, max: number, lo: number, hi: number) {
  const span = max - min || 1
  return (v: number) => lo + (hi - lo) * ((v - min) / span)
}

function atmIv(e: IvExpiry, spot: number): number {
  const s = e.strikes.reduce((best, x) =>
    Math.abs(x.strike - spot) < Math.abs(best.strike - spot) ? x : best, e.strikes[0])
  return ((s.calls.iv + s.puts.iv) / 2) * 100
}

function pointsAttr(pts: { x: number; y: number }[]): string {
  return pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}

export function IvCurves({ surface, expiry }: { surface: IvSurface; expiry: string }) {
  const e = surface.expiries.find((x) => x.expiry === expiry) ?? surface.expiries[0]

  // ── smile (IV vs strike for `e`) ──
  const strikes = e ? e.strikes.map((s) => s.strike) : []
  const ivs = e ? e.strikes.flatMap((s) => [s.calls.iv * 100, s.puts.iv * 100]) : []
  const sx = scaler(Math.min(...strikes), Math.max(...strikes), PAD, W - PAD)
  const sy = scaler(Math.min(...ivs), Math.max(...ivs), H - PAD, PAD)
  const callPts = e ? e.strikes.map((s) => ({ x: sx(s.strike), y: sy(s.calls.iv * 100) })) : []
  const putPts = e ? e.strikes.map((s) => ({ x: sx(s.strike), y: sy(s.puts.iv * 100) })) : []

  // ── term structure (avg ATM IV per expiry) ──
  const term = surface.expiries.map((x, i) => ({ i, iv: atmIv(x, surface.spot), expiry: x.expiry }))
  const tx = scaler(0, Math.max(1, term.length - 1), PAD, W - PAD)
  const tIvs = term.map((t) => t.iv)
  const ty = scaler(Math.min(...tIvs), Math.max(...tIvs), H - PAD, PAD)
  const termPts = term.map((t) => ({ x: tx(t.i), y: ty(t.iv) }))

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <figure className="rounded-lg border border-line bg-panel p-3">
        <figcaption className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
          Smile · {expiry}
        </figcaption>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="iv-smile">
          <polyline data-testid="iv-smile-calls" points={pointsAttr(callPts)} fill="none" stroke="#37c98b" strokeWidth={1.8} />
          <polyline data-testid="iv-smile-puts" points={pointsAttr(putPts)} fill="none" stroke="#ff5d73" strokeWidth={1.8} strokeDasharray="4 3" />
        </svg>
      </figure>
      <figure className="rounded-lg border border-line bg-panel p-3">
        <figcaption className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
          ATM term structure
        </figcaption>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="iv-term-structure">
          <polyline data-testid="iv-term-line" points={pointsAttr(termPts)} fill="none" stroke="#4da3ff" strokeWidth={1.8} />
          {termPts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={2.5} fill="#4da3ff" />)}
        </svg>
      </figure>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/features/markets/IvCurves.test.tsx` → 1 passed. `npm run lint` → clean.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/features/markets/IvCurves.tsx apps/web/src/features/markets/IvCurves.test.tsx
git commit -m "feat(web): IV smile + ATM term-structure curves (custom SVG)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: MarketsGate

**Files:** Create `apps/web/src/features/markets/MarketsGate.tsx`, `apps/web/src/features/markets/MarketsGate.test.tsx`.

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/features/markets/MarketsGate.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { MarketsGate } from './MarketsGate'

describe('MarketsGate', () => {
  it('links to billing to upgrade to Pro', () => {
    render(<MemoryRouter><MarketsGate /></MemoryRouter>)
    const link = screen.getByRole('link', { name: /upgrade to pro/i })
    expect(link).toHaveAttribute('href', '/billing?plan=pro')
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/features/markets/MarketsGate.test.tsx` → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/features/markets/MarketsGate.tsx`:

```typescript
import { Link } from 'react-router-dom'

export function MarketsGate() {
  return (
    <div className="rounded-xl border border-accent/30 bg-accent/5 px-6 py-12 text-center" data-testid="markets-gate">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Pro feature</p>
      <h3 className="mt-3 text-lg font-semibold tracking-tight text-txt">
        Live chains &amp; the IV surface are a Pro feature
      </h3>
      <p className="mt-2 text-sm text-txtDim">
        Upgrade to Pro for real-time options chains with our Greeks and IV, plus the volatility
        smile and term structure for any US ticker.
      </p>
      <Link
        to="/billing?plan=pro"
        className="mt-5 inline-block rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-canvas transition hover:opacity-90"
      >
        Upgrade to Pro
      </Link>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/features/markets/MarketsGate.test.tsx` → 1 passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/features/markets/MarketsGate.tsx apps/web/src/features/markets/MarketsGate.test.tsx
git commit -m "feat(web): markets vol_surface upgrade gate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: hooks + Markets page + route

**Files:** Create `apps/web/src/features/markets/hooks.ts`, `apps/web/src/pages/Markets.tsx`, `apps/web/src/pages/Markets.test.tsx`; Modify `apps/web/src/app/Router.tsx`.

- [ ] **Step 1: Implement the hooks.** Create `apps/web/src/features/markets/hooks.ts`:

```typescript
import { useQuery } from '@tanstack/react-query'
import { getIvSurface, getChain } from '../../lib/market'

export function useIvSurface(ticker: string) {
  return useQuery({
    queryKey: ['iv-surface', ticker],
    queryFn: () => getIvSurface(ticker),
    enabled: !!ticker,
    retry: false,
  })
}

export function useChain(ticker: string, expiry: string, enabled: boolean) {
  return useQuery({
    queryKey: ['chain', ticker, expiry],
    queryFn: () => getChain(ticker, expiry),
    enabled: enabled && !!ticker && !!expiry,
    retry: false,
  })
}
```

- [ ] **Step 2: Write the failing page tests.** Create `apps/web/src/pages/Markets.test.tsx`:

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as market from '../lib/market'
import { Markets } from './Markets'

let mockMe: { entitlements: Record<string, boolean | number> } | null
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ me: mockMe }) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const SURFACE = {
  ticker: 'SPY', market: 'US', as_of: 'x', spot: 100, data_provider: 'massive', model: 'bsm',
  risk_free_source: 'fred', freshness_ms: 0,
  expiries: [{ expiry: '2026-07-17', strikes: [{ strike: 100,
    calls: { price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv: 0.2 },
    puts: { price: 1, delta: -0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: -0.05, iv: 0.21 } }] }],
}

describe('Markets page', () => {
  beforeEach(() => { vi.restoreAllMocks(); mockMe = { entitlements: { vol_surface: true } } })

  it('shows the upgrade gate for a free user and does not fetch', () => {
    mockMe = { entitlements: { vol_surface: false } }
    const spy = vi.spyOn(market, 'getIvSurface')
    render(wrap(<Markets />))
    expect(screen.getByTestId('markets-gate')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  it('loads a ticker and shows the spot + tabs for an entitled user', async () => {
    vi.spyOn(market, 'getIvSurface').mockResolvedValue(SURFACE as never)
    render(wrap(<Markets />))
    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'SPY' } })
    fireEvent.click(screen.getByTestId('ticker-load'))
    await waitFor(() => expect(screen.getByTestId('markets-header').textContent).toMatch(/100/))
    expect(screen.getByTestId('tab-vol')).toBeInTheDocument()
    expect(screen.getByTestId('iv-smile')).toBeInTheDocument()  // Vol Surface tab default
  })
})
```

- [ ] **Step 3: Run to verify failure.** `npx vitest run src/pages/Markets.test.tsx` → FAIL.

- [ ] **Step 4: Implement** `apps/web/src/pages/Markets.tsx`:

```typescript
import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useIvSurface, useChain } from '../features/markets/hooks'
import { ChainTable } from '../features/markets/ChainTable'
import { IvCurves } from '../features/markets/IvCurves'
import { MarketsGate } from '../features/markets/MarketsGate'
import { EntitlementError } from '../lib/market'

export function Markets() {
  const { me } = useAuth()
  const entitled = me?.entitlements?.vol_surface === true

  const [input, setInput] = useState('')
  const [ticker, setTicker] = useState('')
  const [expiry, setExpiry] = useState<string | null>(null)
  const [tab, setTab] = useState<'chain' | 'vol'>('vol')

  const surfaceQ = useIvSurface(entitled ? ticker : '')
  const surface = surfaceQ.data
  const activeExpiry = expiry ?? surface?.expiries[0]?.expiry ?? ''
  const chainQ = useChain(ticker, activeExpiry, entitled && tab === 'chain')

  if (!entitled) return <MarketsGate />
  if (surfaceQ.error instanceof EntitlementError || chainQ.error instanceof EntitlementError) {
    return <MarketsGate />
  }

  function load() {
    const t = input.trim().toUpperCase()
    if (t) { setTicker(t); setExpiry(null) }
  }

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Markets &amp; Vol</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Options chain &amp; volatility</h2>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          data-testid="ticker-input"
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
          onKeyDown={(e) => { if (e.key === 'Enter') load() }}
          placeholder="e.g. SPY"
          maxLength={8}
          className="w-32 rounded-lg border border-line bg-canvas px-3 py-2 font-mono text-sm uppercase tracking-wider text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none"
        />
        <button
          data-testid="ticker-load"
          onClick={load}
          className="rounded-lg bg-accent/20 px-4 py-2 text-xs text-accent transition hover:bg-accent/30"
        >
          Load
        </button>
        {ticker && (
          <button
            data-testid="ticker-refresh"
            onClick={() => { void surfaceQ.refetch(); void chainQ.refetch() }}
            className="rounded-lg border border-line px-3 py-2 text-xs text-txtDim transition hover:text-txt"
          >
            Refresh
          </button>
        )}
      </div>

      {surfaceQ.isLoading && ticker && (
        <div className="animate-pulse rounded-lg border border-line bg-panel2 py-16" data-testid="markets-loading" />
      )}

      {surfaceQ.isError && !(surfaceQ.error instanceof EntitlementError) && (
        <p className="text-sm text-neg" data-testid="markets-error">
          {(surfaceQ.error as Error).message === 'MARKET_DATA_PROVIDER_UNAVAILABLE'
            ? 'Market data is temporarily unavailable — try again.'
            : 'No data for that ticker.'}
        </p>
      )}

      {surface && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-xs text-txtDim" data-testid="markets-header">
            <span className="font-mono text-txt">{surface.ticker}</span>
            <span>spot <span className="tnum text-txt">{surface.spot.toFixed(2)}</span></span>
            <span className="text-txtFaint">· {surface.data_provider} · {new Date(surface.as_of).toLocaleString()}</span>
            <select
              data-testid="expiry-select"
              value={activeExpiry}
              onChange={(e) => setExpiry(e.target.value)}
              className="ml-auto rounded border border-line bg-panel px-2 py-1 font-mono text-xs text-txt"
            >
              {surface.expiries.map((x) => <option key={x.expiry} value={x.expiry}>{x.expiry}</option>)}
            </select>
          </div>

          <div className="flex gap-2 border-b border-line">
            <button
              data-testid="tab-vol"
              onClick={() => setTab('vol')}
              className={`px-3 py-2 text-xs ${tab === 'vol' ? 'border-b-2 border-accent text-txt' : 'text-txtDim'}`}
            >
              Vol Surface
            </button>
            <button
              data-testid="tab-chain"
              onClick={() => setTab('chain')}
              className={`px-3 py-2 text-xs ${tab === 'chain' ? 'border-b-2 border-accent text-txt' : 'text-txtDim'}`}
            >
              Chain
            </button>
          </div>

          {tab === 'vol' ? (
            <IvCurves surface={surface} expiry={activeExpiry} />
          ) : chainQ.isLoading ? (
            <div className="animate-pulse rounded-lg border border-line bg-panel2 py-16" />
          ) : chainQ.data ? (
            <ChainTable contracts={chainQ.data.contracts} spot={surface.spot} />
          ) : null}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Wire the route.** In `apps/web/src/app/Router.tsx`: add `import { Markets } from '../pages/Markets'` and replace `<Route path="markets" element={<PlaceholderPage title="Markets & Vol" />} />` with `<Route path="markets" element={<Markets />} />`.

- [ ] **Step 6: Run to verify pass.** `npx vitest run src/pages/Markets.test.tsx` → 2 passed. `npm run typecheck` → clean; `npm run lint` → clean.

- [ ] **Step 7: Commit.**
```bash
git add apps/web/src/features/markets/hooks.ts apps/web/src/pages/Markets.tsx apps/web/src/pages/Markets.test.tsx apps/web/src/app/Router.tsx
git commit -m "feat(web): Markets & Vol page (chain + IV tabs, ticker-driven, gated)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Final gate

- [ ] **Step 1: Web gate.** From `apps/web`: `npm run typecheck` (clean), `npm run lint` (clean), `npm run test:run` (all pass — expect ~+10 markets tests on top of the existing 194), `npm run build` (still prerenders 17 docs; `/app/markets` is client-only — no SSG change).
- [ ] **Step 2:** Confirm no stray raw-color/inline-style lint issues in the new files.

---

## Notes for the executor
- **Router context in tests:** `MarketsGate` (and the page, which can render it) use `<Link>` — render inside `<MemoryRouter>` in tests (the wrap helpers above do this).
- **`useAuth` mock:** the page reads `me.entitlements.vol_surface`; tests mock `../auth/AuthContext` with a mutable `mockMe`.
- **Expiry default:** `activeExpiry = expiry ?? surface?.expiries[0]?.expiry ?? ''` — no effect needed; selecting an expiry sets `expiry`, loading a new ticker resets it to `null` so it re-defaults.
- **Chain fetched lazily:** `useChain` is enabled only on the Chain tab (`tab === 'chain'`) so the Vol Surface tab (default) never triggers the heavier chain fetch.
- **Theme tokens only:** the SVG strokes use hex literals (`#37c98b`/`#ff5d73`/`#4da3ff`) which match the existing `PayoffChart` convention for SVG strokes — that's allowed (PayoffChart does the same); Tailwind class colors must stay tokens.
