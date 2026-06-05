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
  { key: 'iv', label: 'IV', val: (c) => (Number.isFinite(c.ours.iv) ? pct(c.ours.iv) : '—') },
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
