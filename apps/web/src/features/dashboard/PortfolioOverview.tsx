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
