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
        <UpgradeHint feature="Forecasts & sentiment for your holdings" />
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
