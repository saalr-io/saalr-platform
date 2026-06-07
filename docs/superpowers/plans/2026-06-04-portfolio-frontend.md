# Portfolio Frontend (AN-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `Portfolio` placeholder with a paper-trading desk: select/create a paper account, see positions (with one-click confirmed close), place equity/option market/limit orders, and view/cancel orders.

**Architecture:** A `src/features/portfolio/` feature + `src/lib/oms.ts` client over the OMS endpoints. Pure presentational components (AccountBar, PositionsTable, OrderTicket, OrdersList) + a `Portfolio` page that owns all hooks/state. Orders use `useInfiniteQuery` (cursor). No entitlement gate. Client-only `/app` route (no SSG impact).

**Tech Stack:** React 18 + TS (strict), Tailwind (theme tokens only), TanStack Query, react-router 6, Vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-06-04-portfolio-frontend-design.md`

**Conventions:** from `apps/web`: tests `npx vitest run <files>`; gate `npm run typecheck && npm run lint && npm run test:run`. Commit footer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. NEVER touch root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`. Theme tokens only (`accent/canvas/txt/txtDim/txtFaint/line/lineSoft/panel/panel2/pos/neg/warn`); no raw Tailwind colors; no inline `style={{}}`; double-quote JSX strings with apostrophes.

**Design refinement vs spec:** to keep components unit-testable, ALL sub-components are pure (props only); the **page** owns every hook and passes `onCreate`/`onSubmit`/`onCancel`/close handlers down. `OrderTicket.onSubmit(draft, key)` emits `Omit<OrderCreate,'broker_account_id'>` + the idempotency key; the page adds `broker_account_id` and calls `placeOrder`.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/web/src/lib/oms.ts` (create) | OMS client + types |
| `apps/web/src/features/portfolio/AccountBar.tsx` (create) | account select + create paper account |
| `apps/web/src/features/portfolio/PositionsTable.tsx` (create) | positions + inline-confirm close |
| `apps/web/src/features/portfolio/OrderTicket.tsx` (create) | equity/option market/limit ticket |
| `apps/web/src/features/portfolio/OrdersList.tsx` (create) | orders + cancel + load more |
| `apps/web/src/features/portfolio/hooks.ts` (create) | OMS query/mutation hooks |
| `apps/web/src/pages/Portfolio.tsx` (create) | the `/app/portfolio` page |
| `apps/web/src/app/Router.tsx` (modify) | swap placeholder → `<Portfolio/>` |
| `+ *.test.ts(x)` | tests |

---

## Task 1: `lib/oms.ts` client + types

**Files:** Create `apps/web/src/lib/oms.ts`, `apps/web/src/lib/oms.test.ts`.

- [ ] **Step 1: Write the failing tests.** Create `apps/web/src/lib/oms.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { listBrokerAccounts, createBrokerAccount, listPositions, listOrders, placeOrder, cancelOrder } from './oms'

describe('oms client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('listBrokerAccounts GETs /v1/broker-accounts', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ broker_accounts: [] }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await listBrokerAccounts()
    expect(String(f.mock.calls[0][0])).toContain('/v1/broker-accounts')
  })

  it('createBrokerAccount POSTs a paper account', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ broker_account_id: 'a1' }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await createBrokerAccount('My desk')
    const init = f.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ broker: 'paper', account_label: 'My desk', is_paper: true })
  })

  it('listPositions passes the account id', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ positions: [] }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await listPositions('a1')
    expect(String(f.mock.calls[0][0])).toContain('/v1/positions?broker_account_id=a1')
  })

  it('listOrders adds a cursor when given', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ orders: [], next_cursor: null }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await listOrders('CUR')
    expect(String(f.mock.calls[0][0])).toContain('cursor=CUR')
  })

  it('placeOrder POSTs with the Idempotency-Key header and body', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ order_id: 'o1', status: 'submitted' }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await placeOrder({ broker_account_id: 'a1', symbol: 'SPY', side: 'BUY', qty: 1, order_type: 'market' }, 'KEY-1')
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(String(url)).toContain('/v1/orders')
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('KEY-1')
    expect(JSON.parse(init.body as string).symbol).toBe('SPY')
  })

  it('cancelOrder POSTs to the cancel path', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ order_id: 'o1', status: 'cancelled' }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await cancelOrder('o1')
    expect(String(f.mock.calls[0][0])).toContain('/v1/orders/o1/cancel')
  })

  it('a 422 throws Error with the RISK code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: { error: { code: 'RISK_INSUFFICIENT_BUYING_POWER' } } }), { status: 422 })))
    await expect(placeOrder({ broker_account_id: 'a1', symbol: 'SPY', side: 'BUY', qty: 1, order_type: 'market' }, 'K'))
      .rejects.toThrow('RISK_INSUFFICIENT_BUYING_POWER')
  })
})
```

- [ ] **Step 2: Run to verify failure.** From `apps/web`: `npx vitest run src/lib/oms.test.ts` → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/lib/oms.ts`:

```typescript
import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError } from './strategies'

export { EntitlementError }

export interface BrokerAccount {
  broker_account_id: string
  broker: string
  account_label: string
  is_paper: boolean
  status: string
}

export interface Position {
  broker_account_id: string
  symbol: string
  option_type: 'CALL' | 'PUT' | null
  strike: string | null
  expiry: string | null
  qty: number
  avg_entry_price: string
}

export interface Order {
  order_id: string
  symbol: string
  side: string
  qty: number
  order_type: string
  status: string
  broker_order_id: string | null
  reject_reason_code: string | null
  created_at: string
}

export interface OrderResult {
  order_id: string
  broker_order_id: string | null
  status: string
  submitted_at: string
}

export interface OrderCreate {
  broker_account_id: string
  symbol: string
  side: 'BUY' | 'SELL'
  qty: number
  order_type: 'market' | 'limit'
  option_type?: 'CALL' | 'PUT'
  strike?: number
  expiry?: string
  limit_price?: number
  time_in_force?: 'day'
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

export function listBrokerAccounts(): Promise<{ broker_accounts: BrokerAccount[] }> {
  return request('/v1/broker-accounts')
}

export function createBrokerAccount(label: string): Promise<BrokerAccount> {
  return request('/v1/broker-accounts', {
    method: 'POST',
    body: JSON.stringify({ broker: 'paper', account_label: label, is_paper: true }),
  })
}

export function listPositions(brokerAccountId: string): Promise<{ positions: Position[] }> {
  return request(`/v1/positions?broker_account_id=${encodeURIComponent(brokerAccountId)}`)
}

export function listOrders(cursor?: string): Promise<{ orders: Order[]; next_cursor: string | null }> {
  return request(`/v1/orders?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`)
}

export function placeOrder(body: OrderCreate, idempotencyKey: string): Promise<OrderResult> {
  return request('/v1/orders', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function cancelOrder(orderId: string): Promise<OrderResult> {
  return request(`/v1/orders/${encodeURIComponent(orderId)}/cancel`, { method: 'POST' })
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/lib/oms.test.ts` → 7 passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/lib/oms.ts apps/web/src/lib/oms.test.ts
git commit -m "feat(web): OMS client (accounts, positions, orders)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: AccountBar

**Files:** Create `apps/web/src/features/portfolio/AccountBar.tsx`, `apps/web/src/features/portfolio/AccountBar.test.tsx`.

Pure component. Props: `{ accounts: BrokerAccount[]; selected: string; onSelect(id): void; onCreate(label): void; creating: boolean }`.

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/features/portfolio/AccountBar.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AccountBar } from './AccountBar'
import type { BrokerAccount } from '../../lib/oms'

const A = (id: string, label: string): BrokerAccount => ({
  broker_account_id: id, broker: 'paper', account_label: label, is_paper: true, status: 'active',
})

describe('AccountBar', () => {
  it('lists accounts and selects one', () => {
    const onSelect = vi.fn()
    render(<AccountBar accounts={[A('a1', 'Desk 1'), A('a2', 'Desk 2')]} selected="a1" onSelect={onSelect} onCreate={vi.fn()} creating={false} />)
    fireEvent.change(screen.getByTestId('account-select'), { target: { value: 'a2' } })
    expect(onSelect).toHaveBeenCalledWith('a2')
  })

  it('creates a paper account from the label input', () => {
    const onCreate = vi.fn()
    render(<AccountBar accounts={[A('a1', 'Desk 1')]} selected="a1" onSelect={vi.fn()} onCreate={onCreate} creating={false} />)
    fireEvent.change(screen.getByTestId('new-account-input'), { target: { value: 'Scalps' } })
    fireEvent.click(screen.getByTestId('new-account-create'))
    expect(onCreate).toHaveBeenCalledWith('Scalps')
  })

  it('shows a prompt when there are no accounts', () => {
    render(<AccountBar accounts={[]} selected="" onSelect={vi.fn()} onCreate={vi.fn()} creating={false} />)
    expect(screen.getByTestId('no-accounts')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/features/portfolio/AccountBar.test.tsx` → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/features/portfolio/AccountBar.tsx`:

```typescript
import { useState } from 'react'
import type { BrokerAccount } from '../../lib/oms'

interface Props {
  accounts: BrokerAccount[]
  selected: string
  onSelect: (id: string) => void
  onCreate: (label: string) => void
  creating: boolean
}

function NewAccount({ onCreate, creating }: { onCreate: (label: string) => void; creating: boolean }) {
  const [label, setLabel] = useState('')
  function submit() {
    const l = label.trim()
    if (l) { onCreate(l); setLabel('') }
  }
  return (
    <div className="flex items-center gap-2">
      <input
        data-testid="new-account-input"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
        placeholder="New paper account"
        className="w-44 rounded-lg border border-line bg-canvas px-3 py-2 text-xs text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none"
      />
      <button
        data-testid="new-account-create"
        onClick={submit}
        disabled={creating || label.trim().length === 0}
        className="rounded-lg bg-accent/20 px-3 py-2 text-xs text-accent transition hover:bg-accent/30 disabled:opacity-40"
      >
        {creating ? "Creating…" : "Create"}
      </button>
    </div>
  )
}

export function AccountBar({ accounts, selected, onSelect, onCreate, creating }: Props) {
  if (accounts.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-line bg-panel/40 p-5" data-testid="no-accounts">
        <p className="text-sm text-txtDim">Create a paper account to start trading.</p>
        <div className="mt-3"><NewAccount onCreate={onCreate} creating={creating} /></div>
      </div>
    )
  }
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="font-mono text-[11px] uppercase tracking-wider text-txtFaint">Account</span>
      <select
        data-testid="account-select"
        value={selected}
        onChange={(e) => onSelect(e.target.value)}
        className="rounded-lg border border-line bg-panel px-3 py-2 text-xs text-txt"
      >
        {accounts.map((a) => (
          <option key={a.broker_account_id} value={a.broker_account_id}>
            {a.account_label} · {a.is_paper ? 'paper' : 'live'}
          </option>
        ))}
      </select>
      <span className="h-4 w-px bg-line" />
      <NewAccount onCreate={onCreate} creating={creating} />
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/features/portfolio/AccountBar.test.tsx` → 3 passed; `npm run lint` → clean.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/features/portfolio/AccountBar.tsx apps/web/src/features/portfolio/AccountBar.test.tsx
git commit -m "feat(web): portfolio AccountBar (select + create paper account)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: PositionsTable (inline-confirm close)

**Files:** Create `apps/web/src/features/portfolio/PositionsTable.tsx`, `apps/web/src/features/portfolio/PositionsTable.test.tsx`.

Pure component. Props: `{ positions, confirmingId, closingId, onCloseRequest(rowKey), onCloseConfirm(position), onCloseCancel() }`. `rowKey(p) = \`${p.symbol}|${p.option_type ?? ''}|${p.strike ?? ''}|${p.expiry ?? ''}\``. Export `rowKey` so the page reuses it.

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/features/portfolio/PositionsTable.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PositionsTable, rowKey } from './PositionsTable'
import type { Position } from '../../lib/oms'

const P = (over: Partial<Position> = {}): Position => ({
  broker_account_id: 'a1', symbol: 'AAPL', option_type: null, strike: null, expiry: null,
  qty: 10, avg_entry_price: '150.00', ...over,
})

describe('PositionsTable', () => {
  it('formats an option instrument', () => {
    render(<PositionsTable positions={[P({ option_type: 'CALL', strike: '150', expiry: '2026-12-18' })]}
      confirmingId={null} closingId={null} onCloseRequest={vi.fn()} onCloseConfirm={vi.fn()} onCloseCancel={vi.fn()} />)
    expect(screen.getByText(/AAPL \$150 CALL 2026-12-18/)).toBeInTheDocument()
  })

  it('first Close click requests confirm; Yes confirms', () => {
    const onReq = vi.fn(); const onConfirm = vi.fn()
    const pos = P()
    const key = rowKey(pos)
    const { rerender } = render(<PositionsTable positions={[pos]} confirmingId={null} closingId={null}
      onCloseRequest={onReq} onCloseConfirm={onConfirm} onCloseCancel={vi.fn()} />)
    fireEvent.click(screen.getByTestId('close-btn'))
    expect(onReq).toHaveBeenCalledWith(key)
    expect(onConfirm).not.toHaveBeenCalled()
    rerender(<PositionsTable positions={[pos]} confirmingId={key} closingId={null}
      onCloseRequest={onReq} onCloseConfirm={onConfirm} onCloseCancel={vi.fn()} />)
    fireEvent.click(screen.getByTestId('close-yes'))
    expect(onConfirm).toHaveBeenCalledWith(pos)
  })

  it('shows an empty state', () => {
    render(<PositionsTable positions={[]} confirmingId={null} closingId={null}
      onCloseRequest={vi.fn()} onCloseConfirm={vi.fn()} onCloseCancel={vi.fn()} />)
    expect(screen.getByTestId('positions-empty')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/features/portfolio/PositionsTable.test.tsx` → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/features/portfolio/PositionsTable.tsx`:

```typescript
import type { Position } from '../../lib/oms'

export function rowKey(p: Position): string {
  return `${p.symbol}|${p.option_type ?? ''}|${p.strike ?? ''}|${p.expiry ?? ''}`
}

function instrument(p: Position): string {
  if (p.option_type) return `${p.symbol} $${p.strike} ${p.option_type} ${p.expiry}`
  return p.symbol
}

interface Props {
  positions: Position[]
  confirmingId: string | null
  closingId: string | null
  onCloseRequest: (rowKey: string) => void
  onCloseConfirm: (p: Position) => void
  onCloseCancel: () => void
}

export function PositionsTable({ positions, confirmingId, closingId, onCloseRequest, onCloseConfirm, onCloseCancel }: Props) {
  if (positions.length === 0) {
    return <p className="py-6 text-center text-sm text-txtFaint" data-testid="positions-empty">No open positions.</p>
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="tnum w-full font-mono text-xs">
        <thead>
          <tr className="border-b border-line text-[10px] uppercase tracking-wider text-txtFaint">
            <th className="px-3 py-2 text-left">Instrument</th>
            <th className="px-3 py-2 text-right">Qty</th>
            <th className="px-3 py-2 text-right">Avg entry</th>
            <th className="px-3 py-2 text-right"></th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const key = rowKey(p)
            const confirming = confirmingId === key
            const closing = closingId === key
            return (
              <tr key={key} className="border-b border-lineSoft" data-testid={`position-${key}`}>
                <td className="px-3 py-2 text-txt">{instrument(p)}</td>
                <td className="px-3 py-2 text-right text-txtDim">{p.qty}</td>
                <td className="px-3 py-2 text-right text-txtDim">{p.avg_entry_price}</td>
                <td className="px-3 py-2 text-right">
                  {closing ? (
                    <span className="text-[11px] text-txtFaint">Closing…</span>
                  ) : confirming ? (
                    <span className="inline-flex items-center gap-2">
                      <span className="text-[11px] text-txtDim">Confirm?</span>
                      <button data-testid="close-yes" onClick={() => onCloseConfirm(p)}
                        className="rounded border border-neg/40 px-2 py-0.5 text-[11px] text-neg hover:bg-neg/10">Yes</button>
                      <button data-testid="close-no" onClick={onCloseCancel}
                        className="rounded border border-line px-2 py-0.5 text-[11px] text-txtDim hover:text-txt">No</button>
                    </span>
                  ) : (
                    <button data-testid="close-btn" onClick={() => onCloseRequest(key)}
                      className="rounded border border-line px-2 py-0.5 text-[11px] text-txtDim hover:border-neg hover:text-neg">Close</button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
```
NOTE: the test renders a single position so `data-testid="close-btn"`/`close-yes` are unique. (In the page, multiple rows each render their own — fine since only one row is ever in the `confirming` state.)

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/features/portfolio/PositionsTable.test.tsx` → 3 passed; `npm run lint` → clean.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/features/portfolio/PositionsTable.tsx apps/web/src/features/portfolio/PositionsTable.test.tsx
git commit -m "feat(web): portfolio PositionsTable with inline-confirm close

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: OrderTicket

**Files:** Create `apps/web/src/features/portfolio/OrderTicket.tsx`, `apps/web/src/features/portfolio/OrderTicket.test.tsx`.

Pure component. Props: `{ disabled, pending, error, lastResult, onSubmit }` where `onSubmit(draft: Omit<OrderCreate,'broker_account_id'>, key: string): void`.

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/features/portfolio/OrderTicket.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { OrderTicket } from './OrderTicket'

describe('OrderTicket', () => {
  it('submits an equity market order with a key', () => {
    const onSubmit = vi.fn()
    render(<OrderTicket disabled={false} pending={false} error={null} lastResult={null} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByTestId('ot-symbol'), { target: { value: 'SPY' } })
    fireEvent.change(screen.getByTestId('ot-qty'), { target: { value: '5' } })
    fireEvent.click(screen.getByTestId('ot-submit'))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    const [draft, key] = onSubmit.mock.calls[0]
    expect(draft).toMatchObject({ symbol: 'SPY', side: 'BUY', qty: 5, order_type: 'market' })
    expect(draft.option_type).toBeUndefined()
    expect(typeof key).toBe('string')
  })

  it('adds limit_price and option fields when enabled', () => {
    const onSubmit = vi.fn()
    render(<OrderTicket disabled={false} pending={false} error={null} lastResult={null} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByTestId('ot-symbol'), { target: { value: 'AAPL' } })
    fireEvent.change(screen.getByTestId('ot-qty'), { target: { value: '1' } })
    fireEvent.change(screen.getByTestId('ot-type'), { target: { value: 'limit' } })
    fireEvent.change(screen.getByTestId('ot-limit'), { target: { value: '12.5' } })
    fireEvent.click(screen.getByTestId('ot-options'))
    fireEvent.change(screen.getByTestId('ot-option-type'), { target: { value: 'CALL' } })
    fireEvent.change(screen.getByTestId('ot-strike'), { target: { value: '150' } })
    fireEvent.change(screen.getByTestId('ot-expiry'), { target: { value: '2026-12-18' } })
    fireEvent.click(screen.getByTestId('ot-submit'))
    const [draft] = onSubmit.mock.calls[0]
    expect(draft).toMatchObject({ order_type: 'limit', limit_price: 12.5, option_type: 'CALL', strike: 150, expiry: '2026-12-18' })
  })

  it('disables submit while pending', () => {
    render(<OrderTicket disabled={false} pending={true} error={null} lastResult={null} onSubmit={vi.fn()} />)
    expect(screen.getByTestId('ot-submit')).toBeDisabled()
  })

  it('shows an error message', () => {
    render(<OrderTicket disabled={false} pending={false} error="insufficient buying power" lastResult={null} onSubmit={vi.fn()} />)
    expect(screen.getByTestId('ot-error').textContent).toContain('insufficient buying power')
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/features/portfolio/OrderTicket.test.tsx` → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/features/portfolio/OrderTicket.tsx`:

```typescript
import { useState } from 'react'
import type { OrderCreate } from '../../lib/oms'

type Draft = Omit<OrderCreate, 'broker_account_id'>

interface Props {
  disabled: boolean
  pending: boolean
  error: string | null
  lastResult: string | null
  onSubmit: (draft: Draft, key: string) => void
}

const inputCls = 'rounded-lg border border-line bg-canvas px-3 py-2 text-xs text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none'

export function OrderTicket({ disabled, pending, error, lastResult, onSubmit }: Props) {
  const [symbol, setSymbol] = useState('')
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY')
  const [qty, setQty] = useState('')
  const [orderType, setOrderType] = useState<'market' | 'limit'>('market')
  const [limit, setLimit] = useState('')
  const [optionsOn, setOptionsOn] = useState(false)
  const [optionType, setOptionType] = useState<'CALL' | 'PUT'>('CALL')
  const [strike, setStrike] = useState('')
  const [expiry, setExpiry] = useState('')

  function submit() {
    const sym = symbol.trim().toUpperCase()
    const q = parseInt(qty, 10)
    if (!sym || !q) return
    const draft: Draft = { symbol: sym, side, qty: q, order_type: orderType, time_in_force: 'day' }
    if (orderType === 'limit') draft.limit_price = parseFloat(limit)
    if (optionsOn) {
      draft.option_type = optionType
      draft.strike = parseFloat(strike)
      draft.expiry = expiry
    }
    onSubmit(draft, crypto.randomUUID())
  }

  return (
    <div className="space-y-3 rounded-lg border border-line bg-panel p-4" data-testid="order-ticket">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">// Order ticket</p>

      <div className="flex gap-2">
        <input data-testid="ot-symbol" value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
          placeholder="Symbol" maxLength={8} className={`${inputCls} w-28 uppercase`} />
        <select data-testid="ot-side" value={side} onChange={(e) => setSide(e.target.value as 'BUY' | 'SELL')} className={inputCls}>
          <option value="BUY">Buy</option>
          <option value="SELL">Sell</option>
        </select>
        <input data-testid="ot-qty" value={qty} onChange={(e) => setQty(e.target.value.replace(/[^0-9]/g, ''))}
          placeholder="Qty" className={`${inputCls} w-20`} />
      </div>

      <div className="flex gap-2">
        <select data-testid="ot-type" value={orderType} onChange={(e) => setOrderType(e.target.value as 'market' | 'limit')} className={inputCls}>
          <option value="market">Market</option>
          <option value="limit">Limit</option>
        </select>
        {orderType === 'limit' && (
          <input data-testid="ot-limit" value={limit} onChange={(e) => setLimit(e.target.value)}
            placeholder="Limit price" className={`${inputCls} w-28`} />
        )}
      </div>

      <label className="flex items-center gap-2 text-xs text-txtDim">
        <input data-testid="ot-options" type="checkbox" checked={optionsOn} onChange={(e) => setOptionsOn(e.target.checked)} />
        Options leg
      </label>
      {optionsOn && (
        <div className="flex flex-wrap gap-2">
          <select data-testid="ot-option-type" value={optionType} onChange={(e) => setOptionType(e.target.value as 'CALL' | 'PUT')} className={inputCls}>
            <option value="CALL">Call</option>
            <option value="PUT">Put</option>
          </select>
          <input data-testid="ot-strike" value={strike} onChange={(e) => setStrike(e.target.value)} placeholder="Strike" className={`${inputCls} w-24`} />
          <input data-testid="ot-expiry" type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} className={inputCls} />
        </div>
      )}

      <button data-testid="ot-submit" onClick={submit} disabled={disabled || pending}
        className="w-full rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-40">
        {pending ? "Submitting…" : disabled ? "Select an account" : "Place order"}
      </button>

      {error && <p data-testid="ot-error" className="text-[11px] text-neg">Rejected: {error}</p>}
      {lastResult && !error && <p data-testid="ot-result" className="text-[11px] text-pos">{lastResult}</p>}
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/features/portfolio/OrderTicket.test.tsx` → 4 passed; `npm run lint` → clean.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/features/portfolio/OrderTicket.tsx apps/web/src/features/portfolio/OrderTicket.test.tsx
git commit -m "feat(web): portfolio OrderTicket (equity/option market+limit, per-submit key)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: OrdersList

**Files:** Create `apps/web/src/features/portfolio/OrdersList.tsx`, `apps/web/src/features/portfolio/OrdersList.test.tsx`.

Pure component. Props: `{ orders, cancellingId, hasMore, onCancel(order), onLoadMore() }`.

- [ ] **Step 1: Write the failing test.** Create `apps/web/src/features/portfolio/OrdersList.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { OrdersList } from './OrdersList'
import type { Order } from '../../lib/oms'

const O = (over: Partial<Order> = {}): Order => ({
  order_id: 'o1', symbol: 'SPY', side: 'BUY', qty: 1, order_type: 'market', status: 'submitted',
  broker_order_id: null, reject_reason_code: null, created_at: '2026-06-04T10:00:00Z', ...over,
})

describe('OrdersList', () => {
  it('cancels a submitted order', () => {
    const onCancel = vi.fn()
    render(<OrdersList orders={[O()]} cancellingId={null} hasMore={false} onCancel={onCancel} onLoadMore={vi.fn()} />)
    fireEvent.click(screen.getByTestId('cancel-o1'))
    expect(onCancel).toHaveBeenCalledWith(expect.objectContaining({ order_id: 'o1' }))
  })

  it('shows the reject reason on a rejected order and no cancel button', () => {
    render(<OrdersList orders={[O({ order_id: 'o2', status: 'rejected', reject_reason_code: 'RISK_INSUFFICIENT_BUYING_POWER' })]}
      cancellingId={null} hasMore={false} onCancel={vi.fn()} onLoadMore={vi.fn()} />)
    expect(screen.getByTestId('order-o2').textContent).toContain('RISK_INSUFFICIENT_BUYING_POWER')
    expect(screen.queryByTestId('cancel-o2')).toBeNull()
  })

  it('empty state when no orders', () => {
    render(<OrdersList orders={[]} cancellingId={null} hasMore={false} onCancel={vi.fn()} onLoadMore={vi.fn()} />)
    expect(screen.getByTestId('orders-empty')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure.** `npx vitest run src/features/portfolio/OrdersList.test.tsx` → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/features/portfolio/OrdersList.tsx`:

```typescript
import type { Order } from '../../lib/oms'

const CANCELLABLE = new Set(['pending', 'submitted'])

function statusClass(status: string): string {
  if (status === 'filled') return 'text-pos'
  if (status === 'rejected' || status === 'cancelled') return 'text-neg'
  return 'text-warn'
}

interface Props {
  orders: Order[]
  cancellingId: string | null
  hasMore: boolean
  onCancel: (o: Order) => void
  onLoadMore: () => void
}

export function OrdersList({ orders, cancellingId, hasMore, onCancel, onLoadMore }: Props) {
  if (orders.length === 0) {
    return <p className="py-6 text-center text-sm text-txtFaint" data-testid="orders-empty">No orders yet.</p>
  }
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="tnum w-full font-mono text-xs">
          <thead>
            <tr className="border-b border-line text-[10px] uppercase tracking-wider text-txtFaint">
              <th className="px-3 py-2 text-left">Symbol</th>
              <th className="px-3 py-2 text-left">Side</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-left">Time</th>
              <th className="px-3 py-2 text-right"></th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.order_id} className="border-b border-lineSoft" data-testid={`order-${o.order_id}`}>
                <td className="px-3 py-2 text-txt">{o.symbol}</td>
                <td className="px-3 py-2 text-txtDim">{o.side}</td>
                <td className="px-3 py-2 text-right text-txtDim">{o.qty}</td>
                <td className="px-3 py-2 text-txtDim">{o.order_type}</td>
                <td className={`px-3 py-2 ${statusClass(o.status)}`}>
                  {o.status}{o.reject_reason_code ? ` · ${o.reject_reason_code}` : ''}
                </td>
                <td className="px-3 py-2 text-txtFaint">{new Date(o.created_at).toLocaleTimeString()}</td>
                <td className="px-3 py-2 text-right">
                  {CANCELLABLE.has(o.status) && (
                    <button data-testid={`cancel-${o.order_id}`} onClick={() => onCancel(o)}
                      disabled={cancellingId === o.order_id}
                      className="rounded border border-line px-2 py-0.5 text-[11px] text-txtDim hover:border-neg hover:text-neg disabled:opacity-40">
                      {cancellingId === o.order_id ? "Cancelling…" : "Cancel"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <button data-testid="orders-load-more" onClick={onLoadMore}
          className="rounded-lg border border-line px-3 py-1.5 text-xs text-txtDim transition hover:text-txt">
          Load more
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run to verify pass.** `npx vitest run src/features/portfolio/OrdersList.test.tsx` → 3 passed; `npm run lint` → clean.

- [ ] **Step 5: Commit.**
```bash
git add apps/web/src/features/portfolio/OrdersList.tsx apps/web/src/features/portfolio/OrdersList.test.tsx
git commit -m "feat(web): portfolio OrdersList (status + cancel + load more)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: hooks + Portfolio page + route

**Files:** Create `apps/web/src/features/portfolio/hooks.ts`, `apps/web/src/pages/Portfolio.tsx`, `apps/web/src/pages/Portfolio.test.tsx`; Modify `apps/web/src/app/Router.tsx`.

- [ ] **Step 1: Implement the hooks.** Create `apps/web/src/features/portfolio/hooks.ts`:

```typescript
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  listBrokerAccounts, createBrokerAccount, listPositions, listOrders, placeOrder, cancelOrder,
  type OrderCreate,
} from '../../lib/oms'

export function useBrokerAccounts() {
  return useQuery({ queryKey: ['broker-accounts'], queryFn: listBrokerAccounts, retry: false })
}

export function useCreateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (label: string) => createBrokerAccount(label),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['broker-accounts'] }),
  })
}

export function usePositions(accountId: string) {
  return useQuery({
    queryKey: ['positions', accountId],
    queryFn: () => listPositions(accountId),
    enabled: !!accountId,
    retry: false,
  })
}

export function useOrders() {
  return useInfiniteQuery({
    queryKey: ['orders'],
    queryFn: ({ pageParam }) => listOrders(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    retry: false,
  })
}

export function usePlaceOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ body, key }: { body: OrderCreate; key: string }) => placeOrder(body, key),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['orders'] })
      void qc.invalidateQueries({ queryKey: ['positions'] })
    },
  })
}

export function useCancelOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (orderId: string) => cancelOrder(orderId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['orders'] }),
  })
}
```

- [ ] **Step 2: Write the failing page test.** Create `apps/web/src/pages/Portfolio.test.tsx`:

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as oms from '../lib/oms'
import { Portfolio } from './Portfolio'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const ACC = { broker_account_id: 'a1', broker: 'paper', account_label: 'Desk', is_paper: true, status: 'active' }
const POS = { broker_account_id: 'a1', symbol: 'AAPL', option_type: null, strike: null, expiry: null, qty: 10, avg_entry_price: '150.00' }

describe('Portfolio page', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('prompts to create an account when there are none', async () => {
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [] })
    vi.spyOn(oms, 'listOrders').mockResolvedValue({ orders: [], next_cursor: null })
    render(wrap(<Portfolio />))
    await waitFor(() => expect(screen.getByTestId('no-accounts')).toBeInTheDocument())
  })

  it('closing a position places an offsetting market order', async () => {
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [ACC] as never })
    vi.spyOn(oms, 'listPositions').mockResolvedValue({ positions: [POS] as never })
    vi.spyOn(oms, 'listOrders').mockResolvedValue({ orders: [], next_cursor: null })
    const place = vi.spyOn(oms, 'placeOrder').mockResolvedValue({ order_id: 'o9', broker_order_id: null, status: 'filled', submitted_at: 'x' })
    render(wrap(<Portfolio />))
    await waitFor(() => expect(screen.getByTestId('close-btn')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('close-btn'))     // request confirm
    fireEvent.click(screen.getByTestId('close-yes'))     // confirm
    await waitFor(() => expect(place).toHaveBeenCalled())
    const [body, key] = place.mock.calls[0]
    expect(body).toMatchObject({ broker_account_id: 'a1', symbol: 'AAPL', side: 'SELL', qty: 10, order_type: 'market' })
    expect(typeof key).toBe('string')
  })
})
```

- [ ] **Step 3: Run to verify failure.** `npx vitest run src/pages/Portfolio.test.tsx` → FAIL.

- [ ] **Step 4: Implement** `apps/web/src/pages/Portfolio.tsx`:

```typescript
import { useState } from 'react'
import { AccountBar } from '../features/portfolio/AccountBar'
import { PositionsTable, rowKey } from '../features/portfolio/PositionsTable'
import { OrderTicket } from '../features/portfolio/OrderTicket'
import { OrdersList } from '../features/portfolio/OrdersList'
import {
  useBrokerAccounts, useCreateAccount, usePositions, useOrders, usePlaceOrder, useCancelOrder,
} from '../features/portfolio/hooks'
import type { OrderCreate, Position } from '../lib/oms'

function humanize(code: string): string {
  if (code.startsWith('RISK_')) return code.slice(5).replace(/_/g, ' ').toLowerCase()
  return "couldn't place the order"
}

export function Portfolio() {
  const accountsQ = useBrokerAccounts()
  const createAccount = useCreateAccount()
  const accounts = accountsQ.data?.broker_accounts ?? []

  const [picked, setPicked] = useState<string | null>(null)
  const selected = picked ?? accounts[0]?.broker_account_id ?? ''

  const positionsQ = usePositions(selected)
  const ordersQ = useOrders()
  const place = usePlaceOrder()
  const cancel = useCancelOrder()

  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [closingId, setClosingId] = useState<string | null>(null)
  const [cancellingId, setCancellingId] = useState<string | null>(null)

  const orders = ordersQ.data?.pages.flatMap((p) => p.orders) ?? []

  function placeFromTicket(draft: Omit<OrderCreate, 'broker_account_id'>, key: string) {
    if (!selected) return
    place.mutate({ body: { ...draft, broker_account_id: selected }, key })
  }

  function closeConfirm(p: Position) {
    const key = rowKey(p)
    setClosingId(key)
    setConfirmingId(null)
    const body: OrderCreate = {
      broker_account_id: selected,
      symbol: p.symbol,
      side: p.qty >= 0 ? 'SELL' : 'BUY',
      qty: Math.abs(p.qty),
      order_type: 'market',
      time_in_force: 'day',
      ...(p.option_type
        ? { option_type: p.option_type, strike: Number(p.strike), expiry: p.expiry ?? undefined }
        : {}),
    }
    place.mutate(
      { body, key: crypto.randomUUID() },
      { onSettled: () => setClosingId(null) },
    )
  }

  function cancelOrder(orderId: string) {
    setCancellingId(orderId)
    cancel.mutate(orderId, { onSettled: () => setCancellingId(null) })
  }

  const placeError = place.error ? humanize((place.error as Error).message) : null
  const lastResult = place.data && !place.isError ? `Order ${place.data.status}` : null

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Portfolio</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Paper trading desk</h2>
      </div>

      <AccountBar
        accounts={accounts}
        selected={selected}
        onSelect={setPicked}
        onCreate={(label) => createAccount.mutate(label)}
        creating={createAccount.isPending}
      />

      {accounts.length > 0 && (
        <>
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <div>
              <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtFaint">Positions</p>
              <PositionsTable
                positions={positionsQ.data?.positions ?? []}
                confirmingId={confirmingId}
                closingId={closingId}
                onCloseRequest={setConfirmingId}
                onCloseConfirm={closeConfirm}
                onCloseCancel={() => setConfirmingId(null)}
              />
            </div>
            <OrderTicket
              disabled={!selected}
              pending={place.isPending}
              error={placeError}
              lastResult={lastResult}
              onSubmit={placeFromTicket}
            />
          </div>

          <div>
            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtFaint">Orders</p>
            <OrdersList
              orders={orders}
              cancellingId={cancellingId}
              hasMore={!!ordersQ.hasNextPage}
              onCancel={(o) => cancelOrder(o.order_id)}
              onLoadMore={() => void ordersQ.fetchNextPage()}
            />
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Wire the route.** In `apps/web/src/app/Router.tsx`: add `import { Portfolio } from '../pages/Portfolio'` and replace `<Route path="portfolio" element={<PlaceholderPage title="Portfolio" />} />` with `<Route path="portfolio" element={<Portfolio />} />`. (`PlaceholderPage` stays imported — still used by markets-was-replaced? no; it's used by models + dashboard, so keep it.)

- [ ] **Step 6: Run to verify pass.** `npx vitest run src/pages/Portfolio.test.tsx` → 2 passed. `npm run typecheck` → clean; `npm run lint` → clean. Then full suite `npm run test:run` — all green.

- [ ] **Step 7: Commit.**
```bash
git add apps/web/src/features/portfolio/hooks.ts apps/web/src/pages/Portfolio.tsx apps/web/src/pages/Portfolio.test.tsx apps/web/src/app/Router.tsx
git commit -m "feat(web): Portfolio page (accounts, positions, order ticket, orders)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Final gate

- [ ] **Step 1: Web gate.** From `apps/web`: `npm run typecheck` (clean), `npm run lint` (clean), `npm run test:run` (all pass — expect ~+22 portfolio tests on top of 204), `npm run build` (still prerenders 17 docs; `/app/portfolio` is client-only — no SSG change).
- [ ] **Step 2:** Confirm no raw-color/inline-style lint issues in the new files.

---

## Notes for the executor
- **Pure components + page owns hooks:** none of AccountBar/PositionsTable/OrderTicket/OrdersList call hooks or the client directly — the page wires everything. This keeps each component unit-testable with plain props.
- **`crypto.randomUUID()`** is available in jsdom (Node 18+) and the browser — used for per-submit idempotency keys (ticket) and per-close keys (page).
- **Close offsetting order:** side = `qty >= 0 ? 'SELL' : 'BUY'`, `qty = Math.abs(qty)`, market; option legs carried for option positions. `closingId` is the position `rowKey`, cleared on `onSettled`.
- **Orders use `useInfiniteQuery`:** the page flattens `data.pages`; "Load more" calls `fetchNextPage`; invalidating `['orders']` after a place/cancel refetches from the first page.
- **Error humanizing:** the `request()` wrapper throws `Error(code)`; the page maps a `RISK_*` code to a lowercase phrase, else a generic message.
- **Theme tokens only** for Tailwind classes; no raw colors; double-quote JSX strings with apostrophes (e.g. "Couldn't").
```
