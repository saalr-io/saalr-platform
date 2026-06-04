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
