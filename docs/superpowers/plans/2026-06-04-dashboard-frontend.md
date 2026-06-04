# Dashboard frontend (AN-4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/app` index `PlaceholderPage` with an aggregating dashboard — an ungated portfolio overview, a watchlist derived from held position symbols (vol-forecast + sentiment, `ml_forecast`-gated), and a market snapshot for the primary symbol (`vol_surface`-gated) — with gated widgets degrading to compact inline upgrade nudges.

**Architecture:** No new API client — reuses `lib/oms.ts`, `lib/models.ts`, `lib/market.ts` and the existing AN-1/AN-3 hooks. Five pure presentational components + a `Dashboard` page that owns all hooks and fans the watchlist out with TanStack `useQueries` over the dynamic symbol list. One route swap (retires the last `PlaceholderPage` usage).

**Tech Stack:** Vike + React 18 + TS strict + Tailwind (theme tokens only) + TanStack Query + react-router 6 + Vitest + @testing-library/react.

**Conventions (apply to every task):**
- Run web tests from `apps/web`: `npx vitest run <files>`. Gate: `npm run typecheck` + `npm run lint`.
- Commit footer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Theme tokens only for Tailwind **class** colors; SVG hex literals allowed. No raw Tailwind color classes.
- Double-quote JSX strings containing apostrophes.
- NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`. Stage ONLY each task's files.
- Components using `<Link>` need `<MemoryRouter>` in tests.

---

### Task 1: `UpgradeHint.tsx` (pure)

**Files:** Create `apps/web/src/features/dashboard/UpgradeHint.tsx` + `UpgradeHint.test.tsx`.

- [ ] **Step 1: failing test** `apps/web/src/features/dashboard/UpgradeHint.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { UpgradeHint } from './UpgradeHint'

describe('UpgradeHint', () => {
  it('renders the feature text and an upgrade link to the chosen plan', () => {
    render(<MemoryRouter><UpgradeHint feature="Forecasts for your holdings" plan="premium" /></MemoryRouter>)
    expect(screen.getByTestId('upgrade-hint').textContent).toContain('Forecasts for your holdings')
    expect(screen.getByRole('link', { name: /upgrade/i }).getAttribute('href')).toBe('/billing?plan=premium')
  })

  it('defaults to the pro plan', () => {
    render(<MemoryRouter><UpgradeHint feature="x" /></MemoryRouter>)
    expect(screen.getByRole('link', { name: /upgrade/i }).getAttribute('href')).toBe('/billing?plan=pro')
  })
})
```

- [ ] **Step 2: run → FAIL** — `cd apps/web && npx vitest run src/features/dashboard/UpgradeHint.test.tsx`

- [ ] **Step 3: create** `apps/web/src/features/dashboard/UpgradeHint.tsx`:

```typescript
import { Link } from 'react-router-dom'

export function UpgradeHint({ feature, plan = 'pro' }: { feature: string; plan?: 'pro' | 'premium' }) {
  return (
    <div className="rounded-lg border border-accent/30 bg-accent/5 p-4 text-center" data-testid="upgrade-hint">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">// Pro</p>
      <p className="mt-2 text-sm text-txtDim">{feature}</p>
      <Link to={`/billing?plan=${plan}`} className="mt-3 inline-block rounded-md bg-accent px-4 py-1.5 text-xs font-medium text-canvas transition hover:opacity-90">
        Upgrade
      </Link>
    </div>
  )
}
```

- [ ] **Step 4: run → 2 passed**; typecheck + lint clean.

- [ ] **Step 5: commit**

```bash
git add apps/web/src/features/dashboard/UpgradeHint.tsx apps/web/src/features/dashboard/UpgradeHint.test.tsx
git commit -m "feat(web): dashboard UpgradeHint (inline gated-widget nudge)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `StatStrip.tsx` (pure)

**Files:** Create `apps/web/src/features/dashboard/StatStrip.tsx` + `StatStrip.test.tsx`.

- [ ] **Step 1: failing test** `apps/web/src/features/dashboard/StatStrip.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatStrip } from './StatStrip'

describe('StatStrip', () => {
  it('shows the email and the three counts', () => {
    render(<StatStrip email="a@b.com" tier="pro" accounts={2} positions={5} workingOrders={1} />)
    expect(screen.getByText(/a@b\.com/)).toBeInTheDocument()
    expect(screen.getByTestId('stat-accounts').textContent).toBe('2')
    expect(screen.getByTestId('stat-positions').textContent).toBe('5')
    expect(screen.getByTestId('stat-orders').textContent).toBe('1')
  })
})
```

- [ ] **Step 2: run → FAIL**

- [ ] **Step 3: create** `apps/web/src/features/dashboard/StatStrip.tsx`:

```typescript
export function StatStrip({
  email, tier, accounts, positions, workingOrders,
}: {
  email: string; tier: string; accounts: number; positions: number; workingOrders: number
}) {
  const tiles = [
    { key: 'accounts', label: 'Accounts', value: accounts, testid: 'stat-accounts' },
    { key: 'positions', label: 'Open positions', value: positions, testid: 'stat-positions' },
    { key: 'orders', label: 'Working orders', value: workingOrders, testid: 'stat-orders' },
  ]
  return (
    <div className="space-y-3">
      <p className="text-sm text-txtDim">
        Welcome back, <span className="text-txt">{email}</span>
        <span className="ml-2 rounded-full border border-line px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-txtFaint">{tier}</span>
      </p>
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <div key={t.key} className="rounded-lg border border-line bg-panel p-4">
            <p className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">{t.label}</p>
            <p data-testid={t.testid} className="tnum mt-1 text-2xl font-semibold text-txt">{t.value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: run → 1 passed**; typecheck + lint clean.

- [ ] **Step 5: commit**

```bash
git add apps/web/src/features/dashboard/StatStrip.tsx apps/web/src/features/dashboard/StatStrip.test.tsx
git commit -m "feat(web): dashboard StatStrip (greeting + account/position/order counts)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `PortfolioOverview.tsx` (pure)

**Files:** Create `apps/web/src/features/dashboard/PortfolioOverview.tsx` + `PortfolioOverview.test.tsx`.

- [ ] **Step 1: failing test** `apps/web/src/features/dashboard/PortfolioOverview.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PortfolioOverview } from './PortfolioOverview'
import type { Order } from '../../lib/oms'

const O = (over: Partial<Order> = {}): Order => ({
  order_id: 'o1', symbol: 'SPY', side: 'BUY', qty: 1, order_type: 'market', status: 'filled',
  broker_order_id: null, reject_reason_code: null, created_at: '2026-06-04T10:00:00Z', ...over,
})

describe('PortfolioOverview', () => {
  it('renders recent orders', () => {
    render(<MemoryRouter><PortfolioOverview orders={[O(), O({ order_id: 'o2', status: 'rejected' })]} /></MemoryRouter>)
    expect(screen.getByTestId('overview-order-o1')).toBeInTheDocument()
    expect(screen.getByTestId('overview-order-o2').textContent).toContain('rejected')
  })

  it('shows an empty state', () => {
    render(<MemoryRouter><PortfolioOverview orders={[]} /></MemoryRouter>)
    expect(screen.getByTestId('overview-empty')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: run → FAIL**

- [ ] **Step 3: create** `apps/web/src/features/dashboard/PortfolioOverview.tsx`:

```typescript
import { Link } from 'react-router-dom'
import type { Order } from '../../lib/oms'

function statusClass(status: string): string {
  if (status === 'filled') return 'text-pos'
  if (status === 'rejected' || status === 'cancelled') return 'text-neg'
  return 'text-warn'
}

export function PortfolioOverview({ orders }: { orders: Order[] }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-4" data-testid="portfolio-overview">
      <div className="mb-3 flex items-center justify-between">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Recent orders</p>
        <Link to="/portfolio" className="text-[11px] text-accent hover:underline">View portfolio →</Link>
      </div>
      {orders.length === 0 ? (
        <p className="py-6 text-center text-sm text-txtFaint" data-testid="overview-empty">No orders yet.</p>
      ) : (
        <table className="tnum w-full font-mono text-xs">
          <tbody>
            {orders.map((o) => (
              <tr key={o.order_id} className="border-b border-lineSoft" data-testid={`overview-order-${o.order_id}`}>
                <td className="py-1.5 text-txt">{o.symbol}</td>
                <td className="py-1.5 text-txtDim">{o.side}</td>
                <td className="py-1.5 text-right text-txtDim">{o.qty}</td>
                <td className={`py-1.5 text-right ${statusClass(o.status)}`}>{o.status}</td>
                <td className="py-1.5 text-right text-txtFaint">{new Date(o.created_at).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

- [ ] **Step 4: run → 2 passed**; typecheck + lint clean.

- [ ] **Step 5: commit**

```bash
git add apps/web/src/features/dashboard/PortfolioOverview.tsx apps/web/src/features/dashboard/PortfolioOverview.test.tsx
git commit -m "feat(web): dashboard PortfolioOverview (recent orders + link)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `WatchlistTable.tsx` (pure)

**Files:** Create `apps/web/src/features/dashboard/WatchlistTable.tsx` + `WatchlistTable.test.tsx`.

- [ ] **Step 1: failing test** `apps/web/src/features/dashboard/WatchlistTable.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { WatchlistTable, type WatchRow } from './WatchlistTable'

const R = (over: Partial<WatchRow> = {}): WatchRow => ({
  symbol: 'AAPL', forecastPct: 22.5, sentimentLabel: 'bullish', loading: false, ...over,
})

describe('WatchlistTable', () => {
  it('renders a row with the vol forecast and sentiment chip', () => {
    render(<MemoryRouter><WatchlistTable rows={[R()]} entitled={true} onAddSymbol={vi.fn()} /></MemoryRouter>)
    const row = screen.getByTestId('watch-AAPL')
    expect(row.textContent).toContain('22.5%')
    expect(row.textContent).toContain('bullish')
  })

  it('shows an upgrade hint when not entitled', () => {
    render(<MemoryRouter><WatchlistTable rows={[]} entitled={false} onAddSymbol={vi.fn()} /></MemoryRouter>)
    expect(screen.getByTestId('upgrade-hint')).toBeInTheDocument()
  })

  it('lets the user add a symbol from the empty state', () => {
    const onAdd = vi.fn()
    render(<MemoryRouter><WatchlistTable rows={[]} entitled={true} onAddSymbol={onAdd} /></MemoryRouter>)
    fireEvent.change(screen.getByTestId('watchlist-add-input'), { target: { value: 'TSLA' } })
    fireEvent.click(screen.getByTestId('watchlist-add-btn'))
    expect(onAdd).toHaveBeenCalledWith('TSLA')
  })
})
```

- [ ] **Step 2: run → FAIL**

- [ ] **Step 3: create** `apps/web/src/features/dashboard/WatchlistTable.tsx`:

```typescript
import { useState } from 'react'
import { UpgradeHint } from './UpgradeHint'

export interface WatchRow {
  symbol: string
  forecastPct: number | null
  sentimentLabel: 'bearish' | 'neutral' | 'bullish' | null
  loading: boolean
}

const CHIP: Record<string, string> = { bearish: 'text-neg', neutral: 'text-warn', bullish: 'text-pos' }

function AddSymbol({ onAddSymbol }: { onAddSymbol: (s: string) => void }) {
  const [val, setVal] = useState('')
  function add() {
    const s = val.trim().toUpperCase()
    if (s) { onAddSymbol(s); setVal('') }
  }
  return (
    <div className="flex gap-2">
      <input data-testid="watchlist-add-input" value={val}
        onChange={(e) => setVal(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
        onKeyDown={(e) => { if (e.key === 'Enter') add() }}
        placeholder="Add ticker" maxLength={8}
        className="w-28 rounded border border-line bg-canvas px-2 py-1 font-mono text-xs uppercase text-txt placeholder:text-txtFaint" />
      <button data-testid="watchlist-add-btn" onClick={add}
        className="rounded border border-line px-2 py-1 text-xs text-txtDim hover:text-txt">Add</button>
    </div>
  )
}

export function WatchlistTable({ rows, entitled, onAddSymbol }: {
  rows: WatchRow[]; entitled: boolean; onAddSymbol: (s: string) => void
}) {
  if (!entitled) {
    return (
      <div className="rounded-lg border border-line bg-panel p-4">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Watchlist</p>
        <UpgradeHint feature="Forecasts & sentiment for the symbols you hold" />
      </div>
    )
  }
  return (
    <div className="space-y-3 rounded-lg border border-line bg-panel p-4" data-testid="watchlist">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Watchlist</p>
      {rows.length === 0 ? (
        <div className="space-y-3" data-testid="watchlist-empty">
          <p className="text-sm text-txtFaint">No symbols yet — add one to track its forecast and sentiment.</p>
          <AddSymbol onAddSymbol={onAddSymbol} />
        </div>
      ) : (
        <>
          <table className="tnum w-full font-mono text-xs">
            <thead>
              <tr className="border-b border-line text-[10px] uppercase tracking-wider text-txtFaint">
                <th className="py-1.5 text-left">Symbol</th>
                <th className="py-1.5 text-right">Vol forecast</th>
                <th className="py-1.5 text-right">Sentiment</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.symbol} className="border-b border-lineSoft" data-testid={`watch-${r.symbol}`}>
                  <td className="py-1.5 text-txt">{r.symbol}</td>
                  <td className="py-1.5 text-right text-txtDim">
                    {r.loading ? "…" : r.forecastPct != null ? `${r.forecastPct.toFixed(1)}%` : "—"}
                  </td>
                  <td className={`py-1.5 text-right ${r.sentimentLabel ? CHIP[r.sentimentLabel] : "text-txtFaint"}`}>
                    {r.loading ? "…" : r.sentimentLabel ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <AddSymbol onAddSymbol={onAddSymbol} />
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 4: run → 3 passed**; typecheck + lint clean.

- [ ] **Step 5: commit**

```bash
git add apps/web/src/features/dashboard/WatchlistTable.tsx apps/web/src/features/dashboard/WatchlistTable.test.tsx
git commit -m "feat(web): dashboard WatchlistTable (per-symbol forecast + sentiment, add input)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `MarketSnapshot.tsx` (pure)

**Files:** Create `apps/web/src/features/dashboard/MarketSnapshot.tsx` + `MarketSnapshot.test.tsx`.

- [ ] **Step 1: failing test** `apps/web/src/features/dashboard/MarketSnapshot.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { MarketSnapshot } from './MarketSnapshot'
import type { IvSurface } from '../../lib/market'

const G = (iv: number) => ({ price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv })
const SURFACE: IvSurface = {
  ticker: 'SPY', market: 'US', as_of: 'x', spot: 100, data_provider: 'massive', model: 'bsm',
  risk_free_source: 'fred', freshness_ms: 0,
  expiries: [{ expiry: '2026-07-17', strikes: [
    { strike: 95, calls: G(0.22), puts: G(0.24) },
    { strike: 100, calls: G(0.20), puts: G(0.21) }] }],
}

describe('MarketSnapshot', () => {
  it('shows spot and ATM IV from the surface', () => {
    render(<MarketSnapshot symbol="SPY" surface={SURFACE} entitled={true} loading={false} />)
    expect(screen.getByTestId('snapshot').textContent).toContain('100.00')
    expect(screen.getByTestId('snapshot-iv').textContent).toContain('20.5%')
  })

  it('shows an upgrade hint when not entitled', () => {
    render(<MemoryRouter><MarketSnapshot symbol="SPY" surface={null} entitled={false} loading={false} /></MemoryRouter>)
    expect(screen.getByTestId('upgrade-hint')).toBeInTheDocument()
  })

  it('prompts when there is no symbol', () => {
    render(<MarketSnapshot symbol="" surface={null} entitled={true} loading={false} />)
    expect(screen.getByTestId('snapshot-empty')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: run → FAIL**

- [ ] **Step 3: create** `apps/web/src/features/dashboard/MarketSnapshot.tsx`:

```typescript
import type { IvSurface } from '../../lib/market'
import { UpgradeHint } from './UpgradeHint'

function atmIv(surface: IvSurface): { expiry: string; iv: number } | null {
  const e = surface.expiries[0]
  if (!e || e.strikes.length === 0) return null
  const s = e.strikes.reduce((best, x) =>
    Math.abs(x.strike - surface.spot) < Math.abs(best.strike - surface.spot) ? x : best, e.strikes[0])
  return { expiry: e.expiry, iv: ((s.calls.iv + s.puts.iv) / 2) * 100 }
}

export function MarketSnapshot({ symbol, surface, entitled, loading }: {
  symbol: string; surface: IvSurface | null; entitled: boolean; loading: boolean
}) {
  if (!entitled) {
    return (
      <div className="rounded-lg border border-line bg-panel p-4">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Market snapshot</p>
        <UpgradeHint feature={`Live IV snapshot${symbol ? ` for ${symbol}` : ""}`} />
      </div>
    )
  }
  if (!symbol) {
    return (
      <div className="rounded-lg border border-line bg-panel p-4">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Market snapshot</p>
        <p className="py-6 text-center text-sm text-txtFaint" data-testid="snapshot-empty">Hold a position to see its IV snapshot.</p>
      </div>
    )
  }
  const atm = surface ? atmIv(surface) : null
  return (
    <div className="rounded-lg border border-line bg-panel p-4" data-testid="snapshot">
      <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Market snapshot · {symbol}</p>
      {!surface ? (
        loading
          ? <div className="animate-pulse rounded bg-panel2 py-10" data-testid="snapshot-loading" />
          : <p className="py-6 text-center text-sm text-txtFaint">Snapshot unavailable.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-3 font-mono text-xs text-txtDim">
          <div className="flex justify-between"><dt>spot</dt><dd className="tnum text-txt">{surface.spot.toFixed(2)}</dd></div>
          <div className="flex justify-between"><dt>ATM IV</dt><dd data-testid="snapshot-iv" className="tnum text-txt">{atm ? `${atm.iv.toFixed(1)}%` : "—"}</dd></div>
          <div className="flex justify-between"><dt>expiry</dt><dd className="text-txtDim">{atm?.expiry ?? "—"}</dd></div>
          <div className="flex justify-between"><dt>provider</dt><dd className="text-txtFaint">{surface.data_provider}</dd></div>
        </dl>
      )}
    </div>
  )
}
```

- [ ] **Step 4: run → 3 passed** (spot 100 nearest strike 100 → avg(0.20,0.21)=0.205 → 20.5%); typecheck + lint clean.

- [ ] **Step 5: commit**

```bash
git add apps/web/src/features/dashboard/MarketSnapshot.tsx apps/web/src/features/dashboard/MarketSnapshot.test.tsx
git commit -m "feat(web): dashboard MarketSnapshot (spot + ATM IV for primary symbol)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `Dashboard.tsx` page + route swap + PlaceholderPage cleanup

**Files:**
- Create: `apps/web/src/pages/Dashboard.tsx`, `apps/web/src/pages/Dashboard.test.tsx`
- Modify: `apps/web/src/app/Router.tsx`
- Possibly delete: `apps/web/src/components/PlaceholderPage.tsx` (only if unreferenced — see Step 5)

- [ ] **Step 1: failing test** `apps/web/src/pages/Dashboard.test.tsx`:

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as oms from '../lib/oms'
import * as models from '../lib/models'
import * as market from '../lib/market'
import { Dashboard } from './Dashboard'

let mockMe: { user: { email: string }; tier: string; entitlements: Record<string, boolean | number> } | null
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ me: mockMe }) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const ACC = { broker_account_id: 'a1', broker: 'paper', account_label: 'Desk', is_paper: true, status: 'active' }
const POS = { broker_account_id: 'a1', symbol: 'AAPL', option_type: null, strike: null, expiry: null, qty: 10, avg_entry_price: '150.00' }
const ORD = { order_id: 'o1', symbol: 'AAPL', side: 'BUY', qty: 10, order_type: 'market', status: 'filled', broker_order_id: null, reject_reason_code: null, created_at: '2026-06-04T10:00:00Z' }

describe('Dashboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockMe = { user: { email: 'a@b.com' }, tier: 'pro', entitlements: { ml_forecast: true, vol_surface: true } }
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [ACC] as never })
    vi.spyOn(oms, 'listPositions').mockResolvedValue({ positions: [POS] as never })
    vi.spyOn(oms, 'listOrders').mockResolvedValue({ orders: [ORD] as never, next_cursor: null })
  })

  it('gates the watchlist and snapshot for a free user without fetching gated data', async () => {
    mockMe = { user: { email: 'free@b.com' }, tier: 'free', entitlements: { ml_forecast: false, vol_surface: false } }
    const fc = vi.spyOn(models, 'getVolForecast')
    const iv = vi.spyOn(market, 'getIvSurface')
    render(wrap(<Dashboard />))
    await waitFor(() => expect(screen.getByTestId('portfolio-overview')).toBeInTheDocument())
    expect(screen.getAllByTestId('upgrade-hint').length).toBeGreaterThan(0)
    expect(fc).not.toHaveBeenCalled()
    expect(iv).not.toHaveBeenCalled()
  })

  it('shows a watchlist row with forecast + sentiment for an entitled user', async () => {
    vi.spyOn(models, 'getVolForecast').mockResolvedValue({
      horizon_days: 10, primary_model: 'garch', primary_forecast: [20, 22], primary_ci_95: null,
      alternative_models: [], validation: { holdout_days: 40, garch_mae: 0.5, hv21_mae: 0.6, lift: 0.1 },
      model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true, params: { omega: 0.0001, alpha: 0.08, beta: 0.9 },
    })
    vi.spyOn(models, 'getSentiment').mockResolvedValue({
      ticker: 'AAPL', market: 'US', score: 0.4, label: 'bullish', confident: true, n_headlines: 5,
      has_data: true, computed_at: '2026-06-04T10:00:00Z', as_of: '2026-06-04T00:00:00Z',
    })
    vi.spyOn(market, 'getIvSurface').mockResolvedValue({
      ticker: 'AAPL', market: 'US', as_of: 'x', spot: 150, data_provider: 'massive', model: 'bsm',
      risk_free_source: 'fred', freshness_ms: 0,
      expiries: [{ expiry: '2026-07-17', strikes: [{ strike: 150,
        calls: { price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv: 0.2 },
        puts: { price: 1, delta: -0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: -0.05, iv: 0.22 } }] }],
    } as never)
    render(wrap(<Dashboard />))
    await waitFor(() => expect(screen.getByTestId('watch-AAPL')).toBeInTheDocument())
    expect(screen.getByTestId('watch-AAPL').textContent).toContain('21.0%')
    expect(screen.getByTestId('watch-AAPL').textContent).toContain('bullish')
  })
})
```

- [ ] **Step 2: run → FAIL** — `cd apps/web && npx vitest run src/pages/Dashboard.test.tsx`

- [ ] **Step 3: create** `apps/web/src/pages/Dashboard.tsx`:

```typescript
import { useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { useBrokerAccounts, usePositions, useOrders } from '../features/portfolio/hooks'
import { useIvSurface } from '../features/markets/hooks'
import { getVolForecast, getSentiment } from '../lib/models'
import { StatStrip } from '../features/dashboard/StatStrip'
import { PortfolioOverview } from '../features/dashboard/PortfolioOverview'
import { WatchlistTable, type WatchRow } from '../features/dashboard/WatchlistTable'
import { MarketSnapshot } from '../features/dashboard/MarketSnapshot'

const WATCH_CAP = 5
const CANCELLABLE = new Set(['pending', 'submitted'])

export function Dashboard() {
  const { me } = useAuth()
  const volEntitled = me?.entitlements?.vol_surface === true
  const mlEntitled = me?.entitlements?.ml_forecast === true

  const accountsQ = useBrokerAccounts()
  const accounts = accountsQ.data?.broker_accounts ?? []
  const firstAccount = accounts[0]?.broker_account_id ?? ''
  const positionsQ = usePositions(firstAccount)
  const positions = positionsQ.data?.positions ?? []
  const ordersQ = useOrders()
  const orders = ordersQ.data?.pages[0]?.orders ?? []

  const [extraSymbols, setExtraSymbols] = useState<string[]>([])
  const symbols = Array.from(new Set([...positions.map((p) => p.symbol), ...extraSymbols])).slice(0, WATCH_CAP)

  const forecasts = useQueries({
    queries: symbols.map((s) => ({
      queryKey: ['vol-forecast', s, 10],
      queryFn: () => getVolForecast(s, 10),
      enabled: mlEntitled && !!s,
      retry: false,
    })),
  })
  const sentiments = useQueries({
    queries: symbols.map((s) => ({
      queryKey: ['sentiment', s],
      queryFn: () => getSentiment(s),
      enabled: mlEntitled && !!s,
      retry: false,
    })),
  })

  const rows: WatchRow[] = symbols.map((s, i) => {
    const fc = forecasts[i]
    const sent = sentiments[i]
    const arr = fc?.data?.primary_forecast
    const forecastPct = arr && arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null
    const sentimentLabel = sent?.data?.has_data ? sent.data.label : null
    return { symbol: s, forecastPct, sentimentLabel, loading: !!(fc?.isLoading || sent?.isLoading) }
  })

  const primary = symbols[0] ?? ''
  const surfaceQ = useIvSurface(volEntitled ? primary : '')

  const workingOrders = orders.filter((o) => CANCELLABLE.has(o.status)).length

  function addSymbol(s: string) {
    setExtraSymbols((prev) => (prev.includes(s) ? prev : [...prev, s]))
  }

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Dashboard</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Overview</h2>
      </div>

      <StatStrip
        email={me?.user.email ?? ""}
        tier={me?.tier ?? "free"}
        accounts={accounts.length}
        positions={positions.length}
        workingOrders={workingOrders}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <PortfolioOverview orders={orders.slice(0, 5)} />
        <MarketSnapshot symbol={primary} surface={surfaceQ.data ?? null} entitled={volEntitled} loading={surfaceQ.isLoading} />
      </div>

      <WatchlistTable rows={rows} entitled={mlEntitled} onAddSymbol={addSymbol} />
    </div>
  )
}
```

- [ ] **Step 4: run → 2 passed** — `cd apps/web && npx vitest run src/pages/Dashboard.test.tsx`. (Forecast mean (20+22)/2 = 21.0%.)

- [ ] **Step 5: swap the route + retire PlaceholderPage.** In `apps/web/src/app/Router.tsx`:
  - Add `import { Dashboard } from '../pages/Dashboard'` near the other page imports.
  - Replace `<Route index element={<PlaceholderPage title="Dashboard" />} />` with `<Route index element={<Dashboard />} />`.
  - Remove the now-unused `import { PlaceholderPage } from '../components/PlaceholderPage'` line (this index route was its last consumer — leaving the import causes a lint `no-unused-vars` error).
  - Run `cd apps/web && npx grep-or-rg`: check whether `PlaceholderPage` is referenced anywhere else, e.g. with Grep for `PlaceholderPage` across `apps/web/src`. If the ONLY remaining matches are the component's own definition file (`components/PlaceholderPage.tsx`), delete that file too (`git rm apps/web/src/components/PlaceholderPage.tsx`). If any other file (including a test) imports it, leave the file and only drop the Router import.

- [ ] **Step 6: full gate** — from `apps/web`:

```bash
npm run typecheck && npm run lint && npm run test:run
```

Expected: typecheck + lint clean; full suite green (~247 + ~13 new = ~260 tests). Then `npm run build` → still "17 HTML documents pre-rendered" (the `/app` index is client-only). Report the exact final test count and confirm the 17-doc build.

- [ ] **Step 7: commit**

```bash
git add apps/web/src/pages/Dashboard.tsx apps/web/src/pages/Dashboard.test.tsx apps/web/src/app/Router.tsx
# include the deletion if you removed it:
git add -A apps/web/src/components/PlaceholderPage.tsx
git commit -m "feat(web): Dashboard page (overview + watchlist + snapshot) + route, retire PlaceholderPage

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes (for the executor)

- **No early return before hooks:** the `Dashboard` never gates itself — every hook (`useAuth`,
  `useBrokerAccounts`, `usePositions`, `useOrders`, `useState`, `useQueries` ×2, `useIvSurface`)
  is called unconditionally at the top. `useQueries` legitimately takes a variable-length array,
  so the watchlist fan-out does not violate Rules of Hooks even as `symbols` grows.
- **Entitlement pre-check:** watchlist `useQueries` use `enabled: mlEntitled && !!s`, and the
  snapshot uses `useIvSurface(volEntitled ? primary : '')` — a free user fetches nothing gated
  (the gate test asserts `getVolForecast`/`getIvSurface` are never called).
- **Auth mock:** copy the `let mockMe` + `vi.mock('../auth/AuthContext', …)` pattern (note `me`
  needs `user.email`, `tier`, and `entitlements`).
- **Reuse, don't duplicate:** import the portfolio hooks from `../features/portfolio/hooks` and
  `useIvSurface` from `../features/markets/hooks`; do NOT create a new client.
- **Decimal/strings:** OMS `avg_entry_price`/`strike` are strings (the overview shows `qty` and
  `status`, no math); the models/market numbers are real JSON numbers.
```
