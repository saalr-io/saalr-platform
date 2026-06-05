# Sensibull-style Option Chain UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `ChainTable.tsx` into a Sensibull-style option chain — compact columns with a Greeks toggle, ITM shading, OI bars, ATM-centered focus with a spot line, and a 10/20/All strike limiter.

**Architecture:** One self-contained React component. Props unchanged (`{ contracts, spot }`); all view state (column mode, strike window) is local. `Markets.tsx`, the hooks, the client, and the `Contract` type are untouched.

**Tech Stack:** React 18 + TS strict + Tailwind (theme tokens only) + Vitest + @testing-library/react. **pnpm/npm — NOT yarn.**

**Spec:** `docs/superpowers/specs/2026-06-05-sensibull-chain-ux-design.md`

**Conventions:** commit footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`; theme tokens only for Tailwind class colors (`text-pos`/`bg-pos`, `text-neg`/`bg-neg`, `bg-accent`, `text-txt/txtDim/txtFaint`, `border-line/lineSoft`, `bg-panel/panel2` are all valid); double-quote JSX strings; NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`; branch `feat/scaffold-data-layer`. Web: from `apps/web`, `npx vitest run <file>`; gate `npm run typecheck`/`npm run lint`.

**Reference — the `Contract` type (`apps/web/src/lib/market.ts`, unchanged):**
```ts
export interface Greeks { price: number; delta: number; gamma: number; theta: number; vega: number; rho: number; iv: number }
export interface Contract {
  expiry: string; strike: number; type: 'CALL' | 'PUT'
  bid: number; ask: number; last: number; volume: number; open_interest: number
  ours: Greeks; vendor: { iv: number; delta: number; gamma: number; theta: number; vega: number }
}
```

---

## File Structure

- **Modify (rewrite)** `apps/web/src/features/markets/ChainTable.tsx` — the Sensibull-style table. Keeps the existing `pivot` + `nearestStrike` helpers and the `chain-table` / `chain-row-{strike}` / `chain-empty` / `data-atm` testids; adds view state + the four visual cues.
- **Modify** `apps/web/src/features/markets/ChainTable.test.tsx` — update for the new structure + new assertions.

No other files change. `Markets.tsx` renders `<ChainTable contracts={chainQ.data.contracts} spot={surface.spot} />` exactly as before.

---

## Task 1: Rewrite ChainTable into the Sensibull-style chain

**Files:**
- Modify: `apps/web/src/features/markets/ChainTable.tsx`
- Test: `apps/web/src/features/markets/ChainTable.test.tsx`

- [ ] **Step 1: Replace the test** `apps/web/src/features/markets/ChainTable.test.tsx` with:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { ChainTable } from './ChainTable'
import type { Contract, Greeks } from '../../lib/market'

const G = (iv: number): Greeks => ({ price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv })
const C = (strike: number, type: 'CALL' | 'PUT', iv: number, oi = 99): Contract => ({
  expiry: '2026-12-18', strike, type, bid: 1, ask: 1.2, last: 1.1, volume: 10, open_interest: oi,
  ours: G(iv), vendor: { iv: iv - 0.001, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1 },
})

// a strike ladder straddling spot=101, with a call+put at each strike
function ladder(strikes: number[], spot: number) {
  const cs = strikes.flatMap((k) => [C(k, 'CALL', 0.2, k), C(k, 'PUT', 0.25, k)])
  return <ChainTable contracts={cs} spot={spot} />
}

describe('ChainTable', () => {
  it('pivots a call and a put at the same strike onto one row', () => {
    render(<ChainTable contracts={[C(100, 'CALL', 0.2), C(100, 'PUT', 0.25)]} spot={101} />)
    const row = screen.getByTestId('chain-row-100')
    expect(row.textContent).toContain('20.0%')
    expect(row.textContent).toContain('25.0%')
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

  it('tints the ITM side: calls below spot, puts above spot', () => {
    render(ladder([95, 100, 105], 101))
    // strike 95 < spot -> call side ITM
    expect(within(screen.getByTestId('chain-row-95')).getByTestId('call-cells-95')).toHaveAttribute('data-itm', 'true')
    expect(within(screen.getByTestId('chain-row-95')).getByTestId('put-cells-95')).not.toHaveAttribute('data-itm', 'true')
    // strike 105 > spot -> put side ITM
    expect(within(screen.getByTestId('chain-row-105')).getByTestId('put-cells-105')).toHaveAttribute('data-itm', 'true')
    expect(within(screen.getByTestId('chain-row-105')).getByTestId('call-cells-105')).not.toHaveAttribute('data-itm', 'true')
  })

  it('toggles between prices and greeks columns', () => {
    // headers are mirrored (calls + puts), so each label appears twice -> use *AllByText
    render(ladder([100, 101, 102], 101))
    expect(screen.getAllByText('OI').length).toBeGreaterThan(0)
    expect(screen.queryAllByText('Δ')).toHaveLength(0)
    fireEvent.click(screen.getByTestId('chain-greeks-toggle'))
    expect(screen.getAllByText('Δ').length).toBeGreaterThan(0)
    expect(screen.queryAllByText('OI')).toHaveLength(0)
  })

  it('limits to a window around ATM by default and expands on All', () => {
    const strikes = Array.from({ length: 41 }, (_, i) => 80 + i) // 80..120, ATM=101
    render(ladder(strikes, 101))
    // default window = 10 each side -> at most 21 strike rows
    expect(screen.queryByTestId('chain-row-80')).not.toBeInTheDocument()
    expect(screen.getByTestId('chain-row-101')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('chain-window-all'))
    expect(screen.getByTestId('chain-row-80')).toBeInTheDocument()
  })

  it('renders a spot line and an OI bar', () => {
    render(ladder([100, 101, 102], 101))
    expect(screen.getByTestId('chain-spot-line').textContent).toContain('101')
    expect(screen.getByTestId('oi-bar-call-101')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test, verify it fails**

Run (from `apps/web`): `npx vitest run src/features/markets/ChainTable.test.tsx`
Expected: FAIL (new testids `call-cells-*`, `chain-greeks-toggle`, `chain-window-all`, `chain-spot-line`, `oi-bar-*` don't exist yet).

- [ ] **Step 3: Rewrite** `apps/web/src/features/markets/ChainTable.tsx` with:

```tsx
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
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
const kfmt = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v))

type Mode = 'default' | 'greeks'
type Win = 10 | 20 | 'all'

// Column definitions per mode. `bar` flags the OI column for the inline magnitude bar.
interface ColDef { key: string; label: string; val: (c: Contract) => string; bar?: boolean }

const DEFAULT_COLS: ColDef[] = [
  { key: 'oi', label: 'OI', val: (c) => kfmt(c.open_interest), bar: true },
  { key: 'vol', label: 'Vol', val: (c) => kfmt(c.volume) },
  { key: 'iv', label: 'IV', val: (c) => pct(c.ours.iv) },
  { key: 'ltp', label: 'LTP', val: (c) => px(c.last) },
  { key: 'bid', label: 'Bid', val: (c) => px(c.bid) },
  { key: 'ask', label: 'Ask', val: (c) => px(c.ask) },
]
const GREEK_COLS: ColDef[] = [
  { key: 'd', label: 'Δ', val: (c) => g3(c.ours.delta) },
  { key: 'g', label: 'Γ', val: (c) => g3(c.ours.gamma) },
  { key: 't', label: 'Θ', val: (c) => g3(c.ours.theta) },
  { key: 'v', label: 'Vega', val: (c) => g3(c.ours.vega) },
]

function SideCells({
  c, cols, side, strike, itm, maxOi,
}: {
  c: Contract | undefined; cols: ColDef[]; side: 'call' | 'put'; strike: number; itm: boolean; maxOi: number
}) {
  // puts mirror calls: render columns reversed so bid/ask hug the strike
  const ordered = side === 'put' ? [...cols].reverse() : cols
  const tint = itm ? (side === 'call' ? 'bg-pos/[0.08]' : 'bg-neg/[0.08]') : ''
  return (
    <>
      {ordered.map((col) => {
        const showBar = col.bar && c
        return (
          <td
            key={col.key}
            data-testid={col.key === ordered[0].key ? `${side}-cells-${strike}` : undefined}
            data-itm={col.key === ordered[0].key && itm ? 'true' : undefined}
            className={`relative px-2 py-1 text-right text-txtDim ${tint}`}
          >
            {showBar && (
              <span
                data-testid={`oi-bar-${side}-${strike}`}
                aria-hidden
                className={`pointer-events-none absolute inset-y-[3px] right-0 rounded-sm ${side === 'call' ? 'bg-pos/20' : 'bg-neg/20'}`}
                style={{ width: `${Math.round((c!.open_interest / maxOi) * 100)}%` }}
              />
            )}
            <span className="relative">{c ? col.val(c) : '—'}</span>
          </td>
        )
      })}
    </>
  )
}

export function ChainTable({ contracts, spot }: { contracts: Contract[]; spot: number }) {
  const [mode, setMode] = useState<Mode>('default')
  const [win, setWin] = useState<Win>(10)
  const atmRef = useRef<HTMLTableRowElement | null>(null)

  const allRows = useMemo(() => pivot(contracts), [contracts])
  const atm = nearestStrike(allRows, spot)
  const maxOi = useMemo(
    () => Math.max(1, ...allRows.flatMap((r) => [r.call?.open_interest ?? 0, r.put?.open_interest ?? 0])),
    [allRows],
  )

  const rows = useMemo(() => {
    if (win === 'all' || atm === null) return allRows
    const atmIdx = allRows.findIndex((r) => r.strike === atm)
    return allRows.slice(Math.max(0, atmIdx - win), atmIdx + win + 1)
  }, [allRows, atm, win])

  useEffect(() => {
    atmRef.current?.scrollIntoView?.({ block: 'center' })
  }, [atm, win, mode, contracts])

  if (allRows.length === 0) {
    return <p className="py-8 text-center text-sm text-txtFaint" data-testid="chain-empty">No chain for this expiry.</p>
  }

  const cols = mode === 'greeks' ? GREEK_COLS : DEFAULT_COLS
  const span = cols.length
  // index of the first row at/above spot — the spot line goes just before it
  const spotIdx = rows.findIndex((r) => r.strike >= spot)

  return (
    <div className="space-y-2" data-testid="chain">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <div className="flex overflow-hidden rounded-md border border-line">
          {(['default', 'greeks'] as Mode[]).map((m) => (
            <button
              key={m}
              data-testid={m === 'greeks' ? 'chain-greeks-toggle' : 'chain-prices-toggle'}
              onClick={() => setMode(m)}
              className={`px-2.5 py-1 ${mode === m ? 'bg-accent/20 text-accent' : 'text-txtDim hover:text-txt'}`}
            >
              {m === 'greeks' ? 'Greeks' : 'Prices'}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1 text-txtFaint">
          <span className="font-mono text-[9px] uppercase tracking-wider">Strikes</span>
          {([10, 20, 'all'] as Win[]).map((w) => (
            <button
              key={String(w)}
              data-testid={`chain-window-${w}`}
              onClick={() => setWin(w)}
              className={`rounded px-2 py-0.5 ${win === w ? 'bg-panel text-txt' : 'text-txtDim hover:text-txt'}`}
            >
              {w === 'all' ? 'All' : `±${w}`}
            </button>
          ))}
        </div>
      </div>

      <div className="max-h-[70vh] overflow-auto rounded-lg border border-line">
        <table className="tnum w-full min-w-[680px] font-mono text-[11px]" data-testid="chain-table">
          <thead className="sticky top-0 z-10 bg-panel">
            <tr className="border-b border-line text-txtFaint">
              <th colSpan={span} className="px-2 py-1 text-left uppercase tracking-wider text-pos">Calls</th>
              <th className="px-2 py-1 text-center">Strike</th>
              <th colSpan={span} className="px-2 py-1 text-right uppercase tracking-wider text-neg">Puts</th>
            </tr>
            <tr className="border-b border-line text-[9px] text-txtFaint">
              {cols.map((c) => <th key={`ch-${c.key}`} className="px-2 py-1 text-right">{c.label}</th>)}
              <th className="px-2 py-1 text-center">·</th>
              {[...cols].reverse().map((c) => <th key={`ph-${c.key}`} className="px-2 py-1 text-right">{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const isAtm = r.strike === atm
              return (
                <Fragment key={r.strike}>
                  {i === spotIdx && spotIdx > 0 && (
                    <tr data-testid="chain-spot-line">
                      <td colSpan={span * 2 + 1} className="border-y border-accent/40 bg-accent/5 px-2 py-0.5 text-center text-[10px] text-accent">
                        spot {spot.toFixed(2)}
                      </td>
                    </tr>
                  )}
                  <tr
                    ref={isAtm ? atmRef : undefined}
                    data-testid={`chain-row-${r.strike}`}
                    data-atm={isAtm ? 'true' : undefined}
                    className={`border-b border-lineSoft ${isAtm ? 'bg-accent/10' : ''}`}
                  >
                    <SideCells c={r.call} cols={cols} side="call" strike={r.strike} itm={r.strike < spot} maxOi={maxOi} />
                    <td className="px-2 py-1 text-center font-semibold text-txt">{r.strike}</td>
                    <SideCells c={r.put} cols={cols} side="put" strike={r.strike} itm={r.strike > spot} maxOi={maxOi} />
                  </tr>
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run the test, verify it passes**

Run (from `apps/web`): `npx vitest run src/features/markets/ChainTable.test.tsx`
Expected: PASS (7 tests).

Notes if something fails:
- The `oi-bar-{side}-{strike}` testid is emitted only on the OI column and only when a contract exists; the test's ladder gives every strike a call with OI, so `oi-bar-call-101` is present.
- The ITM side-cell testid (`call-cells-{strike}` / `put-cells-{strike}`) is attached to the FIRST rendered column of each side. For calls that's `OI`; for puts (reversed) that's `Ask`. The `data-itm` attribute sits on that same first cell. The test asserts presence/absence of `data-itm`, which is correct regardless of which column is first.
- Mirrored headers mean each label (`OI`, `Δ`, …) appears twice, so the toggle test uses `getAllByText`/`queryAllByText`, not `getByText`.

- [ ] **Step 5: Typecheck + lint**

Run (from `apps/web`): `npm run typecheck` then `npm run lint`.
Expected: both clean. The `data-testid`/`data-itm` ternaries returning `undefined` are valid React (an `undefined` attribute is omitted) — no change needed.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/features/markets/ChainTable.tsx apps/web/src/features/markets/ChainTable.test.tsx
git commit -m "feat(web): Sensibull-style option chain — compact cols + greeks toggle, ITM shading, OI bars, ATM center, strike limiter

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Final gate

- [ ] **Step 1: Web suite** — from `apps/web`: `npm run typecheck && npm run lint && npm run test:run` → green (the only changed component is `ChainTable`; `Markets.tsx` and its tests are unaffected). `npm run build` → still "47 HTML documents pre-rendered" (`/app/markets` is client-only).
- [ ] **Step 2 (optional, local stack running): visual check** — open `http://localhost:5173/app/markets`, load `SPY` (premium login), switch to the Chain tab: confirm the compact columns, ATM-centered window with the spot line, ITM shading on the correct sides, OI bars, the Greeks toggle, and the ±10/±20/All limiter.

---

## Self-Review notes (for the executor)

- **Only `ChainTable.tsx` + its test change.** `Markets.tsx` passes `contracts` + `spot` exactly as before; do not touch it.
- **Moneyness:** a call is ITM when `strike < spot`; a put is ITM when `strike > spot`. The `itm` prop is computed per side accordingly.
- **Puts mirror calls:** the puts column order is the reversed `cols`, so Bid/Ask sit next to the strike on both sides.
- **OI bar width** uses `maxOi` (guarded to `>= 1`) across the whole expiry so bar lengths are comparable as the window expands.
- **scrollIntoView is optional-chained** (`?.scrollIntoView?.(...)`) — jsdom doesn't implement it, so this keeps tests from throwing.
- **Keyed Fragment** (Step 5) is the canonical fix for a `.map` that renders the optional spot-line row plus the strike row; don't use `<>` there.
- **Strike limiter** slices `allRows` by ATM index ± window; `All` shows the full ±15% band the backend returned.
