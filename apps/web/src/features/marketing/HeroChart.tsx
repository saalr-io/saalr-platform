import { PayoffChart } from '../strategies/PayoffChart'
import { EXPLAINERS } from '../../seo/content/strategies'
import { spotGrid, expirationCurve, breakevens, maxPL } from '../../seo/payoffExpiry'

// Authentic hero art: a real computed payoff curve from one of the strategy
// explainers (no mock data). Prefer a neutral, two-sided shape if available.
const DEMO = EXPLAINERS.find((e) => e.category === 'neutral') ?? EXPLAINERS[0]

export function HeroChart() {
  if (!DEMO) return null
  const grid = spotGrid(DEMO.legs)
  const curve = expirationCurve(DEMO.legs, grid)
  const be = breakevens(curve)
  const m = maxPL(curve)

  return (
    <figure className="overflow-hidden rounded-lg border border-line bg-panel/70 shadow-[0_28px_80px_-32px_rgba(0,0,0,0.9)]">
      <figcaption className="flex items-center gap-2 border-b border-line bg-panel2/60 px-3 py-2">
        <span aria-hidden className="flex gap-1.5">
          <span className="h-2 w-2 rounded-full bg-neg/70" />
          <span className="h-2 w-2 rounded-full bg-warn/70" />
          <span className="h-2 w-2 rounded-full bg-pos/70" />
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
          payoff · {DEMO.title}
        </span>
        <span className="ml-auto font-mono text-[10px] text-txtFaint">at expiry</span>
      </figcaption>
      <div className="p-3">
        <PayoffChart
          expirationCurve={curve.map((p) => ({ spot: p.spot, pnl: p.pnl }))}
          breakevens={be}
        />
        <dl className="mt-3 grid grid-cols-3 gap-2 font-mono text-[11px]">
          <div>
            <dt className="text-txtFaint">max profit</dt>
            <dd className="tnum text-pos">{m.unboundedProfit ? '∞' : m.maxProfit?.toFixed(0)}</dd>
          </div>
          <div>
            <dt className="text-txtFaint">max loss</dt>
            <dd className="tnum text-neg">{m.unboundedLoss ? '∞' : m.maxLoss?.toFixed(0)}</dd>
          </div>
          <div>
            <dt className="text-txtFaint">breakeven</dt>
            <dd className="tnum text-txt">{be.map((x) => x.toFixed(0)).join(' · ') || '—'}</dd>
          </div>
        </dl>
      </div>
    </figure>
  )
}
