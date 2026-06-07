import type { MonteCarloResult } from '../../lib/models'
import { InfoHint } from '../../components/InfoHint'
import { hintProps } from '../../content/helpHints'

const W = 360
const H = 184
// room on the left for the frequency axis and on the bottom for the P&L axis
const PAD = { l: 30, r: 10, t: 14, b: 28 }

const usd = (v: number) => {
  const a = Math.abs(v)
  const sign = v < 0 ? '−' : v > 0 ? '+' : ''
  return a >= 1000 ? `${sign}$${(a / 1000).toFixed(1)}k` : `${sign}$${Math.round(a)}`
}

export function MonteCarloPanel({ result }: { result: MonteCarloResult }) {
  const { counts, bin_edges } = result.histogram
  const maxC = Math.max(1, ...counts)
  const x0 = bin_edges[0]
  const x1 = bin_edges[bin_edges.length - 1]
  const span = x1 - x0 || 1
  const sx = (v: number) => PAD.l + (W - PAD.l - PAD.r) * ((v - x0) / span)
  const baseY = H - PAD.b
  const zeroX = sx(0)
  const hasBars = counts.length > 0
  const xTicks = hasBars ? (x0 < 0 && x1 > 0 ? [x0, 0, x1] : [x0, x1]) : []

  return (
    <div className="space-y-3 rounded-lg border border-line bg-panel p-4" data-testid="mc-panel">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <span className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">Simulation <InfoHint {...hintProps('monte-carlo')} /></span>
        <div>
          <span className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">POP</span>{" "}
          <span data-testid="mc-pop" className="tnum text-lg font-semibold text-txt">{(result.pop * 100).toFixed(1)}%</span>
        </div>
        <div>
          <span className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">EV</span>{" "}
          <span data-testid="mc-ev" className={`tnum text-lg font-semibold ${result.ev >= 0 ? "text-pos" : "text-neg"}`}>{result.ev.toFixed(2)}</span>
        </div>
        <span data-testid="mc-sigma-source" className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-txtDim">σ {result.sigma_source}</span>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="mc-histogram">
        <g fontFamily="monospace" fontSize={8.5}>
          <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={baseY} stroke="#2c3340" strokeWidth={1} />
          <line x1={PAD.l} y1={baseY} x2={W - PAD.r} y2={baseY} stroke="#2c3340" strokeWidth={1} />
          {xTicks.map((v, i) => {
            const x = sx(v)
            const anchor = v === x0 ? 'start' : v === x1 ? 'end' : 'middle'
            const fill = v < 0 ? '#ff5d73' : v > 0 ? '#37c98b' : '#9aa4b2'
            return (
              <g key={i}>
                <line x1={x} y1={baseY} x2={x} y2={baseY + 3} stroke="#2c3340" strokeWidth={1} />
                <text x={x} y={baseY + 13} textAnchor={anchor} fill={fill}>{usd(v)}</text>
              </g>
            )
          })}
          <text x={(PAD.l + W - PAD.r) / 2} y={H - 1} textAnchor="middle" fill="#5b6472">P&amp;L at expiry</text>
          <text x={2} y={PAD.t - 4} textAnchor="start" fill="#5b6472">paths</text>
        </g>
        {counts.map((c, i) => {
          const bx0 = sx(bin_edges[i])
          const bx1 = sx(bin_edges[i + 1])
          const h = (H - PAD.t - PAD.b) * (c / maxC)
          const mid = (bin_edges[i] + bin_edges[i + 1]) / 2
          return (
            <rect key={i} data-testid="mc-bar" x={bx0} y={baseY - h}
              width={Math.max(0.5, bx1 - bx0 - 0.5)} height={h} fill={mid >= 0 ? "#37c98b" : "#ff5d73"} />
          )
        })}
        {hasBars && <line x1={zeroX} y1={PAD.t} x2={zeroX} y2={baseY} stroke="#5b6472" strokeWidth={1} strokeDasharray="3 3" />}
      </svg>

      <p className="text-[11px] leading-snug text-txtFaint" data-testid="mc-explainer">
        Each bar is how often the simulated P&amp;L landed in that range across {result.paths.toLocaleString()} paths.
        A capped-risk spread piles up at its max loss (left, red) and max profit (right, green), so you usually see two tall bars.
      </p>

      <dl className="grid grid-cols-3 gap-2 font-mono text-[11px] text-txtDim">
        <div className="flex justify-between"><dt>p5</dt><dd className="tnum">{result.percentiles.p5.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>p50</dt><dd className="tnum">{result.percentiles.p50.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>p95</dt><dd className="tnum">{result.percentiles.p95.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>max +</dt><dd className="tnum text-pos">{result.max_profit_observed.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>max −</dt><dd className="tnum text-neg">{result.max_loss_observed.toFixed(0)}</dd></div>
        <div className="flex justify-between"><dt>spot</dt><dd className="tnum">{result.spot.toFixed(2)}</dd></div>
      </dl>

      <p className="text-[11px] text-txtFaint" data-testid="mc-sentiment">
        {result.sentiment.applied
          ? `sentiment applied · ${result.sentiment.label} (${result.sentiment.score?.toFixed(2)})`
          : `sentiment: ${result.sentiment.reason ?? "not applied"}`}
        {" · "}{result.horizon_days}d · rate {(result.rate * 100).toFixed(2)}%
      </p>
    </div>
  )
}
