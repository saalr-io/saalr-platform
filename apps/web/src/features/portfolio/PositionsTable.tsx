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
                      <button data-testid="close-yes" onClick={() => onCloseConfirm(p)} disabled={closing}
                        className="rounded border border-neg/40 px-2 py-0.5 text-[11px] text-neg hover:bg-neg/10 disabled:opacity-40">Yes</button>
                      <button data-testid="close-no" onClick={onCloseCancel} disabled={closing}
                        className="rounded border border-line px-2 py-0.5 text-[11px] text-txtDim hover:text-txt disabled:opacity-40">No</button>
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
