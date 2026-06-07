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
