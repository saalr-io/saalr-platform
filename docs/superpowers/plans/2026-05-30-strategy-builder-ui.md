# Strategy Builder UI (7b) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Sensibull-inspired, chart-first strategy builder at `/strategies` — custom SVG payoff chart (expiry + target-date), stats, ready-made templates, build-your-own leg editor, save/list — consuming the 7a backend.

**Architecture:** React 18 + Vite + Tailwind + React Query (existing stack, no new deps). Feature folder `src/features/strategies/`; typed HTTP client in `lib/strategies.ts`; pure chart math isolated in `scale.ts`. CRUD + pure payoff for all tiers; live analysis (Greeks/POP/target-date) is `vol_surface`-gated and surfaces a 402 as an upgrade nudge.

**Tech Stack:** TypeScript, React 18, react-router-dom 6, @tanstack/react-query 5, Tailwind 3, vitest + @testing-library/react (fireEvent; no user-event dep).

**Spec:** `docs/superpowers/specs/2026-05-30-strategy-builder-ui-design.md`

**Run all web commands from `apps/web/`** (e.g. `cd apps/web && pnpm test:run`). The dark theme tokens used below already exist in Tailwind config: `bg-panel`, `bg-canvas`, `border-line`, `text-txt`/`txtDim`/`txtFaint`, `bg-pos` (green), plus `animate-fadeUp`.

## File structure

```
apps/web/src/
  lib/api.ts                         # MODIFY: export BASE + authHeaders for reuse
  lib/strategies.ts                  # client + TS types + EntitlementError
  features/strategies/
    scale.ts                         # PURE curve -> SVG-pixel math
    hooks.ts                         # React Query hooks
    PayoffChart.tsx                  # presentational SVG chart
    StatsPanel.tsx                   # stat cards
    LegEditor.tsx                    # leg rows + underlying/expiry
    TemplatePicker.tsx               # ready-made chips
    SavedList.tsx                    # saved strategies list
  pages/Strategies.tsx               # route: tabs + orchestration (layout B)
  main.tsx                           # MODIFY: /strategies -> <Strategies/>
  (tests colocated as *.test.ts(x))
```

---

## Task 1: HTTP client + types (`lib/strategies.ts`)

**Files:**
- Modify: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/lib/strategies.ts`
- Test: `apps/web/src/lib/strategies.test.ts`

- [ ] **Step 1: Export the shared base + headers from api.ts**

In `apps/web/src/lib/api.ts`, change `const BASE = ...` to `export const BASE = ...` and change `function authHeaders()` to `export function authHeaders()`. Leave the rest unchanged.

- [ ] **Step 2: Write failing tests**

Create `apps/web/src/lib/strategies.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { analyzeStrategy, listTemplates, EntitlementError } from './strategies'

const cfg = { underlying: 'AAPL', legs: [
  { kind: 'option' as const, option_type: 'CALL' as const, side: 'BUY' as const,
    strike: 100, expiry: '2026-12-18', qty: 1, entry_price: 6 },
] }

describe('strategies client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('analyze returns parsed result on 200', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ expiration_curve: [{ spot: 100, pnl: -400 }], breakevens: [104],
        max_profit: 600, max_loss: -400, unbounded_profit: false, unbounded_loss: false,
        net_premium: 400, risk_reward: 1.5 }), { status: 200 })))
    const r = await analyzeStrategy(cfg, { live: false })
    expect(r.breakevens).toEqual([104])
    expect(r.max_profit).toBe(600)
  })

  it('throws EntitlementError on 402', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO' } } }),
      { status: 402 })))
    await expect(analyzeStrategy(cfg, { live: true })).rejects.toBeInstanceOf(EntitlementError)
  })

  it('listTemplates returns the array', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ templates: [{ key: 'iron_condor', name: 'Iron Condor',
        category: 'neutral', description: '...' }] }), { status: 200 })))
    const t = await listTemplates()
    expect(t[0].key).toBe('iron_condor')
  })
})
```

- [ ] **Step 3: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/lib/strategies.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement strategies.ts**

Create `apps/web/src/lib/strategies.ts`:

```ts
import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'

export type OptionType = 'CALL' | 'PUT'
export type Side = 'BUY' | 'SELL'

export interface OptionLeg {
  kind: 'option'; option_type: OptionType; side: Side
  strike: number; expiry: string; qty: number; entry_price?: number | null
}
export interface EquityLeg { kind: 'equity'; side: Side; qty: number; entry_price?: number | null }
export interface CashLeg { kind: 'cash'; amount: number }
export type Leg = OptionLeg | EquityLeg | CashLeg

export interface StrategyConfig { underlying: string; legs: Leg[] }

export interface Strategy {
  strategy_id: string; name: string; description: string | null
  state: string; market: string; config: StrategyConfig
  created_at: string; updated_at: string
}

export interface TemplateDescriptor {
  key: string; name: string; category: 'bullish' | 'bearish' | 'neutral'; description: string
}

export interface CurvePoint { spot: number; pnl: number }

export interface AnalyzeResult {
  expiration_curve: CurvePoint[]
  breakevens: number[]
  max_profit: number | null
  max_loss: number | null
  unbounded_profit: boolean
  unbounded_loss: boolean
  net_premium: number
  risk_reward: number | null
  // live-only:
  net_greeks?: { delta: number; gamma: number; theta: number; vega: number; rho: number }
  probability_of_profit?: { pop: number | null; method: string; approximate: boolean }
  target_date_curve?: CurvePoint[]
  spot?: number
  data_provider?: string
  risk_free_source?: string
}

export class EntitlementError extends Error {
  code: string
  constructor(code: string) {
    super('entitlement required')
    this.name = 'EntitlementError'
    this.code = code
  }
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

export function listStrategies(cursor?: string): Promise<{ strategies: Strategy[]; next_cursor: string | null }> {
  return request(`/v1/strategies${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`)
}
export function getStrategy(id: string): Promise<Strategy> {
  return request(`/v1/strategies/${id}`)
}
export function createStrategy(body: { name: string; description?: string; market?: string; config: StrategyConfig }): Promise<Strategy> {
  return request('/v1/strategies', { method: 'POST', body: JSON.stringify(body) })
}
export function transitionStrategy(id: string, target_state: string): Promise<Strategy> {
  return request(`/v1/strategies/${id}/transition`, { method: 'POST', body: JSON.stringify({ target_state }) })
}
export function archiveStrategy(id: string): Promise<Strategy> {
  return request(`/v1/strategies/${id}`, { method: 'DELETE' })
}
export async function listTemplates(): Promise<TemplateDescriptor[]> {
  const r = await request<{ templates: TemplateDescriptor[] }>('/v1/strategies/templates')
  return r.templates
}
export async function buildTemplate(
  key: string, params: { underlying: string; expiry: string; atm_strike: number; width?: number },
): Promise<StrategyConfig> {
  const r = await request<{ underlying: string; legs: Leg[] }>(
    `/v1/strategies/templates/${key}/build`, { method: 'POST', body: JSON.stringify(params) })
  return { underlying: r.underlying, legs: r.legs }
}
export function analyzeStrategy(
  config: StrategyConfig, opts: { target_date?: string; live?: boolean },
): Promise<AnalyzeResult> {
  return request('/v1/strategies/analyze', {
    method: 'POST',
    body: JSON.stringify({ config, target_date: opts.target_date, live: opts.live ?? false }),
  })
}
```

- [ ] **Step 5: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/lib/strategies.test.ts`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/api.ts apps/web/src/lib/strategies.ts apps/web/src/lib/strategies.test.ts
git commit -m "feat(web): strategies API client + types + EntitlementError"
```

---

## Task 2: Pure chart math (`features/strategies/scale.ts`)

**Files:**
- Create: `apps/web/src/features/strategies/scale.ts`
- Test: `apps/web/src/features/strategies/scale.test.ts`

- [ ] **Step 1: Write failing tests**

Create `apps/web/src/features/strategies/scale.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { computeBounds, toPixels, xForSpot, yForPnl } from './scale'

const DIMS = { width: 100, height: 100, padX: 0, padY: 0 }

describe('scale', () => {
  it('computeBounds spans all curves', () => {
    const b = computeBounds([[{ spot: 80, pnl: -10 }, { spot: 120, pnl: 30 }]])
    expect(b).toEqual({ minS: 80, maxS: 120, minP: -10, maxP: 30 })
  })

  it('xForSpot maps left/right edges', () => {
    const b = { minS: 80, maxS: 120, minP: -10, maxP: 30 }
    expect(xForSpot(80, b, DIMS)).toBeCloseTo(0)
    expect(xForSpot(120, b, DIMS)).toBeCloseTo(100)
  })

  it('yForPnl inverts (max P&L at top)', () => {
    const b = { minS: 80, maxS: 120, minP: -10, maxP: 30 }
    expect(yForPnl(30, b, DIMS)).toBeCloseTo(0)
    expect(yForPnl(-10, b, DIMS)).toBeCloseTo(100)
  })

  it('toPixels maps a curve', () => {
    const b = { minS: 0, maxS: 100, minP: 0, maxP: 100 }
    const px = toPixels([{ spot: 0, pnl: 0 }, { spot: 100, pnl: 100 }], b, DIMS)
    expect(px[0]).toEqual({ x: 0, y: 100 })
    expect(px[1]).toEqual({ x: 100, y: 0 })
  })

  it('flat P&L range does not divide by zero', () => {
    const b = computeBounds([[{ spot: 50, pnl: 5 }, { spot: 60, pnl: 5 }]])
    const y = yForPnl(5, b, DIMS)
    expect(Number.isFinite(y)).toBe(true)
  })

  it('empty curves yield a safe default span', () => {
    const b = computeBounds([])
    expect(Number.isFinite(b.minS) && Number.isFinite(b.maxP)).toBe(true)
  })
})
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/features/strategies/scale.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement scale.ts**

Create `apps/web/src/features/strategies/scale.ts`:

```ts
import type { CurvePoint } from '../../lib/strategies'

export interface Bounds { minS: number; maxS: number; minP: number; maxP: number }
export interface Dims { width: number; height: number; padX: number; padY: number }

export function computeBounds(curves: CurvePoint[][]): Bounds {
  const pts = curves.flat()
  if (pts.length === 0) return { minS: 0, maxS: 1, minP: -1, maxP: 1 }
  let minS = Infinity, maxS = -Infinity, minP = Infinity, maxP = -Infinity
  for (const p of pts) {
    if (p.spot < minS) minS = p.spot
    if (p.spot > maxS) maxS = p.spot
    if (p.pnl < minP) minP = p.pnl
    if (p.pnl > maxP) maxP = p.pnl
  }
  if (minS === maxS) { minS -= 1; maxS += 1 }
  if (minP === maxP) { minP -= 1; maxP += 1 }
  return { minS, maxS, minP, maxP }
}

export function xForSpot(spot: number, b: Bounds, d: Dims): number {
  const inner = d.width - 2 * d.padX
  return d.padX + ((spot - b.minS) / (b.maxS - b.minS)) * inner
}

export function yForPnl(pnl: number, b: Bounds, d: Dims): number {
  const inner = d.height - 2 * d.padY
  return d.padY + (1 - (pnl - b.minP) / (b.maxP - b.minP)) * inner
}

export function toPixels(curve: CurvePoint[], b: Bounds, d: Dims): { x: number; y: number }[] {
  return curve.map((p) => ({ x: xForSpot(p.spot, b, d), y: yForPnl(p.pnl, b, d) }))
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/features/strategies/scale.test.ts`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/strategies/scale.ts apps/web/src/features/strategies/scale.test.ts
git commit -m "feat(web): pure payoff-chart coordinate math"
```

---

## Task 3: React Query hooks (`features/strategies/hooks.ts`)

**Files:**
- Create: `apps/web/src/features/strategies/hooks.ts`

- [ ] **Step 1: Implement hooks.ts**

Create `apps/web/src/features/strategies/hooks.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  analyzeStrategy, archiveStrategy, buildTemplate, createStrategy, listStrategies,
  listTemplates, transitionStrategy,
  type AnalyzeResult, type StrategyConfig,
} from '../../lib/strategies'

export function useStrategies() {
  return useQuery({ queryKey: ['strategies'], queryFn: () => listStrategies() })
}

export function useTemplates() {
  return useQuery({ queryKey: ['templates'], queryFn: listTemplates, staleTime: 60 * 60 * 1000 })
}

export function useCreateStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createStrategy,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}

export function useArchive() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => archiveStrategy(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}

export function useTransition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, target }: { id: string; target: string }) => transitionStrategy(id, target),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['strategies'] }),
  })
}

export function useAnalyze() {
  return useMutation<AnalyzeResult, Error, { config: StrategyConfig; live: boolean; target_date?: string }>({
    mutationFn: ({ config, live, target_date }) => analyzeStrategy(config, { live, target_date }),
  })
}

export function useBuildTemplate() {
  return useMutation({
    mutationFn: ({ key, params }: { key: string; params: { underlying: string; expiry: string; atm_strike: number; width?: number } }) =>
      buildTemplate(key, params),
  })
}
```

- [ ] **Step 2: Verify it typechecks**

Run: `cd apps/web && pnpm typecheck`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/features/strategies/hooks.ts
git commit -m "feat(web): react-query hooks for strategies"
```

---

## Task 4: Payoff chart (`features/strategies/PayoffChart.tsx`)

**Files:**
- Create: `apps/web/src/features/strategies/PayoffChart.tsx`
- Test: `apps/web/src/features/strategies/PayoffChart.test.tsx`

- [ ] **Step 1: Write failing test**

Create `apps/web/src/features/strategies/PayoffChart.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PayoffChart } from './PayoffChart'

const expiration = [
  { spot: 80, pnl: -400 }, { spot: 100, pnl: -400 },
  { spot: 110, pnl: 600 }, { spot: 130, pnl: 600 },
]

describe('PayoffChart', () => {
  it('renders the expiration polyline', () => {
    render(<PayoffChart expirationCurve={expiration} breakevens={[104]} />)
    expect(screen.getByTestId('payoff-expiry')).toBeInTheDocument()
  })

  it('renders the target-date path only when provided', () => {
    const { rerender } = render(<PayoffChart expirationCurve={expiration} breakevens={[]} />)
    expect(screen.queryByTestId('payoff-target')).not.toBeInTheDocument()
    rerender(<PayoffChart expirationCurve={expiration} targetDateCurve={expiration} breakevens={[]} />)
    expect(screen.getByTestId('payoff-target')).toBeInTheDocument()
  })

  it('renders a breakeven marker per breakeven', () => {
    render(<PayoffChart expirationCurve={expiration} breakevens={[104, 116]} />)
    expect(screen.getAllByTestId('payoff-be')).toHaveLength(2)
  })

  it('renders the spot marker when spot given', () => {
    render(<PayoffChart expirationCurve={expiration} breakevens={[]} spot={100} />)
    expect(screen.getByTestId('payoff-spot')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/features/strategies/PayoffChart.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement PayoffChart.tsx**

Create `apps/web/src/features/strategies/PayoffChart.tsx`:

```tsx
import { useState } from 'react'
import type { CurvePoint } from '../../lib/strategies'
import { computeBounds, toPixels, xForSpot, yForPnl, type Dims } from './scale'

const W = 720, H = 240
const DIMS: Dims = { width: W, height: H, padX: 44, padY: 18 }

function pathFrom(points: { x: number; y: number }[]): string {
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}

export function PayoffChart({
  expirationCurve, targetDateCurve, breakevens, spot,
}: {
  expirationCurve: CurvePoint[]
  targetDateCurve?: CurvePoint[]
  breakevens: number[]
  spot?: number
}) {
  const [hover, setHover] = useState<CurvePoint | null>(null)
  const curves = targetDateCurve ? [expirationCurve, targetDateCurve] : [expirationCurve]
  const b = computeBounds(curves)
  const zeroY = yForPnl(0, b, DIMS)
  const expPx = toPixels(expirationCurve, b, DIMS)

  // profit (green) / loss (red) fill polygons vs the zero line
  const areaPath = (sign: 1 | -1) => {
    const clipped = expPx.map((p, i) => ({
      x: p.x,
      y: sign === 1 ? Math.min(p.y, zeroY) : Math.max(p.y, zeroY),
      pnl: expirationCurve[i].pnl,
    }))
    return `${pathFrom(clipped)} L${clipped[clipped.length - 1].x.toFixed(1)},${zeroY.toFixed(1)} L${clipped[0].x.toFixed(1)},${zeroY.toFixed(1)} Z`
  }

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    let nearest = expirationCurve[0]
    let best = Infinity
    for (const p of expirationCurve) {
      const d = Math.abs(xForSpot(p.spot, b, DIMS) - px)
      if (d < best) { best = d; nearest = p }
    }
    setHover(nearest)
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-md border border-line bg-canvas/60"
         onMouseMove={onMove} onMouseLeave={() => setHover(null)} data-testid="payoff-chart">
      <path d={areaPath(1)} fill="rgba(46,160,110,0.16)" />
      <path d={areaPath(-1)} fill="rgba(220,70,70,0.14)" />
      <line x1={DIMS.padX} y1={zeroY} x2={W - DIMS.padX} y2={zeroY} stroke="#2a3340" />
      {targetDateCurve && (
        <path data-testid="payoff-target" d={pathFrom(toPixels(targetDateCurve, b, DIMS))}
              fill="none" stroke="#5b9bd5" strokeWidth={1.6} strokeDasharray="5 4" />
      )}
      <path data-testid="payoff-expiry" d={pathFrom(expPx)} fill="none" stroke="#37c98b" strokeWidth={2.2} />
      {spot !== undefined && (
        <line data-testid="payoff-spot" x1={xForSpot(spot, b, DIMS)} y1={DIMS.padY}
              x2={xForSpot(spot, b, DIMS)} y2={H - DIMS.padY} stroke="#3a4660" strokeDasharray="3 3" />
      )}
      {breakevens.map((be, i) => (
        <circle key={i} data-testid="payoff-be" cx={xForSpot(be, b, DIMS)} cy={zeroY} r={3.5} fill="#e8c24a" />
      ))}
      {hover && (
        <g>
          <line x1={xForSpot(hover.spot, b, DIMS)} y1={DIMS.padY} x2={xForSpot(hover.spot, b, DIMS)}
                y2={H - DIMS.padY} stroke="#2a3340" />
          <text x={xForSpot(hover.spot, b, DIMS) + 6} y={DIMS.padY + 14} className="fill-txtDim" fontSize="11"
                data-testid="payoff-hover">@ {hover.spot.toFixed(1)} · P&amp;L {hover.pnl.toFixed(0)}</text>
        </g>
      )}
    </svg>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/features/strategies/PayoffChart.test.tsx`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/strategies/PayoffChart.tsx apps/web/src/features/strategies/PayoffChart.test.tsx
git commit -m "feat(web): SVG payoff chart (expiry + target-date, zones, markers, hover)"
```

---

## Task 5: Stats panel (`features/strategies/StatsPanel.tsx`)

**Files:**
- Create: `apps/web/src/features/strategies/StatsPanel.tsx`
- Test: `apps/web/src/features/strategies/StatsPanel.test.tsx`

- [ ] **Step 1: Write failing test**

Create `apps/web/src/features/strategies/StatsPanel.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatsPanel } from './StatsPanel'
import type { AnalyzeResult } from '../../lib/strategies'

const base: AnalyzeResult = {
  expiration_curve: [], breakevens: [104], max_profit: 600, max_loss: -400,
  unbounded_profit: false, unbounded_loss: false, net_premium: 400, risk_reward: 1.5,
}

describe('StatsPanel', () => {
  it('shows Unbounded when the flag is set', () => {
    render(<StatsPanel result={{ ...base, max_profit: null, unbounded_profit: true }} />)
    expect(screen.getByTestId('stat-max-profit')).toHaveTextContent('Unbounded')
  })

  it('hides live-only stats and shows upgrade hint when absent', () => {
    render(<StatsPanel result={base} />)
    expect(screen.queryByTestId('stat-greeks')).not.toBeInTheDocument()
    expect(screen.getByTestId('upgrade-hint')).toBeInTheDocument()
  })

  it('shows greeks + POP when present', () => {
    render(<StatsPanel result={{ ...base,
      net_greeks: { delta: 12, gamma: 1, theta: -5, vega: 8, rho: 0 },
      probability_of_profit: { pop: 0.58, method: 'lognormal_atm_iv', approximate: true } }} />)
    expect(screen.getByTestId('stat-greeks')).toBeInTheDocument()
    expect(screen.getByTestId('stat-pop')).toHaveTextContent('58')
  })
})
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/features/strategies/StatsPanel.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement StatsPanel.tsx**

Create `apps/web/src/features/strategies/StatsPanel.tsx`:

```tsx
import type { AnalyzeResult } from '../../lib/strategies'

function Card({ label, value, tone, testid }: { label: string; value: string; tone?: 'pos' | 'neg'; testid: string }) {
  const color = tone === 'pos' ? 'text-pos' : tone === 'neg' ? 'text-red-400' : 'text-txt'
  return (
    <div className="flex-1 rounded-md border border-line bg-panel/60 p-2 text-center" data-testid={testid}>
      <div className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">{label}</div>
      <div className={`text-sm ${color}`}>{value}</div>
    </div>
  )
}

export function StatsPanel({ result }: { result: AnalyzeResult }) {
  const maxP = result.unbounded_profit ? 'Unbounded' : result.max_profit?.toFixed(0) ?? '—'
  const maxL = result.unbounded_loss ? 'Unbounded' : result.max_loss?.toFixed(0) ?? '—'
  const g = result.net_greeks
  const pop = result.probability_of_profit?.pop
  return (
    <div>
      <div className="flex gap-2">
        <Card label="Max Profit" value={maxP} tone="pos" testid="stat-max-profit" />
        <Card label="Max Loss" value={maxL} tone="neg" testid="stat-max-loss" />
        <Card label="Breakeven" value={result.breakevens.map((b) => b.toFixed(1)).join(', ') || '—'} testid="stat-be" />
        <Card label="Net Premium" value={result.net_premium.toFixed(0)} testid="stat-net" />
        {pop !== undefined && pop !== null && (
          <Card label="POP*" value={`${Math.round(pop * 100)}%`} testid="stat-pop" />
        )}
        {g && (
          <div className="flex-1 rounded-md border border-line bg-panel/60 p-2 text-center" data-testid="stat-greeks">
            <div className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">Δ / Θ / V</div>
            <div className="text-xs text-txt">{g.delta.toFixed(0)} / {g.theta.toFixed(0)} / {g.vega.toFixed(0)}</div>
          </div>
        )}
      </div>
      {!g && (
        <div className="mt-2 text-[11px] text-txtFaint" data-testid="upgrade-hint">
          Upgrade to Pro for live Greeks, probability of profit, and the target-date curve.
        </div>
      )}
      {result.probability_of_profit?.approximate && (
        <div className="mt-1 font-mono text-[9px] text-txtFaint">* POP approximate (lognormal).</div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/features/strategies/StatsPanel.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/strategies/StatsPanel.tsx apps/web/src/features/strategies/StatsPanel.test.tsx
git commit -m "feat(web): stats panel (unbounded-aware, live-only gating)"
```

---

## Task 6: Leg editor (`features/strategies/LegEditor.tsx`)

**Files:**
- Create: `apps/web/src/features/strategies/LegEditor.tsx`
- Test: `apps/web/src/features/strategies/LegEditor.test.tsx`

- [ ] **Step 1: Write failing test**

Create `apps/web/src/features/strategies/LegEditor.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LegEditor } from './LegEditor'
import type { StrategyConfig } from '../../lib/strategies'

const cfg: StrategyConfig = {
  underlying: 'AAPL',
  legs: [{ kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1, entry_price: 6 }],
}

describe('LegEditor', () => {
  it('adds a leg', () => {
    const onChange = vi.fn()
    render(<LegEditor config={cfg} onChange={onChange} />)
    fireEvent.click(screen.getByTestId('add-leg'))
    expect(onChange).toHaveBeenCalled()
    const next = onChange.mock.calls.at(-1)![0] as StrategyConfig
    expect(next.legs).toHaveLength(2)
  })

  it('removes a leg', () => {
    const onChange = vi.fn()
    render(<LegEditor config={cfg} onChange={onChange} />)
    fireEvent.click(screen.getByTestId('remove-leg-0'))
    expect((onChange.mock.calls.at(-1)![0] as StrategyConfig).legs).toHaveLength(0)
  })

  it('edits the strike of a leg', () => {
    const onChange = vi.fn()
    render(<LegEditor config={cfg} onChange={onChange} />)
    fireEvent.change(screen.getByTestId('strike-0'), { target: { value: '105' } })
    const leg = (onChange.mock.calls.at(-1)![0] as StrategyConfig).legs[0]
    expect(leg.kind === 'option' && leg.strike).toBe(105)
  })

  it('edits the underlying', () => {
    const onChange = vi.fn()
    render(<LegEditor config={cfg} onChange={onChange} />)
    fireEvent.change(screen.getByTestId('underlying'), { target: { value: 'TSLA' } })
    expect((onChange.mock.calls.at(-1)![0] as StrategyConfig).underlying).toBe('TSLA')
  })
})
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/features/strategies/LegEditor.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement LegEditor.tsx**

Create `apps/web/src/features/strategies/LegEditor.tsx`:

```tsx
import type { Leg, OptionLeg, StrategyConfig } from '../../lib/strategies'

const FIELD = 'rounded border border-line bg-canvas px-2 py-1 text-xs text-txt'

function newOptionLeg(): OptionLeg {
  return { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1, entry_price: null }
}

export function LegEditor({ config, onChange }: { config: StrategyConfig; onChange: (c: StrategyConfig) => void }) {
  function patchLeg(i: number, patch: Partial<OptionLeg>) {
    const legs = config.legs.map((l, idx) => (idx === i ? { ...l, ...patch } as Leg : l))
    onChange({ ...config, legs })
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <label className="text-[11px] text-txtDim">Underlying</label>
        <input data-testid="underlying" className={FIELD} value={config.underlying}
               onChange={(e) => onChange({ ...config, underlying: e.target.value.toUpperCase() })} />
      </div>
      {config.legs.map((leg, i) => (
        <div key={i} className="flex items-center gap-2" data-testid={`leg-${i}`}>
          {leg.kind === 'option' ? (
            <>
              <select className={FIELD} data-testid={`side-${i}`} value={leg.side}
                      onChange={(e) => patchLeg(i, { side: e.target.value as OptionLeg['side'] })}>
                <option>BUY</option><option>SELL</option>
              </select>
              <select className={FIELD} data-testid={`type-${i}`} value={leg.option_type}
                      onChange={(e) => patchLeg(i, { option_type: e.target.value as OptionLeg['option_type'] })}>
                <option>CALL</option><option>PUT</option>
              </select>
              <input className={`${FIELD} w-20`} data-testid={`strike-${i}`} type="number" value={leg.strike}
                     onChange={(e) => patchLeg(i, { strike: Number(e.target.value) })} />
              <input className={`${FIELD} w-32`} data-testid={`expiry-${i}`} type="date" value={leg.expiry}
                     onChange={(e) => patchLeg(i, { expiry: e.target.value })} />
              <input className={`${FIELD} w-16`} data-testid={`qty-${i}`} type="number" value={leg.qty}
                     onChange={(e) => patchLeg(i, { qty: Number(e.target.value) })} />
              <input className={`${FIELD} w-20`} data-testid={`entry-${i}`} type="number" placeholder="price"
                     value={leg.entry_price ?? ''} onChange={(e) => patchLeg(i, { entry_price: e.target.value === '' ? null : Number(e.target.value) })} />
            </>
          ) : (
            <span className="text-xs text-txtDim">{leg.kind} leg</span>
          )}
          <button className="text-xs text-red-400" data-testid={`remove-leg-${i}`}
                  onClick={() => onChange({ ...config, legs: config.legs.filter((_, idx) => idx !== i) })}>✕</button>
        </div>
      ))}
      <button className="rounded border border-line bg-panel px-3 py-1 text-xs text-txtDim hover:text-txt"
              data-testid="add-leg" onClick={() => onChange({ ...config, legs: [...config.legs, newOptionLeg()] })}>
        + add leg
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/features/strategies/LegEditor.test.tsx`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/strategies/LegEditor.tsx apps/web/src/features/strategies/LegEditor.test.tsx
git commit -m "feat(web): multi-leg editor"
```

---

## Task 7: Template picker (`features/strategies/TemplatePicker.tsx`)

**Files:**
- Create: `apps/web/src/features/strategies/TemplatePicker.tsx`
- Test: `apps/web/src/features/strategies/TemplatePicker.test.tsx`

- [ ] **Step 1: Write failing test**

Create `apps/web/src/features/strategies/TemplatePicker.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TemplatePicker } from './TemplatePicker'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('TemplatePicker', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('lists templates and applies one', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).endsWith('/templates')) {
        return new Response(JSON.stringify({ templates: [
          { key: 'bull_call_spread', name: 'Bull Call Spread', category: 'bullish', description: 'x' }] }), { status: 200 })
      }
      if (String(url).includes('/templates/bull_call_spread/build')) {
        return new Response(JSON.stringify({ underlying: 'AAPL', legs: [
          { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1 },
          { kind: 'option', option_type: 'CALL', side: 'SELL', strike: 110, expiry: '2026-12-18', qty: 1 }] }), { status: 200 })
      }
      return new Response('{}', { status: 200 })
    }))
    const onApply = vi.fn()
    render(wrap(<TemplatePicker underlying="AAPL" expiry="2026-12-18" atmStrike={100} onApply={onApply} />))
    const chip = await screen.findByText('Bull Call Spread')
    fireEvent.click(chip)
    await waitFor(() => expect(onApply).toHaveBeenCalled())
    expect(onApply.mock.calls.at(-1)![0].legs).toHaveLength(2)
  })
})
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/features/strategies/TemplatePicker.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement TemplatePicker.tsx**

Create `apps/web/src/features/strategies/TemplatePicker.tsx`:

```tsx
import { useTemplates, useBuildTemplate } from './hooks'
import type { StrategyConfig } from '../../lib/strategies'

const CATS: Array<'bullish' | 'bearish' | 'neutral'> = ['bullish', 'bearish', 'neutral']

export function TemplatePicker({
  underlying, expiry, atmStrike, onApply,
}: {
  underlying: string; expiry: string; atmStrike: number; onApply: (c: StrategyConfig) => void
}) {
  const { data: templates = [], isLoading } = useTemplates()
  const build = useBuildTemplate()

  function apply(key: string) {
    build.mutate(
      { key, params: { underlying, expiry, atm_strike: atmStrike } },
      { onSuccess: (cfg) => onApply(cfg) },
    )
  }

  if (isLoading) return <div className="text-xs text-txtFaint">Loading templates…</div>
  return (
    <div className="space-y-3">
      {CATS.map((cat) => (
        <div key={cat}>
          <div className="mb-1 font-mono text-[9px] uppercase tracking-wider text-txtFaint">{cat}</div>
          <div className="flex flex-wrap gap-2">
            {templates.filter((t) => t.category === cat).map((t) => (
              <button key={t.key} title={t.description} onClick={() => apply(t.key)}
                      className="rounded-full border border-line bg-panel px-3 py-1 text-xs text-txtDim hover:text-txt">
                {t.name}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/features/strategies/TemplatePicker.test.tsx`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/strategies/TemplatePicker.tsx apps/web/src/features/strategies/TemplatePicker.test.tsx
git commit -m "feat(web): ready-made template picker"
```

---

## Task 8: Saved list (`features/strategies/SavedList.tsx`)

**Files:**
- Create: `apps/web/src/features/strategies/SavedList.tsx`
- Test: `apps/web/src/features/strategies/SavedList.test.tsx`

- [ ] **Step 1: Write failing test**

Create `apps/web/src/features/strategies/SavedList.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SavedList } from './SavedList'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const strat = {
  strategy_id: 's1', name: 'My Spread', description: null, state: 'draft', market: 'US',
  config: { underlying: 'AAPL', legs: [] }, created_at: '2026-05-30T00:00:00Z', updated_at: '2026-05-30T00:00:00Z',
}

describe('SavedList', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('lists strategies and loads one', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ strategies: [strat], next_cursor: null }), { status: 200 })))
    const onLoad = vi.fn()
    render(wrap(<SavedList onLoad={onLoad} />))
    const item = await screen.findByText('My Spread')
    fireEvent.click(item)
    await waitFor(() => expect(onLoad).toHaveBeenCalledWith(expect.objectContaining({ strategy_id: 's1' })))
  })
}) 
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/features/strategies/SavedList.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement SavedList.tsx**

Create `apps/web/src/features/strategies/SavedList.tsx`:

```tsx
import { useStrategies, useArchive } from './hooks'
import type { Strategy } from '../../lib/strategies'

export function SavedList({ onLoad }: { onLoad: (s: Strategy) => void }) {
  const { data, isLoading } = useStrategies()
  const archive = useArchive()
  if (isLoading) return <div className="text-xs text-txtFaint">Loading…</div>
  const items = data?.strategies ?? []
  if (items.length === 0) return <div className="text-xs text-txtFaint">No saved strategies yet.</div>
  return (
    <ul className="space-y-1">
      {items.map((s) => (
        <li key={s.strategy_id} className="flex items-center justify-between rounded border border-line bg-panel/50 px-3 py-2">
          <button className="text-left text-sm text-txt hover:underline" onClick={() => onLoad(s)}>{s.name}</button>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-line px-2 py-0.5 font-mono text-[9px] uppercase text-txtFaint">{s.state}</span>
            <button className="text-xs text-red-400" data-testid={`archive-${s.strategy_id}`}
                    onClick={() => archive.mutate(s.strategy_id)}>archive</button>
          </div>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/features/strategies/SavedList.test.tsx`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/strategies/SavedList.tsx apps/web/src/features/strategies/SavedList.test.tsx
git commit -m "feat(web): saved strategies list (load + archive)"
```

---

## Task 9: Strategies page + routing (`pages/Strategies.tsx`)

**Files:**
- Create: `apps/web/src/pages/Strategies.tsx`
- Create: `apps/web/src/pages/Strategies.test.tsx`
- Modify: `apps/web/src/main.tsx`

- [ ] **Step 1: Write failing test (analyze flow + 402 nudge)**

Create `apps/web/src/pages/Strategies.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Strategies } from './Strategies'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const pureResult = {
  expiration_curve: [{ spot: 80, pnl: -400 }, { spot: 130, pnl: 600 }], breakevens: [104],
  max_profit: 600, max_loss: -400, unbounded_profit: false, unbounded_loss: false,
  net_premium: 400, risk_reward: 1.5,
}

describe('Strategies page', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('analyzes and renders the chart + stats', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) return new Response(JSON.stringify({ templates: [] }), { status: 200 })
      if (String(url).endsWith('/v1/strategies')) return new Response(JSON.stringify({ strategies: [], next_cursor: null }), { status: 200 })
      return new Response(JSON.stringify(pureResult), { status: 200 })
    }))
    render(wrap(<Strategies />))
    fireEvent.click(screen.getByTestId('analyze-btn'))
    await waitFor(() => expect(screen.getByTestId('payoff-chart')).toBeInTheDocument())
    expect(screen.getByTestId('stat-max-profit')).toHaveTextContent('600')
  })

  it('shows an upgrade nudge on 402 for a live analyze', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) return new Response(JSON.stringify({ templates: [] }), { status: 200 })
      if (String(url).endsWith('/v1/strategies')) return new Response(JSON.stringify({ strategies: [], next_cursor: null }), { status: 200 })
      return new Response(JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO' } } }), { status: 402 })
    }))
    render(wrap(<Strategies />))
    fireEvent.click(screen.getByTestId('live-toggle'))
    fireEvent.click(screen.getByTestId('analyze-btn'))
    await waitFor(() => expect(screen.getByTestId('upgrade-banner')).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/pages/Strategies.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement Strategies.tsx**

Create `apps/web/src/pages/Strategies.tsx`:

```tsx
import { useState } from 'react'
import { LegEditor } from '../features/strategies/LegEditor'
import { TemplatePicker } from '../features/strategies/TemplatePicker'
import { SavedList } from '../features/strategies/SavedList'
import { PayoffChart } from '../features/strategies/PayoffChart'
import { StatsPanel } from '../features/strategies/StatsPanel'
import { useAnalyze, useCreateStrategy } from '../features/strategies/hooks'
import { EntitlementError, type AnalyzeResult, type StrategyConfig } from '../lib/strategies'

type Tab = 'ready' | 'build' | 'saved'

const INITIAL: StrategyConfig = {
  underlying: 'AAPL',
  legs: [
    { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1, entry_price: 6 },
    { kind: 'option', option_type: 'CALL', side: 'SELL', strike: 110, expiry: '2026-12-18', qty: 1, entry_price: 2 },
  ],
}

function atmStrike(c: StrategyConfig): number {
  const s = c.legs.flatMap((l) => (l.kind === 'option' ? [l.strike] : []))
  return s.length ? s.reduce((a, b) => a + b, 0) / s.length : 100
}
function firstExpiry(c: StrategyConfig): string {
  const o = c.legs.find((l) => l.kind === 'option')
  return o && o.kind === 'option' ? o.expiry : '2026-12-18'
}

export function Strategies() {
  const [tab, setTab] = useState<Tab>('build')
  const [config, setConfig] = useState<StrategyConfig>(INITIAL)
  const [live, setLive] = useState(false)
  const [targetDate, setTargetDate] = useState('')
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [needUpgrade, setNeedUpgrade] = useState(false)
  const analyze = useAnalyze()
  const create = useCreateStrategy()

  function runAnalyze() {
    setNeedUpgrade(false)
    analyze.mutate(
      { config, live, target_date: targetDate || undefined },
      {
        onSuccess: (r) => setResult(r),
        onError: (e) => { if (e instanceof EntitlementError) setNeedUpgrade(true) },
      },
    )
  }

  return (
    <div className="animate-fadeUp space-y-4">
      <div className="flex items-baseline gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Strategy Builder</h2>
        <span className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">payoff · greeks · POP</span>
      </div>

      {needUpgrade && (
        <div className="rounded-md border border-yellow-700/40 bg-yellow-900/10 px-3 py-2 text-xs text-yellow-300" data-testid="upgrade-banner">
          Live Greeks, probability of profit, and the target-date curve require a Pro plan. Showing the expiry payoff from entered prices.
        </div>
      )}

      {result && (
        <>
          <PayoffChart expirationCurve={result.expiration_curve} targetDateCurve={result.target_date_curve}
                       breakevens={result.breakevens} spot={result.spot} />
          <StatsPanel result={result} />
        </>
      )}

      <div className="rounded-lg border border-line bg-panel/30 p-3">
        <div className="mb-3 flex gap-2">
          {(['ready', 'build', 'saved'] as Tab[]).map((t) => (
            <button key={t} data-testid={`tab-${t}`} onClick={() => setTab(t)}
                    className={`rounded px-3 py-1 text-xs ${tab === t ? 'bg-pos/20 text-pos' : 'text-txtDim hover:text-txt'}`}>
              {t === 'ready' ? 'Ready-made' : t === 'build' ? 'Build your own' : 'Saved'}
            </button>
          ))}
        </div>

        {tab === 'ready' && (
          <TemplatePicker underlying={config.underlying} expiry={firstExpiry(config)} atmStrike={atmStrike(config)}
                          onApply={(c) => { setConfig(c); setTab('build') }} />
        )}
        {tab === 'build' && <LegEditor config={config} onChange={setConfig} />}
        {tab === 'saved' && <SavedList onLoad={(s) => { setConfig(s.config); setTab('build') }} />}

        <div className="mt-3 flex items-center gap-3">
          <label className="flex items-center gap-1 text-[11px] text-txtDim">
            <input type="checkbox" data-testid="live-toggle" checked={live} onChange={(e) => setLive(e.target.checked)} /> live
          </label>
          <input type="date" className="rounded border border-line bg-canvas px-2 py-1 text-xs text-txt"
                 data-testid="target-date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} disabled={!live} />
          <button data-testid="analyze-btn" onClick={runAnalyze} disabled={analyze.isPending}
                  className="rounded bg-pos/20 px-4 py-1 text-xs text-pos hover:bg-pos/30">
            {analyze.isPending ? 'Analyzing…' : 'Analyze'}
          </button>
          <button data-testid="save-btn"
                  onClick={() => create.mutate({ name: `${config.underlying} strategy`, config })}
                  className="rounded border border-line px-4 py-1 text-xs text-txtDim hover:text-txt">Save</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/pages/Strategies.test.tsx`
Expected: 2 passed.

- [ ] **Step 5: Wire the route**

In `apps/web/src/main.tsx`:
1. Add the import: `import { Strategies } from './pages/Strategies'`
2. Replace `<Route path="strategies" element={<PlaceholderPage title="Strategies" />} />` with `<Route path="strategies" element={<Strategies />} />`.

- [ ] **Step 6: Verify build + typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/pages/Strategies.tsx apps/web/src/pages/Strategies.test.tsx apps/web/src/main.tsx
git commit -m "feat(web): strategy builder page (tabs, analyze, live gating) + route"
```

---

## Task 10: Full gate

- [ ] **Step 1: Run the whole web suite + typecheck + lint**

Run: `cd apps/web && pnpm test:run`
Expected: all suites pass.
Run: `cd apps/web && pnpm typecheck`
Expected: no errors.
Run: `cd apps/web && pnpm lint`
Expected: clean (fix any unused imports / hook-deps warnings).

- [ ] **Step 2: Final commit (if lint fixups were needed)**

```bash
git add -A apps/web
git commit -m "chore(web): lint + full web suite green for strategy builder"
```

---

## Self-review checklist (completed)

- **Spec coverage:** data layer + EntitlementError (T1), scale math (T2), RQ hooks (T3), PayoffChart with expiry+target-date+zones+markers+hover (T4), StatsPanel unbounded/live-gating (T5), LegEditor (T6), TemplatePicker (T7), SavedList (T8), page orchestration + tabs + tier flow + routing (T9), gate (T10). All spec sections covered. (PATCH/in-place edit is out of scope per spec; create/load/archive only.)
- **Placeholder scan:** none — every step has complete code.
- **Type consistency:** `AnalyzeResult`, `StrategyConfig`, `Leg`/`OptionLeg`, `CurvePoint`, `Bounds`/`Dims`, `EntitlementError`, hook names (`useAnalyze`/`useTemplates`/`useBuildTemplate`/`useStrategies`/`useCreateStrategy`/`useArchive`), and component props line up across tasks. The page consumes `result.expiration_curve`/`target_date_curve`/`spot`/`breakevens` exactly as the client types them.

## Known risks / notes for the implementer

- **`pnpm` vs `npm`:** commands assume `pnpm` (the repo uses pnpm for web). If only npm is available, substitute `npm run test:run -- <path>` etc.
- **React import for JSX in tests:** the project's vite/tsconfig uses the automatic JSX runtime (no `import React` needed); test files using `React.ReactNode` import the type implicitly via `wrap(ui: React.ReactNode)` — if tsc complains, add `import type React from 'react'`.
- **Debounced auto-analyze** (spec mentions it) is intentionally simplified to an explicit "Analyze" button here to keep tests deterministic; a debounce-on-edit can be layered on later without changing the data flow.
- **Free-tier pure analyze** needs `entry_price` on each option leg (the INITIAL config provides them). The LegEditor exposes the price field for this.
```
