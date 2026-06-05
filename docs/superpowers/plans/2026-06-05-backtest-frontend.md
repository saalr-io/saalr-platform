# Backtest screen (`/app/backtests`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dedicated `/app/backtests` page to run a model-priced historical backtest on a saved strategy and view the equity curve + metrics. Includes one small backend change (expose the engine's daily equity series). Spec: `docs/superpowers/specs/2026-06-05-backtest-frontend-design.md`.

**Architecture:** Backend — the engine returns a new `equity_series` and the GET exposes it. Frontend — a `lib/backtests.ts` client, TanStack hooks (2s poll mirroring research), pure components, a `Backtests` page, a route, and a Sidebar link.

**Tech Stack:** Python (saalr-core engine + FastAPI) + React 18/TS/Tailwind/TanStack/Vitest. **pnpm** for web.

**Conventions (apply to every task):**
- Web tests from `apps/web`: `npx vitest run <files>`; gate `npm run typecheck` + `npm run lint`. Python: `uv run pytest <path>` (DB on 55432, Redis 6379 for integration).
- Commit footer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Theme tokens only (SVG hex literals allowed); double-quote JSX apostrophes; NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`. Stage ONLY each task's files.

---

### Task 1: backend — expose the daily equity series

**Files:** Modify `packages/core/saalr_core/backtest/engine.py`, `apps/api/saalr_api/backtests/router.py`, `packages/core/tests/test_backtest_engine.py`, `tests/integration/test_backtest_api.py`.

- [ ] **Step 1: engine — add `equity_series`.** In `engine.py`, change the equity accumulator init (near `equity_curve: list[float] = []`):

```python
    equity_curve: list[float] = []
    equity_series: list[dict] = []
    trade_pnls: list[float] = []
```

In the `for d in sim_days:` loop, replace the final `equity_curve.append(...)` line with:

```python
        cur_value = _position_value(legs, closes[d], vol_at(d), d, params.rate)
        eq = params.initial_capital + realized + (cur_value - entry_value - open_cost)
        equity_curve.append(eq)
        equity_series.append({"date": d.isoformat(), "equity": eq})
```

In the returned result dict, add `equity_series` right after `equity_points`:

```python
        "equity_points": len(equity_curve),
        "equity_series": equity_series,
```

- [ ] **Step 2: GET — expose it.** In `apps/api/saalr_api/backtests/router.py`, the `succeeded` branch of `get_backtest_run`:

```python
    if row.status == "succeeded":
        out["metrics"] = (row.metrics_json or {}).get("metrics", {})
        out["equity_series"] = (row.metrics_json or {}).get("equity_series", [])
        out["trade_log_url"] = None
```

- [ ] **Step 3: engine test.** Append to `packages/core/tests/test_backtest_engine.py`:

```python
def test_engine_returns_a_dated_equity_series():
    start = date(2025, 1, 1)
    prices = [100.0 + i * 0.2 for i in range(120)]
    closes = _closes(start, prices)
    cfg = _long_call("2025-02-15")
    t = RelativeTemplate.from_config(cfg, ref_spot=100.0, ref_date=start)
    res = run_backtest_engine(closes, t, _params(start, start + timedelta(days=119)))
    series = res["equity_series"]
    assert len(series) == res["equity_points"]
    assert all(set(p.keys()) == {"date", "equity"} for p in series)
    dates = [p["date"] for p in series]
    assert dates == sorted(dates)  # ISO dates, non-decreasing
    assert series[-1]["equity"] == res["final_equity"]
```

Run: `uv run pytest packages/core/tests/test_backtest_engine.py -q` → all pass.

- [ ] **Step 4: API test.** Read `tests/integration/test_backtest_api.py`; in the test that asserts a `succeeded` GET payload, add an assertion alongside the existing `metrics` check:

```python
    assert "equity_series" in body
    assert len(body["equity_series"]) > 0
    assert set(body["equity_series"][0].keys()) == {"date", "equity"}
```

Run the backtest integration tests (needs DB 55432 + Redis): `uv run --package saalr-backtest-worker pytest tests/integration/test_backtest_api.py -q` (or the project's documented invocation) → pass. If the integration DB/Redis isn't available in the executor, note it and rely on the engine test + a manual end-to-end check in Task 6.

- [ ] **Step 5: commit**

```bash
git add packages/core/saalr_core/backtest/engine.py apps/api/saalr_api/backtests/router.py packages/core/tests/test_backtest_engine.py tests/integration/test_backtest_api.py
git commit -m "feat(backtest): expose the daily equity_series from the engine + GET /v1/backtests/{id}

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `lib/backtests.ts` client + test + hooks

**Files:** Create `apps/web/src/lib/backtests.ts`, `apps/web/src/lib/backtests.test.ts`, `apps/web/src/features/backtests/hooks.ts`.

- [ ] **Step 1: failing test** `apps/web/src/lib/backtests.test.ts`:

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest'
import { createBacktest, getBacktest } from './backtests'

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body })
}
afterEach(() => vi.unstubAllGlobals())

describe('backtests client', () => {
  it('createBacktest POSTs with an Idempotency-Key and returns 202 shape', async () => {
    const f = mockFetch(202, { backtest_id: 'b1', status: 'queued', estimated_duration_seconds: 12, poll_url: '/v1/backtests/b1' })
    vi.stubGlobal('fetch', f)
    const r = await createBacktest('s1', { start_date: '2023-01-01', end_date: '2025-01-01', initial_capital: 100000, include_costs: true }, 'idem-1')
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/v1/strategies/s1/backtest')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('idem-1')
    expect(r.backtest_id).toBe('b1')
  })

  it('getBacktest returns the succeeded payload with metrics + equity_series', async () => {
    const f = mockFetch(200, { backtest_id: 'b1', status: 'succeeded', metrics: { sharpe: 0.6 }, equity_series: [{ date: '2023-01-03', equity: 100000 }] })
    vi.stubGlobal('fetch', f)
    const r = await getBacktest('b1')
    expect(r.status).toBe('succeeded')
    expect(r.equity_series?.[0].equity).toBe(100000)
  })

  it('throws Error(code) on a non-ok status', async () => {
    vi.stubGlobal('fetch', mockFetch(404, { detail: { error: { code: 'RESOURCE_NOT_FOUND' } } }))
    await expect(getBacktest('nope')).rejects.toThrow('RESOURCE_NOT_FOUND')
  })
})
```

- [ ] **Step 2: create** `apps/web/src/lib/backtests.ts`:

```typescript
import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'

export type BacktestStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface BacktestMetrics {
  total_return: number
  annualized_return: number
  sharpe: number
  sortino: number
  max_drawdown: number
  win_rate: number
  trades: number
  avg_trade_pnl: number
}

export interface EquityPoint {
  date: string
  equity: number
}

export interface BacktestRun {
  backtest_id: string
  status: BacktestStatus
  estimated_duration_seconds: number
  poll_url: string
}

export interface BacktestResult {
  backtest_id: string
  status: BacktestStatus
  metrics?: BacktestMetrics
  equity_series?: EquityPoint[]
  trade_log_url?: string | null
  error?: { code: string; message: string }
}

export interface BacktestRequestBody {
  start_date: string
  end_date: string
  initial_capital: number
  include_costs: boolean
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
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail?.error?.code ?? `request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export function createBacktest(
  strategyId: string,
  body: BacktestRequestBody,
  idempotencyKey: string,
): Promise<BacktestRun> {
  return request(`/v1/strategies/${strategyId}/backtest`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function getBacktest(id: string): Promise<BacktestResult> {
  return request(`/v1/backtests/${id}`)
}
```

Run `npx vitest run src/lib/backtests.test.ts` → 3 passed (if the index-access cast trips `tsc`, use `(f.mock.calls[0] as unknown as [string, RequestInit])`).

- [ ] **Step 3: create** `apps/web/src/features/backtests/hooks.ts`:

```typescript
import { useMutation, useQuery } from '@tanstack/react-query'
import { createBacktest, getBacktest, type BacktestRequestBody } from '../../lib/backtests'

export function useCreateBacktest() {
  return useMutation({
    mutationFn: ({ strategyId, body, key }: { strategyId: string; body: BacktestRequestBody; key: string }) =>
      createBacktest(strategyId, body, key),
  })
}

export function useBacktest(id: string | null) {
  return useQuery({
    queryKey: ['backtest', id],
    queryFn: () => getBacktest(id!),
    enabled: !!id,
    retry: false,
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'succeeded' || s === 'failed' ? false : 2000
    },
  })
}
```

- [ ] **Step 4: typecheck + lint** clean. **Commit:**

```bash
git add apps/web/src/lib/backtests.ts apps/web/src/lib/backtests.test.ts apps/web/src/features/backtests/hooks.ts
git commit -m "feat(web): backtests client + hooks (2s poll, stops on terminal status)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: pure components — EquityCurve, MetricsPanel, BacktestStatus

**Files:** Create `apps/web/src/features/backtests/{EquityCurve,MetricsPanel,BacktestStatus}.tsx` + their `.test.tsx`.

- [ ] **Step 1: tests** (three files):

`EquityCurve.test.tsx`:
```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EquityCurve } from './EquityCurve'

const series = [
  { date: '2023-01-03', equity: 100000 },
  { date: '2023-01-04', equity: 101000 },
  { date: '2023-01-05', equity: 99000 },
]

describe('EquityCurve', () => {
  it('draws one point per equity sample plus a baseline', () => {
    render(<EquityCurve series={series} initialCapital={100000} />)
    expect(screen.getByTestId('equity-line').getAttribute('points')!.trim().split(' ')).toHaveLength(3)
    expect(screen.getByTestId('equity-baseline')).toBeInTheDocument()
  })
})
```

`MetricsPanel.test.tsx`:
```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MetricsPanel } from './MetricsPanel'
import type { BacktestMetrics } from '../../lib/backtests'

const m: BacktestMetrics = {
  total_return: 0.124, annualized_return: 0.061, sharpe: 0.67, sortino: 0.9,
  max_drawdown: 0.18, win_rate: 0.55, trades: 12, avg_trade_pnl: 340.5,
}

describe('MetricsPanel', () => {
  it('renders metrics with percent formatting + the approximate chip', () => {
    render(<MetricsPanel metrics={m} finalEquity={112400} approximate model="bsm" volLookback={20} />)
    expect(screen.getByTestId('mx-total-return').textContent).toContain('12.4%')
    expect(screen.getByTestId('mx-sharpe').textContent).toContain('0.67')
    expect(screen.getByText(/approximate/i)).toBeInTheDocument()
  })
})
```

`BacktestStatus.test.tsx`:
```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BacktestStatus } from './BacktestStatus'

describe('BacktestStatus', () => {
  it('shows a running state with the estimate', () => {
    render(<BacktestStatus status="running" estSeconds={15} error={null} />)
    expect(screen.getByTestId('bt-running').textContent).toMatch(/15/)
  })
  it('shows the failure message', () => {
    render(<BacktestStatus status="failed" estSeconds={0} error="no bars for SPY" />)
    expect(screen.getByTestId('bt-error').textContent).toContain('no bars for SPY')
  })
})
```

- [ ] **Step 2: create** `apps/web/src/features/backtests/EquityCurve.tsx`:

```typescript
import type { EquityPoint } from '../../lib/backtests'

const W = 520
const H = 220
const PAD = 8

function scaler(min: number, max: number, lo: number, hi: number) {
  const span = max - min || 1
  return (v: number) => lo + (hi - lo) * ((v - min) / span)
}

export function EquityCurve({ series, initialCapital }: { series: EquityPoint[]; initialCapital: number }) {
  const eq = series.map((p) => p.equity)
  const n = eq.length
  const ys = [...eq, initialCapital]
  const sx = scaler(0, Math.max(1, n - 1), PAD, W - PAD)
  const sy = scaler(Math.min(...ys), Math.max(...ys), H - PAD, PAD)
  const pts = series.map((p, i) => `${sx(i).toFixed(1)},${sy(p.equity).toFixed(1)}`).join(' ')
  const baseY = sy(initialCapital)
  const last = eq[n - 1] ?? initialCapital
  const up = last >= initialCapital
  return (
    <figure className="rounded-lg border border-line bg-panel p-4" data-testid="equity-curve">
      <figcaption className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Equity curve</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <line data-testid="equity-baseline" x1={PAD} y1={baseY} x2={W - PAD} y2={baseY} stroke="#5b6472" strokeWidth={1} strokeDasharray="3 3" />
        <polyline data-testid="equity-line" points={pts} fill="none" stroke={up ? "#37c98b" : "#ff5d73"} strokeWidth={1.8} />
      </svg>
    </figure>
  )
}
```

- [ ] **Step 3: create** `apps/web/src/features/backtests/MetricsPanel.tsx`:

```typescript
import type { BacktestMetrics } from '../../lib/backtests'

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
const usd = (v: number) => `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`

export function MetricsPanel({
  metrics, finalEquity, approximate, model, volLookback,
}: {
  metrics: BacktestMetrics; finalEquity: number; approximate: boolean; model: string; volLookback: number
}) {
  const tiles: { key: string; label: string; value: string; cls?: string; testid: string }[] = [
    { key: 'tr', label: 'Total return', value: pct(metrics.total_return), cls: metrics.total_return >= 0 ? 'text-pos' : 'text-neg', testid: 'mx-total-return' },
    { key: 'ar', label: 'Annualized', value: pct(metrics.annualized_return), testid: 'mx-annualized' },
    { key: 'sh', label: 'Sharpe', value: metrics.sharpe.toFixed(2), testid: 'mx-sharpe' },
    { key: 'so', label: 'Sortino', value: metrics.sortino.toFixed(2), testid: 'mx-sortino' },
    { key: 'dd', label: 'Max drawdown', value: pct(metrics.max_drawdown), cls: 'text-neg', testid: 'mx-maxdd' },
    { key: 'wr', label: 'Win rate', value: pct(metrics.win_rate), testid: 'mx-winrate' },
    { key: 'tc', label: 'Trades', value: String(metrics.trades), testid: 'mx-trades' },
    { key: 'ap', label: 'Avg trade P&L', value: usd(metrics.avg_trade_pnl), cls: metrics.avg_trade_pnl >= 0 ? 'text-pos' : 'text-neg', testid: 'mx-avgpnl' },
    { key: 'fe', label: 'Final equity', value: usd(finalEquity), testid: 'mx-final' },
  ]
  return (
    <div className="space-y-3 rounded-lg border border-line bg-panel p-4" data-testid="metrics-panel">
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <div key={t.key} className="rounded border border-lineSoft p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">{t.label}</p>
            <p data-testid={t.testid} className={`tnum mt-1 text-lg font-semibold ${t.cls ?? 'text-txt'}`}>{t.value}</p>
          </div>
        ))}
      </div>
      {approximate && (
        <p className="font-mono text-[11px] text-txtFaint">
          model {model} · realized-vol IV · vol lookback {volLookback} · <span className="text-warn">approximate</span> (model-priced, not tick data)
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 4: create** `apps/web/src/features/backtests/BacktestStatus.tsx`:

```typescript
import type { BacktestStatus as Status } from '../../lib/backtests'

export function BacktestStatus({ status, estSeconds, error }: { status: Status; estSeconds: number; error: string | null }) {
  if (status === 'failed') {
    return <p data-testid="bt-error" className="text-sm text-neg">Backtest failed: {error ?? 'unknown error'}</p>
  }
  return (
    <div data-testid="bt-running" className="flex items-center gap-3 rounded-lg border border-line bg-panel2 px-4 py-6">
      <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
      <span className="text-sm text-txtDim">Running backtest… ≈ {estSeconds}s</span>
    </div>
  )
}
```

- [ ] **Step 5: run** `npx vitest run src/features/backtests` → all pass; typecheck + lint clean. **Commit:**

```bash
git add apps/web/src/features/backtests/EquityCurve.tsx apps/web/src/features/backtests/EquityCurve.test.tsx apps/web/src/features/backtests/MetricsPanel.tsx apps/web/src/features/backtests/MetricsPanel.test.tsx apps/web/src/features/backtests/BacktestStatus.tsx apps/web/src/features/backtests/BacktestStatus.test.tsx
git commit -m "feat(web): backtest EquityCurve + MetricsPanel + BacktestStatus

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: StrategyPicker + BacktestForm + Backtests page + route + Sidebar + test

**Files:** Create `apps/web/src/features/backtests/{StrategyPicker,BacktestForm}.tsx`, `apps/web/src/pages/Backtests.tsx`, `apps/web/src/pages/Backtests.test.tsx`; modify `apps/web/src/app/Router.tsx`, `apps/web/src/components/Sidebar.tsx`.

- [ ] **Step 1: create** `apps/web/src/features/backtests/StrategyPicker.tsx`:

```typescript
import type { Strategy } from '../../lib/strategies'

export function StrategyPicker({
  strategies, value, onChange,
}: {
  strategies: Strategy[]; value: string; onChange: (id: string) => void
}) {
  if (strategies.length === 0) {
    return (
      <p className="text-sm text-txtFaint" data-testid="no-strategies">
        No saved strategies yet — <a href="/app/strategies" className="text-accent underline">build and save one</a> first.
      </p>
    )
  }
  return (
    <label className="flex items-center gap-2 text-xs text-txtDim">
      Strategy
      <select data-testid="bt-strategy" value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-line bg-panel px-2 py-2 font-mono text-xs text-txt">
        <option value="">Select…</option>
        {strategies.map((s) => <option key={s.strategy_id} value={s.strategy_id}>{s.name}</option>)}
      </select>
    </label>
  )
}
```

- [ ] **Step 2: create** `apps/web/src/features/backtests/BacktestForm.tsx`:

```typescript
import { useState } from 'react'
import type { BacktestRequestBody } from '../../lib/backtests'

function isoYearsAgo(years: number): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}

export function BacktestForm({
  disabled, pending, onSubmit,
}: {
  disabled: boolean; pending: boolean; onSubmit: (body: BacktestRequestBody, key: string) => void
}) {
  const [start, setStart] = useState(isoYearsAgo(2))
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10))
  const [capital, setCapital] = useState('100000')
  const [costs, setCosts] = useState(true)

  const valid = !!start && !!end && end > start
  function submit() {
    if (!valid) return
    onSubmit(
      { start_date: start, end_date: end, initial_capital: parseInt(capital, 10) || 100000, include_costs: costs },
      crypto.randomUUID(),
    )
  }
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-panel p-4">
      <label className="text-xs text-txtDim">Start
        <input data-testid="bt-start" type="date" value={start} onChange={(e) => setStart(e.target.value)}
          className="ml-2 rounded border border-line bg-canvas px-2 py-1 font-mono text-xs text-txt" /></label>
      <label className="text-xs text-txtDim">End
        <input data-testid="bt-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)}
          className="ml-2 rounded border border-line bg-canvas px-2 py-1 font-mono text-xs text-txt" /></label>
      <label className="text-xs text-txtDim">Capital
        <input data-testid="bt-capital" value={capital} onChange={(e) => setCapital(e.target.value.replace(/[^0-9]/g, ''))}
          className="ml-2 w-28 rounded border border-line bg-canvas px-2 py-1 font-mono text-xs text-txt" /></label>
      <label className="flex items-center gap-2 text-xs text-txtDim">
        <input data-testid="bt-costs" type="checkbox" checked={costs} onChange={(e) => setCosts(e.target.checked)} /> Include costs
      </label>
      <button data-testid="bt-run" onClick={submit} disabled={disabled || pending || !valid}
        className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-40">
        {pending ? "Running…" : "Run backtest"}
      </button>
    </div>
  )
}
```

- [ ] **Step 3: failing page test** `apps/web/src/pages/Backtests.test.tsx`:

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as strategies from '../lib/strategies'
import * as backtests from '../lib/backtests'
import { Backtests } from './Backtests'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const STRAT = { strategy_id: 's1', name: 'SPY bull call', description: null, state: 'draft', market: 'US', config: { underlying: 'SPY', legs: [] }, created_at: 'x', updated_at: 'x' }

describe('Backtests page', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('prompts when there are no saved strategies', async () => {
    vi.spyOn(strategies, 'listStrategies').mockResolvedValue({ strategies: [], next_cursor: null })
    render(wrap(<Backtests />))
    await waitFor(() => expect(screen.getByTestId('no-strategies')).toBeInTheDocument())
  })

  it('runs a backtest and renders the curve + metrics on success', async () => {
    vi.spyOn(strategies, 'listStrategies').mockResolvedValue({ strategies: [STRAT] as never, next_cursor: null })
    vi.spyOn(backtests, 'createBacktest').mockResolvedValue({ backtest_id: 'b1', status: 'queued', estimated_duration_seconds: 10, poll_url: '/v1/backtests/b1' })
    vi.spyOn(backtests, 'getBacktest').mockResolvedValue({
      backtest_id: 'b1', status: 'succeeded',
      metrics: { total_return: 0.1, annualized_return: 0.05, sharpe: 0.6, sortino: 0.8, max_drawdown: 0.2, win_rate: 0.5, trades: 8, avg_trade_pnl: 100 },
      equity_series: [{ date: '2023-01-03', equity: 100000 }, { date: '2023-01-04', equity: 110000 }],
    })
    render(wrap(<Backtests />))
    await waitFor(() => expect(screen.getByTestId('bt-strategy')).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('bt-strategy'), { target: { value: 's1' } })
    fireEvent.click(screen.getByTestId('bt-run'))
    await waitFor(() => expect(screen.getByTestId('equity-curve')).toBeInTheDocument())
    expect(screen.getByTestId('metrics-panel')).toBeInTheDocument()
    expect(screen.getByTestId('mx-total-return').textContent).toContain('10.0%')
  })
})
```

- [ ] **Step 4: create** `apps/web/src/pages/Backtests.tsx`:

```typescript
import { useState } from 'react'
import { useStrategies } from '../features/strategies/hooks'
import { useCreateBacktest, useBacktest } from '../features/backtests/hooks'
import { StrategyPicker } from '../features/backtests/StrategyPicker'
import { BacktestForm } from '../features/backtests/BacktestForm'
import { EquityCurve } from '../features/backtests/EquityCurve'
import { MetricsPanel } from '../features/backtests/MetricsPanel'
import { BacktestStatus } from '../features/backtests/BacktestStatus'
import type { BacktestRequestBody } from '../lib/backtests'

export function Backtests() {
  const strategiesQ = useStrategies()
  const strategies = strategiesQ.data?.strategies ?? []
  const [strategyId, setStrategyId] = useState('')
  const [capital, setCapital] = useState(100000)
  const create = useCreateBacktest()
  const [backtestId, setBacktestId] = useState<string | null>(null)
  const runQ = useBacktest(backtestId)
  const run = runQ.data

  function onSubmit(body: BacktestRequestBody, key: string) {
    if (!strategyId) return
    setCapital(body.initial_capital)
    setBacktestId(null)
    create.mutate({ strategyId, body, key }, { onSuccess: (r) => setBacktestId(r.backtest_id) })
  }

  const status = run?.status ?? (create.isPending ? 'queued' : null)
  const estSeconds = create.data?.estimated_duration_seconds ?? 0

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Backtest</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Historical backtest</h2>
      </div>

      <StrategyPicker strategies={strategies} value={strategyId} onChange={setStrategyId} />
      {strategies.length > 0 && (
        <BacktestForm disabled={!strategyId} pending={create.isPending} onSubmit={onSubmit} />
      )}

      {create.isError && <p className="text-sm text-neg">Couldn&apos;t start the backtest — try again.</p>}

      {status && status !== 'succeeded' && (
        <BacktestStatus
          status={status}
          estSeconds={estSeconds}
          error={run?.error?.message ?? null}
        />
      )}

      {run?.status === 'succeeded' && run.metrics && run.equity_series && (
        <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
          <EquityCurve series={run.equity_series} initialCapital={capital} />
          <MetricsPanel metrics={run.metrics} finalEquity={run.equity_series[run.equity_series.length - 1].equity} approximate model="bsm" volLookback={20} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: route** in `apps/web/src/app/Router.tsx` — add `import { Backtests } from '../pages/Backtests'` and `<Route path="backtests" element={<Backtests />} />` (next to `strategies`).

- [ ] **Step 6: Sidebar** — in `apps/web/src/components/Sidebar.tsx`, add `['/backtests', 'Backtests']` to the `'Trade'` section's `items` array (after `['/strategies', 'Strategies']`).

- [ ] **Step 7: run** `npx vitest run src/pages/Backtests.test.tsx` → 2 passed.

- [ ] **Step 8: commit**

```bash
git add apps/web/src/features/backtests/StrategyPicker.tsx apps/web/src/features/backtests/BacktestForm.tsx apps/web/src/pages/Backtests.tsx apps/web/src/pages/Backtests.test.tsx apps/web/src/app/Router.tsx apps/web/src/components/Sidebar.tsx
git commit -m "feat(web): Backtests page (/app/backtests) — picker + form + curve + metrics + route + nav

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: final gate

- [ ] **Step 1: web gate** from `apps/web`: `npm run typecheck && npm run lint && npm run test:run` → green (≈ +12 tests). `npm run build` → still "47 HTML documents pre-rendered" (`/app/backtests` is client-only).
- [ ] **Step 2: python gate** (engine): `uv run pytest packages/core/tests/test_backtest_engine.py -q` → green. Backtest integration test if DB/Redis available.
- [ ] **Step 3 (optional, local stack is running): end-to-end smoke** — create a SPY strategy via the API, POST a backtest, poll, confirm `equity_series` + metrics come back (the running worker + SPY bars make this real). Report the result.

---

## Self-Review notes (for the executor)

- **The only backend behaviour change** is the additive `equity_series` (engine return + GET); existing metrics/flags are untouched, so the existing backtest tests stay green.
- **Poll** mirrors `features/research/hooks.useNote` exactly (`refetchInterval` → `false` on `succeeded`/`failed`).
- **Ungated:** backtest has no entitlement gate — `lib/backtests.ts` omits the 402/`EntitlementError` branch.
- **Strategy required:** the POST needs a saved `strategy_id`; the empty-strategies case links to `/app/strategies`.
- **Returns are fractions on the wire** (× 100 for display); Sharpe/Sortino are ratios; PnL/equity are dollars.
- **Idempotency:** a fresh `crypto.randomUUID()` per submit + disable-while-pending guards double-runs.
```
