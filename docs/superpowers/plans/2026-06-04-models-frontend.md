# Models frontend (AN-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/app/models` placeholder with the ML surface — a ticker-driven Insights view (GARCH vol-forecast + news sentiment) and a Monte-Carlo POP tab (ready-made template → strategy config → P&L histogram), all `ml_forecast`-gated.

**Architecture:** A thin `lib/models.ts` client (reusing `EntitlementError` + `StrategyConfig` from `lib/strategies.ts` and the `request()` pattern from `lib/market.ts`), TanStack Query hooks, four pure presentational components (custom-SVG charts, AN-1 convention), and a `Models` page that owns all hooks/state and reuses the existing `<TemplatePicker>` for the MC config. One route swap.

**Tech Stack:** Vike + React 18 + TS strict + Tailwind (theme tokens only) + TanStack Query + react-router 6 + Vitest + @testing-library/react.

**Conventions (apply to every task):**
- Run web tests from `apps/web`: `npx vitest run <files>`. Gate: `npm run typecheck` + `npm run lint`.
- Commit footer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Theme tokens only for Tailwind **class** colors; SVG `fill`/`stroke` **hex literals are allowed** (PayoffChart/IvCurves convention). No raw Tailwind color classes.
- Double-quote JSX strings containing apostrophes.
- NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`. Stage ONLY each task's files.
- Strict-TS lesson: `mock.calls[0][i]` index access can fail `tsc --noEmit` even when it passes at runtime — cast through `unknown` (`as unknown as [string, RequestInit]`).

---

### Task 1: `lib/models.ts` client + test

**Files:**
- Create: `apps/web/src/lib/models.ts`
- Test: `apps/web/src/lib/models.test.ts`

- [ ] **Step 1: Write the failing test** — `apps/web/src/lib/models.test.ts`

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest'
import { getVolForecast, getSentiment, runMonteCarlo, EntitlementError } from './models'

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body })
}

afterEach(() => vi.unstubAllGlobals())

describe('models client', () => {
  it('getVolForecast hits the vol-forecast endpoint with horizon', async () => {
    const f = mockFetch(200, { primary_model: 'garch' })
    vi.stubGlobal('fetch', f)
    await getVolForecast('SPY', 20)
    expect(f.mock.calls[0][0] as string).toContain('/v1/market/vol-forecast?ticker=SPY&market=US&horizon=20')
  })

  it('getSentiment hits the sentiment endpoint', async () => {
    const f = mockFetch(200, { has_data: false })
    vi.stubGlobal('fetch', f)
    await getSentiment('AAPL')
    expect(f.mock.calls[0][0] as string).toContain('/v1/market/sentiment?ticker=AAPL&market=US')
  })

  it('runMonteCarlo POSTs the body', async () => {
    const f = mockFetch(200, { pop: 0.5 })
    vi.stubGlobal('fetch', f)
    await runMonteCarlo({ config: { underlying: 'SPY', legs: [] }, paths: 5000, use_sentiment: true })
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/v1/strategies/montecarlo')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toMatchObject({ paths: 5000, use_sentiment: true })
  })

  it('throws EntitlementError on 402', async () => {
    vi.stubGlobal('fetch', mockFetch(402, { detail: { error: { code: 'ENTITLEMENT_REQUIRED' } } }))
    await expect(getVolForecast('SPY', 10)).rejects.toBeInstanceOf(EntitlementError)
  })

  it('throws Error(code) on 422', async () => {
    vi.stubGlobal('fetch', mockFetch(422, { detail: { error: { code: 'INSUFFICIENT_HISTORY' } } }))
    await expect(getVolForecast('SPY', 10)).rejects.toThrow('INSUFFICIENT_HISTORY')
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/web && npx vitest run src/lib/models.test.ts`
Expected: FAIL (cannot resolve `./models`).

- [ ] **Step 3: Create** `apps/web/src/lib/models.ts`

```typescript
import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError, type StrategyConfig } from './strategies'

export { EntitlementError }

export interface VolForecastAlt {
  model: string
  forecast: number[]
  status: 'baseline' | 'underperforming_baseline'
  delta_mae_vs_baseline: number
}

export interface VolForecast {
  horizon_days: number
  primary_model: 'garch' | 'hv21'
  primary_forecast: number[]
  primary_ci_95: [number, number][] | null
  alternative_models: VolForecastAlt[]
  validation: { holdout_days: number; garch_mae: number; hv21_mae: number; lift: number }
  model: string
  iv_source: string
  approximate: boolean
  params: { omega: number; alpha: number; beta: number }
}

export interface Sentiment {
  ticker: string
  market: string
  score: number
  label: 'bearish' | 'neutral' | 'bullish'
  confident: boolean
  n_headlines: number
  has_data: boolean
  computed_at: string | null
  as_of: string | null
}

export interface MonteCarloRequest {
  config: StrategyConfig
  market?: string
  sigma?: number
  paths?: number
  seed?: number
  use_sentiment?: boolean
}

export interface MonteCarloResult {
  pop: number
  ev: number
  paths: number
  histogram: { counts: number[]; bin_edges: number[] }
  percentiles: { p5: number; p50: number; p95: number }
  max_profit_observed: number
  max_loss_observed: number
  model: string
  approximate: boolean
  seed: number
  underlying: string
  market: string
  spot: number
  sigma: number
  sigma_source: 'override' | 'garch'
  horizon_days: number
  rate: number
  sentiment: { applied: boolean; reason?: string; score?: number; label?: string; computed_at?: string }
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

export function getVolForecast(ticker: string, horizon: number): Promise<VolForecast> {
  return request(`/v1/market/vol-forecast?ticker=${encodeURIComponent(ticker)}&market=US&horizon=${horizon}`)
}

export function getSentiment(ticker: string): Promise<Sentiment> {
  return request(`/v1/market/sentiment?ticker=${encodeURIComponent(ticker)}&market=US`)
}

export function runMonteCarlo(body: MonteCarloRequest): Promise<MonteCarloResult> {
  return request('/v1/strategies/montecarlo', { method: 'POST', body: JSON.stringify(body) })
}
```

- [ ] **Step 4: Run to verify it passes** — `cd apps/web && npx vitest run src/lib/models.test.ts` → 5 passed. If `f.mock.calls[0][0] as string` fails `npm run typecheck`, change those two to `(f.mock.calls[0] as unknown as [string])[0]`.

- [ ] **Step 5: Typecheck + lint** — `npm run typecheck` and `npm run lint` → clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/models.ts apps/web/src/lib/models.test.ts
git commit -m "feat(web): models ML client (vol-forecast, sentiment, monte-carlo)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `features/models/hooks.ts`

**Files:**
- Create: `apps/web/src/features/models/hooks.ts`

(No standalone test — these hooks are exercised by `Models.test.tsx` in Task 7. They are thin wrappers; testing them in isolation would duplicate the page test.)

- [ ] **Step 1: Create** `apps/web/src/features/models/hooks.ts`

```typescript
import { useMutation, useQuery } from '@tanstack/react-query'
import { getVolForecast, getSentiment, runMonteCarlo, type MonteCarloRequest } from '../../lib/models'

export function useVolForecast(ticker: string, horizon: number, enabled: boolean) {
  return useQuery({
    queryKey: ['vol-forecast', ticker, horizon],
    queryFn: () => getVolForecast(ticker, horizon),
    enabled: enabled && !!ticker,
    retry: false,
  })
}

export function useSentiment(ticker: string, enabled: boolean) {
  return useQuery({
    queryKey: ['sentiment', ticker],
    queryFn: () => getSentiment(ticker),
    enabled: enabled && !!ticker,
    retry: false,
  })
}

export function useMonteCarlo() {
  return useMutation({
    mutationFn: (body: MonteCarloRequest) => runMonteCarlo(body),
  })
}
```

- [ ] **Step 2: Typecheck + lint** — `npm run typecheck` and `npm run lint` → clean (no test run; nothing imports it yet — typecheck confirms it compiles).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/features/models/hooks.ts
git commit -m "feat(web): models TanStack Query hooks

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `ForecastPanel.tsx` (pure)

**Files:**
- Create: `apps/web/src/features/models/ForecastPanel.tsx`
- Test: `apps/web/src/features/models/ForecastPanel.test.tsx`

- [ ] **Step 1: Write the failing test** — `apps/web/src/features/models/ForecastPanel.test.tsx`

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ForecastPanel } from './ForecastPanel'
import type { VolForecast } from '../../lib/models'

const base: VolForecast = {
  horizon_days: 3,
  primary_model: 'garch',
  primary_forecast: [20, 21, 22],
  primary_ci_95: [[18, 22], [19, 23], [20, 24]],
  alternative_models: [{ model: 'hv21', forecast: [19, 19, 19], status: 'baseline', delta_mae_vs_baseline: -0.1 }],
  validation: { holdout_days: 40, garch_mae: 0.5, hv21_mae: 0.6, lift: 0.1 },
  model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true,
  params: { omega: 0.0001, alpha: 0.08, beta: 0.9 },
}

describe('ForecastPanel', () => {
  it('draws a primary line with one point per horizon day and a CI band', () => {
    render(<ForecastPanel forecast={base} />)
    expect(screen.getByTestId('forecast-line').getAttribute('points')!.trim().split(' ')).toHaveLength(3)
    expect(screen.getByTestId('forecast-ci')).toBeInTheDocument()
    expect(screen.getByTestId('forecast-primary').textContent).toContain('garch')
  })

  it('omits the CI band when primary_ci_95 is null (hv21 primary)', () => {
    render(<ForecastPanel forecast={{ ...base, primary_model: 'hv21', primary_ci_95: null }} />)
    expect(screen.queryByTestId('forecast-ci')).toBeNull()
    expect(screen.getByTestId('forecast-line')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails** — `cd apps/web && npx vitest run src/features/models/ForecastPanel.test.tsx` → FAIL.

- [ ] **Step 3: Create** `apps/web/src/features/models/ForecastPanel.tsx`

```typescript
import type { VolForecast } from '../../lib/models'

const W = 360
const H = 180
const PAD = 30

function scaler(min: number, max: number, lo: number, hi: number) {
  const span = max - min || 1
  return (v: number) => lo + (hi - lo) * ((v - min) / span)
}

export function ForecastPanel({ forecast }: { forecast: VolForecast }) {
  const fc = forecast.primary_forecast
  const ci = forecast.primary_ci_95
  const n = fc.length
  const xs = scaler(0, Math.max(1, n - 1), PAD, W - PAD)
  const allYs = [...fc, ...(ci ? ci.flat() : [])]
  const ys = scaler(Math.min(...allYs), Math.max(...allYs), H - PAD, PAD)

  const linePts = fc.map((v, i) => `${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(' ')
  const band = ci
    ? [
        ...ci.map((p, i) => `${xs(i).toFixed(1)},${ys(p[1]).toFixed(1)}`),
        ...ci.map((p, i) => `${xs(i).toFixed(1)},${ys(p[0]).toFixed(1)}`).reverse(),
      ].join(' ')
    : null

  const alt = forecast.alternative_models[0]

  return (
    <figure className="rounded-lg border border-line bg-panel p-4" data-testid="forecast-panel">
      <figcaption className="mb-2 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
        Vol forecast · {forecast.horizon_days}d
        <span data-testid="forecast-primary" className="rounded bg-accent/20 px-1.5 py-0.5 text-accent">{forecast.primary_model}</span>
        <span className="rounded border border-line px-1.5 py-0.5 text-txtFaint">approximate</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {band && <polygon data-testid="forecast-ci" points={band} fill="#4da3ff22" stroke="none" />}
        <polyline data-testid="forecast-line" points={linePts} fill="none" stroke="#4da3ff" strokeWidth={1.8} />
      </svg>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px] text-txtDim">
        <div className="flex justify-between"><dt>lift</dt><dd className="tnum text-txt">{forecast.validation.lift.toFixed(3)}</dd></div>
        <div className="flex justify-between"><dt>garch MAE</dt><dd className="tnum">{forecast.validation.garch_mae.toFixed(3)}</dd></div>
        <div className="flex justify-between"><dt>hv21 MAE</dt><dd className="tnum">{forecast.validation.hv21_mae.toFixed(3)}</dd></div>
        <div className="flex justify-between"><dt>ω/α/β</dt><dd className="tnum">{forecast.params.omega.toFixed(4)}/{forecast.params.alpha.toFixed(2)}/{forecast.params.beta.toFixed(2)}</dd></div>
      </dl>
      {alt && (
        <p className="mt-2 text-[11px] text-txtFaint" data-testid="forecast-alt">
          alt: {alt.model} ({alt.status.replace(/_/g, " ")})
        </p>
      )}
    </figure>
  )
}
```

- [ ] **Step 4: Run to verify it passes** — `cd apps/web && npx vitest run src/features/models/ForecastPanel.test.tsx` → 2 passed.

- [ ] **Step 5: Typecheck + lint** → clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/features/models/ForecastPanel.tsx apps/web/src/features/models/ForecastPanel.test.tsx
git commit -m "feat(web): models ForecastPanel (vol curve + CI band + honesty row)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `SentimentGauge.tsx` (pure)

**Files:**
- Create: `apps/web/src/features/models/SentimentGauge.tsx`
- Test: `apps/web/src/features/models/SentimentGauge.test.tsx`

- [ ] **Step 1: Write the failing test** — `apps/web/src/features/models/SentimentGauge.test.tsx`

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SentimentGauge } from './SentimentGauge'
import type { Sentiment } from '../../lib/models'

const S = (over: Partial<Sentiment> = {}): Sentiment => ({
  ticker: 'AAPL', market: 'US', score: 0, label: 'neutral', confident: true,
  n_headlines: 12, has_data: true, computed_at: '2026-06-04T10:00:00Z', as_of: '2026-06-04T00:00:00Z', ...over,
})

describe('SentimentGauge', () => {
  it('places the marker past midpoint and labels bullish for a positive score', () => {
    render(<SentimentGauge sentiment={S({ score: 0.6, label: 'bullish' })} />)
    expect(Number(screen.getByTestId('sentiment-marker').getAttribute('cx'))).toBeGreaterThan(120)
    expect(screen.getByTestId('sentiment-label').textContent).toContain('bullish')
  })

  it('places the marker before midpoint for a bearish score', () => {
    render(<SentimentGauge sentiment={S({ score: -0.6, label: 'bearish' })} />)
    expect(Number(screen.getByTestId('sentiment-marker').getAttribute('cx'))).toBeLessThan(120)
  })

  it('shows an empty state when has_data is false', () => {
    render(<SentimentGauge sentiment={S({ has_data: false })} />)
    expect(screen.getByTestId('sentiment-empty')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails** — `cd apps/web && npx vitest run src/features/models/SentimentGauge.test.tsx` → FAIL.

- [ ] **Step 3: Create** `apps/web/src/features/models/SentimentGauge.tsx`

```typescript
import type { Sentiment } from '../../lib/models'

const W = 240
const H = 28

const LABEL_CLS: Record<string, string> = { bearish: 'text-neg', neutral: 'text-warn', bullish: 'text-pos' }

export function SentimentGauge({ sentiment }: { sentiment: Sentiment }) {
  if (!sentiment.has_data) {
    return (
      <div className="rounded-lg border border-line bg-panel p-4" data-testid="sentiment-empty">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">News sentiment</p>
        <p className="mt-3 text-sm text-txtFaint">No sentiment coverage yet for {sentiment.ticker}.</p>
      </div>
    )
  }
  const cx = ((sentiment.score + 1) / 2) * W
  return (
    <div className="rounded-lg border border-line bg-panel p-4" data-testid="sentiment-panel">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">News sentiment</p>
      <div className="mt-3 flex items-baseline gap-2">
        <span data-testid="sentiment-label" className={`text-lg font-semibold ${LABEL_CLS[sentiment.label] ?? 'text-txt'}`}>
          {sentiment.label}
        </span>
        <span className="tnum font-mono text-sm text-txtDim">{sentiment.score.toFixed(2)}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full" data-testid="sentiment-gauge">
        <line x1={0} y1={H / 2} x2={W} y2={H / 2} stroke="#2a2f3a" strokeWidth={3} strokeLinecap="round" />
        <line x1={W / 2} y1={4} x2={W / 2} y2={H - 4} stroke="#3a4150" strokeWidth={1} />
        <circle data-testid="sentiment-marker" cx={cx} cy={H / 2} r={5} fill="#e6e9ef" />
      </svg>
      <p className="mt-3 font-mono text-[11px] text-txtFaint">
        {sentiment.confident ? "confident" : "low confidence"} · {sentiment.n_headlines} headlines
        {sentiment.as_of ? ` · ${new Date(sentiment.as_of).toLocaleDateString()}` : ""}
      </p>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify it passes** — `cd apps/web && npx vitest run src/features/models/SentimentGauge.test.tsx` → 3 passed. (W=240, mid=120; score 0.6 → cx=192; score −0.6 → cx=48.)

- [ ] **Step 5: Typecheck + lint** → clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/features/models/SentimentGauge.tsx apps/web/src/features/models/SentimentGauge.test.tsx
git commit -m "feat(web): models SentimentGauge (-1..1 meter + empty state)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `MonteCarloPanel.tsx` (pure)

**Files:**
- Create: `apps/web/src/features/models/MonteCarloPanel.tsx`
- Test: `apps/web/src/features/models/MonteCarloPanel.test.tsx`

- [ ] **Step 1: Write the failing test** — `apps/web/src/features/models/MonteCarloPanel.test.tsx`

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MonteCarloPanel } from './MonteCarloPanel'
import type { MonteCarloResult } from '../../lib/models'

const R = (over: Partial<MonteCarloResult> = {}): MonteCarloResult => ({
  pop: 0.62, ev: 35.5, paths: 10000,
  histogram: { counts: [2, 5, 9, 4], bin_edges: [-100, -50, 0, 50, 100] },
  percentiles: { p5: -80, p50: 10, p95: 90 },
  max_profit_observed: 120, max_loss_observed: -110,
  model: 'gbm_mc', approximate: true, seed: 0,
  underlying: 'SPY', market: 'US', spot: 500, sigma: 0.2, sigma_source: 'garch',
  horizon_days: 14, rate: 0.04,
  sentiment: { applied: false, reason: 'not_requested' }, ...over,
})

describe('MonteCarloPanel', () => {
  it('renders POP, EV, percentiles and one bar per histogram bin', () => {
    render(<MonteCarloPanel result={R()} />)
    expect(screen.getByTestId('mc-pop').textContent).toContain('62.0%')
    expect(screen.getByTestId('mc-ev').textContent).toContain('35.5')
    expect(screen.getAllByTestId('mc-bar')).toHaveLength(4)
    expect(screen.getByTestId('mc-sigma-source').textContent).toContain('garch')
  })

  it('notes when sentiment was applied', () => {
    render(<MonteCarloPanel result={R({ sentiment: { applied: true, score: 0.4, label: 'bullish' } })} />)
    expect(screen.getByTestId('mc-sentiment').textContent).toContain('sentiment applied')
    expect(screen.getByTestId('mc-sentiment').textContent).toContain('bullish')
  })
})
```

- [ ] **Step 2: Run to verify it fails** — `cd apps/web && npx vitest run src/features/models/MonteCarloPanel.test.tsx` → FAIL.

- [ ] **Step 3: Create** `apps/web/src/features/models/MonteCarloPanel.tsx`

```typescript
import type { MonteCarloResult } from '../../lib/models'

const W = 360
const H = 160
const PAD = 8
const BASELINE = 20

export function MonteCarloPanel({ result }: { result: MonteCarloResult }) {
  const { counts, bin_edges } = result.histogram
  const maxC = Math.max(1, ...counts)
  const x0 = bin_edges[0]
  const x1 = bin_edges[bin_edges.length - 1]
  const span = x1 - x0 || 1
  const sx = (v: number) => PAD + (W - 2 * PAD) * ((v - x0) / span)
  const zeroX = sx(0)

  return (
    <div className="space-y-4 rounded-lg border border-line bg-panel p-4" data-testid="mc-panel">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <div>
          <span className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">POP</span>{" "}
          <span data-testid="mc-pop" className="tnum text-lg font-semibold text-txt">{(result.pop * 100).toFixed(1)}%</span>
        </div>
        <div>
          <span className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">EV</span>{" "}
          <span data-testid="mc-ev" className={`tnum text-lg font-semibold ${result.ev >= 0 ? "text-pos" : "text-neg"}`}>{result.ev.toFixed(2)}</span>
        </div>
        <span data-testid="mc-sigma-source" className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-txtDim">σ {result.sigma_source}</span>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="mc-histogram">
        {counts.map((c, i) => {
          const bx0 = sx(bin_edges[i])
          const bx1 = sx(bin_edges[i + 1])
          const h = (H - BASELINE) * (c / maxC)
          const mid = (bin_edges[i] + bin_edges[i + 1]) / 2
          return (
            <rect key={i} data-testid="mc-bar" x={bx0} y={H - BASELINE - h}
              width={Math.max(0.5, bx1 - bx0 - 0.5)} height={h} fill={mid >= 0 ? "#37c98b" : "#ff5d73"} />
          )
        })}
        <line x1={zeroX} y1={0} x2={zeroX} y2={H - BASELINE} stroke="#5b6472" strokeWidth={1} strokeDasharray="3 3" />
      </svg>

      <dl className="grid grid-cols-3 gap-2 font-mono text-[11px] text-txtDim">
        <div className="flex justify-between"><dt>p5</dt><dd className="tnum">{result.percentiles.p5.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>p50</dt><dd className="tnum">{result.percentiles.p50.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>p95</dt><dd className="tnum">{result.percentiles.p95.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>max +</dt><dd className="tnum text-pos">{result.max_profit_observed.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>max −</dt><dd className="tnum text-neg">{result.max_loss_observed.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>spot</dt><dd className="tnum">{result.spot.toFixed(2)}</dd></div>
      </dl>

      <p className="text-[11px] text-txtFaint" data-testid="mc-sentiment">
        {result.sentiment.applied
          ? `sentiment applied · ${result.sentiment.label} (${result.sentiment.score?.toFixed(2)})`
          : `sentiment: ${result.sentiment.reason ?? "not applied"}`}
        {" · "}{result.horizon_days}d · rate {(result.rate * 100).toFixed(2)}%
      </p>
    </div>
  )
}
```

- [ ] **Step 4: Run to verify it passes** — `cd apps/web && npx vitest run src/features/models/MonteCarloPanel.test.tsx` → 2 passed.

- [ ] **Step 5: Typecheck + lint** → clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/features/models/MonteCarloPanel.tsx apps/web/src/features/models/MonteCarloPanel.test.tsx
git commit -m "feat(web): models MonteCarloPanel (P&L histogram + POP/EV stats)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `ModelsGate.tsx`

**Files:**
- Create: `apps/web/src/features/models/ModelsGate.tsx`

(No standalone test — covered by the `Models.test.tsx` gate case in Task 7. It is a static presentational component mirroring `MarketsGate`.)

- [ ] **Step 1: Create** `apps/web/src/features/models/ModelsGate.tsx`

```typescript
import { Link } from 'react-router-dom'

export function ModelsGate() {
  return (
    <div className="rounded-xl border border-accent/30 bg-accent/5 px-6 py-12 text-center" data-testid="models-gate">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Pro feature</p>
      <h3 className="mt-3 text-lg font-semibold tracking-tight text-txt">
        Forecasts &amp; Monte-Carlo are a Pro feature
      </h3>
      <p className="mt-2 text-sm text-txtDim">
        Upgrade to Pro for GARCH volatility forecasts with walk-forward validation, news
        sentiment, and Monte-Carlo probability-of-profit on any strategy.
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

- [ ] **Step 2: Typecheck + lint** → clean.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/features/models/ModelsGate.tsx
git commit -m "feat(web): models upgrade gate (ml_forecast nudge)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `Models.tsx` page + route swap + page test

**Files:**
- Create: `apps/web/src/pages/Models.tsx`
- Test: `apps/web/src/pages/Models.test.tsx`
- Modify: `apps/web/src/app/Router.tsx` (swap the `models` placeholder route)

- [ ] **Step 1: Write the failing test** — `apps/web/src/pages/Models.test.tsx`

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as models from '../lib/models'
import * as strategies from '../lib/strategies'
import { Models } from './Models'

let mockMe: { entitlements: Record<string, boolean | number> } | null
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ me: mockMe }) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const FORECAST: models.VolForecast = {
  horizon_days: 10, primary_model: 'garch',
  primary_forecast: Array(10).fill(20), primary_ci_95: Array(10).fill([18, 22]),
  alternative_models: [{ model: 'hv21', forecast: Array(10).fill(19), status: 'baseline', delta_mae_vs_baseline: -0.1 }],
  validation: { holdout_days: 40, garch_mae: 0.5, hv21_mae: 0.6, lift: 0.1 },
  model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true,
  params: { omega: 0.0001, alpha: 0.08, beta: 0.9 },
}
const SENTIMENT: models.Sentiment = {
  ticker: 'AAPL', market: 'US', score: 0.3, label: 'bullish', confident: true,
  n_headlines: 8, has_data: true, computed_at: '2026-06-04T10:00:00Z', as_of: '2026-06-04T00:00:00Z',
}
const MC: models.MonteCarloResult = {
  pop: 0.6, ev: 20, paths: 10000, histogram: { counts: [1, 2], bin_edges: [-10, 0, 10] },
  percentiles: { p5: -5, p50: 1, p95: 8 }, max_profit_observed: 10, max_loss_observed: -10,
  model: 'gbm_mc', approximate: true, seed: 0, underlying: 'SPY', market: 'US', spot: 500,
  sigma: 0.2, sigma_source: 'garch', horizon_days: 14, rate: 0.04, sentiment: { applied: false, reason: 'not_requested' },
}

describe('Models page', () => {
  beforeEach(() => { vi.restoreAllMocks(); mockMe = { entitlements: { ml_forecast: true } } })

  it('gates a free user and does not fetch', () => {
    mockMe = { entitlements: { ml_forecast: false } }
    const spy = vi.spyOn(models, 'getVolForecast')
    render(wrap(<Models />))
    expect(screen.getByTestId('models-gate')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  it('loads a ticker and renders forecast + sentiment', async () => {
    vi.spyOn(models, 'getVolForecast').mockResolvedValue(FORECAST)
    vi.spyOn(models, 'getSentiment').mockResolvedValue(SENTIMENT)
    render(wrap(<Models />))
    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByTestId('ticker-load'))
    await waitFor(() => expect(screen.getByTestId('forecast-panel')).toBeInTheDocument())
    expect(screen.getByTestId('sentiment-label').textContent).toContain('bullish')
  })

  it('runs a Monte-Carlo simulation from a template', async () => {
    const cfg: strategies.StrategyConfig = {
      underlying: 'SPY',
      legs: [{ kind: 'option', option_type: 'CALL', side: 'BUY', strike: 500, expiry: '2026-12-18', qty: 1 }],
    }
    vi.spyOn(strategies, 'listTemplates').mockResolvedValue([{ key: 'long-call', name: 'Long Call', category: 'bullish', description: 'x' }])
    vi.spyOn(strategies, 'buildTemplate').mockResolvedValue(cfg)
    const run = vi.spyOn(models, 'runMonteCarlo').mockResolvedValue(MC)
    render(wrap(<Models />))
    fireEvent.click(screen.getByTestId('tab-montecarlo'))
    fireEvent.change(screen.getByTestId('mc-underlying'), { target: { value: 'SPY' } })
    fireEvent.change(screen.getByTestId('mc-expiry'), { target: { value: '2026-12-18' } })
    fireEvent.change(screen.getByTestId('mc-strike'), { target: { value: '500' } })
    await waitFor(() => expect(screen.getByText('Long Call')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Long Call'))
    await waitFor(() => expect(screen.getByTestId('mc-config-summary')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('mc-run'))
    await waitFor(() => expect(run).toHaveBeenCalled())
    expect(screen.getByTestId('mc-panel')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails** — `cd apps/web && npx vitest run src/pages/Models.test.tsx` → FAIL.

- [ ] **Step 3: Create** `apps/web/src/pages/Models.tsx`

```typescript
import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useVolForecast, useSentiment, useMonteCarlo } from '../features/models/hooks'
import { ForecastPanel } from '../features/models/ForecastPanel'
import { SentimentGauge } from '../features/models/SentimentGauge'
import { MonteCarloPanel } from '../features/models/MonteCarloPanel'
import { ModelsGate } from '../features/models/ModelsGate'
import { TemplatePicker } from '../features/strategies/TemplatePicker'
import { EntitlementError } from '../lib/models'
import type { StrategyConfig } from '../lib/strategies'

const HORIZONS = [10, 20, 30]

function forecastError(err: unknown): string | null {
  if (!err) return null
  const code = (err as Error).message
  if (code === 'INSUFFICIENT_HISTORY') return 'Not enough price history (need 250+ trading days).'
  if (code === 'RESOURCE_NOT_FOUND') return 'Unknown ticker.'
  return 'Something went wrong — try again.'
}

function mcError(err: unknown): string | null {
  if (!err) return null
  const code = (err as Error).message
  if (code === 'VALIDATION_NO_EXPIRY') return 'Pick a template with an option expiry in the future.'
  if (code === 'INSUFFICIENT_HISTORY') return 'Not enough price history to estimate volatility (need 250+ trading days).'
  return 'Something went wrong — try again.'
}

export function Models() {
  const { me } = useAuth()
  const entitled = me?.entitlements?.ml_forecast === true

  const [tab, setTab] = useState<'insights' | 'montecarlo'>('insights')
  const [input, setInput] = useState('')
  const [ticker, setTicker] = useState('')
  const [horizon, setHorizon] = useState(10)

  const forecastQ = useVolForecast(entitled ? ticker : '', horizon, entitled)
  const sentimentQ = useSentiment(entitled ? ticker : '', entitled)

  const [underlying, setUnderlying] = useState('')
  const [expiry, setExpiry] = useState('')
  const [atmStrike, setAtmStrike] = useState('')
  const [config, setConfig] = useState<StrategyConfig | null>(null)
  const [paths, setPaths] = useState('10000')
  const [useSentiment, setUseSentiment] = useState(false)
  const mc = useMonteCarlo()

  if (!entitled) return <ModelsGate />
  if (
    forecastQ.error instanceof EntitlementError ||
    sentimentQ.error instanceof EntitlementError ||
    mc.error instanceof EntitlementError
  ) {
    return <ModelsGate />
  }

  function load() {
    const t = input.trim().toUpperCase()
    if (t) setTicker(t)
  }

  function runMc() {
    if (!config) return
    mc.mutate({ config, paths: parseInt(paths, 10) || 10000, use_sentiment: useSentiment })
  }

  const fcErr = forecastError(forecastQ.error)
  const mcErrMsg = mcError(mc.error)
  const strike = parseFloat(atmStrike)
  const canPickTemplate = !!underlying.trim() && !!expiry && isFinite(strike) && strike > 0

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Models</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Forecasts &amp; simulation</h2>
      </div>

      <div className="flex gap-2 border-b border-line">
        <button data-testid="tab-insights" onClick={() => setTab('insights')}
          className={`px-3 py-2 text-xs ${tab === 'insights' ? 'border-b-2 border-accent text-txt' : 'text-txtDim'}`}>Insights</button>
        <button data-testid="tab-montecarlo" onClick={() => setTab('montecarlo')}
          className={`px-3 py-2 text-xs ${tab === 'montecarlo' ? 'border-b-2 border-accent text-txt' : 'text-txtDim'}`}>Monte-Carlo</button>
      </div>

      {tab === 'insights' ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <input data-testid="ticker-input" value={input}
              onChange={(e) => setInput(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
              onKeyDown={(e) => { if (e.key === 'Enter') load() }}
              placeholder="e.g. AAPL" maxLength={8}
              className="w-32 rounded-lg border border-line bg-canvas px-3 py-2 font-mono text-sm uppercase tracking-wider text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none" />
            <select data-testid="horizon-select" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}
              className="rounded-lg border border-line bg-panel px-2 py-2 font-mono text-xs text-txt">
              {HORIZONS.map((h) => <option key={h} value={h}>{h}d</option>)}
            </select>
            <button data-testid="ticker-load" onClick={load}
              className="rounded-lg bg-accent/20 px-4 py-2 text-xs text-accent transition hover:bg-accent/30">Load</button>
          </div>

          {(forecastQ.isLoading || sentimentQ.isLoading) && ticker && (
            <div className="animate-pulse rounded-lg border border-line bg-panel2 py-16" data-testid="models-loading" />
          )}
          {fcErr && ticker && <p className="text-sm text-neg" data-testid="forecast-error">{fcErr}</p>}

          {(forecastQ.data || sentimentQ.data) && (
            <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
              {forecastQ.data && <ForecastPanel forecast={forecastQ.data} />}
              {sentimentQ.data && <SentimentGauge sentiment={sentimentQ.data} />}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 rounded-lg border border-line bg-panel p-4 md:grid-cols-4">
            <input data-testid="mc-underlying" value={underlying}
              onChange={(e) => setUnderlying(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
              placeholder="Underlying" className="rounded border border-line bg-canvas px-3 py-2 font-mono text-xs uppercase text-txt placeholder:text-txtFaint" />
            <input data-testid="mc-expiry" type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)}
              className="rounded border border-line bg-canvas px-3 py-2 font-mono text-xs text-txt" />
            <input data-testid="mc-strike" value={atmStrike}
              onChange={(e) => setAtmStrike(e.target.value.replace(/[^0-9.]/g, ''))}
              placeholder="ATM strike" className="rounded border border-line bg-canvas px-3 py-2 font-mono text-xs text-txt placeholder:text-txtFaint" />
            <input data-testid="mc-paths" value={paths}
              onChange={(e) => setPaths(e.target.value.replace(/[^0-9]/g, ''))}
              placeholder="Paths" className="rounded border border-line bg-canvas px-3 py-2 font-mono text-xs text-txt placeholder:text-txtFaint" />
          </div>

          {canPickTemplate ? (
            <TemplatePicker underlying={underlying} expiry={expiry} atmStrike={strike} onApply={setConfig} />
          ) : (
            <p className="text-xs text-txtFaint" data-testid="mc-need-inputs">Enter an underlying, expiry, and ATM strike to pick a template.</p>
          )}

          {config && (
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-[11px] text-txtDim" data-testid="mc-config-summary">{config.underlying} · {config.legs.length} legs</span>
              <label className="flex items-center gap-2 text-xs text-txtDim">
                <input data-testid="mc-use-sentiment" type="checkbox" checked={useSentiment} onChange={(e) => setUseSentiment(e.target.checked)} />
                Apply sentiment drift
              </label>
              <button data-testid="mc-run" onClick={runMc} disabled={mc.isPending}
                className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-40">
                {mc.isPending ? "Simulating…" : "Run simulation"}
              </button>
            </div>
          )}

          {mcErrMsg && <p className="text-sm text-neg" data-testid="mc-error">{mcErrMsg}</p>}
          {mc.data && <MonteCarloPanel result={mc.data} />}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run to verify it passes** — `cd apps/web && npx vitest run src/pages/Models.test.tsx` → 3 passed.

- [ ] **Step 5: Swap the route** in `apps/web/src/app/Router.tsx` — add the import and replace the models route. Find:

```typescript
<Route path="models" element={<PlaceholderPage title="Models" />} />
```

Replace with:

```typescript
<Route path="models" element={<Models />} />
```

And add the import near the other page imports:

```typescript
import { Models } from '../pages/Models'
```

(Leave `PlaceholderPage` imported — still used by the dashboard route.)

- [ ] **Step 6: Full gate** — from `apps/web`:

```bash
npm run typecheck && npm run lint && npm run test:run
```

Expected: typecheck + lint clean; full suite green (227 + ~12 new = ~239 tests). Then `npm run build` → still "17 HTML documents pre-rendered" (the `/app/models` route is client-only).

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/pages/Models.tsx apps/web/src/pages/Models.test.tsx apps/web/src/app/Router.tsx
git commit -m "feat(web): Models page (insights + monte-carlo) + route

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes (for the executor)

- **Rules of Hooks:** every `useState`/`useQuery`/`useMutation` in `Models.tsx` is declared BEFORE the `if (!entitled) return <ModelsGate />` early return — do not move them below it.
- **Entitlement pre-check:** `useVolForecast(entitled ? ticker : '', …, entitled)` — a free user passes an empty ticker AND `enabled:false`, so nothing fetches (the gate test asserts `getVolForecast` is never called).
- **Template mock:** `<TemplatePicker>` calls `listTemplates`/`buildTemplate` from `lib/strategies`; the page test spies on those module exports (live-binding spy, the established pattern).
- **Auth mock:** copy the `let mockMe` + `vi.mock('../auth/AuthContext', …)` pattern verbatim from `Markets.test.tsx`.
- **Decimal/strings:** these three endpoints return JSON numbers (not Decimal strings) — `pop`, `ev`, `score`, forecast values are all real numbers. No string coercion needed (unlike the OMS money fields).
```
