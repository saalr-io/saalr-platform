import type { MonteCarloResult } from '../../lib/models'

const W = 360
const H = 160
const PAD = 8
const BASELINE = 20

export function MonteCarloPanel({ result }: { result: MonteCarloResult }) {
  const { counts, bin_edges } = result.histogram
  const maxC = Math.max(1, ...counts)
  const x0 = bin_edges[0]
  const x1 = bin_edges[bin_edges.length - 1]
  const span = x1 - x0 || 1
  const sx = (v: number) => PAD + (W - 2 * PAD) * ((v - x0) / span)
  const zeroX = sx(0)

  return (
    <div className="space-y-4 rounded-lg border border-line bg-panel p-4" data-testid="mc-panel">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
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
        {counts.map((c, i) => {
          const bx0 = sx(bin_edges[i])
          const bx1 = sx(bin_edges[i + 1])
          const h = (H - BASELINE) * (c / maxC)
          const mid = (bin_edges[i] + bin_edges[i + 1]) / 2
          return (
            <rect key={i} data-testid="mc-bar" x={bx0} y={H - BASELINE - h}
              width={Math.max(0.5, bx1 - bx0 - 0.5)} height={h} fill={mid >= 0 ? "#37c98b" : "#ff5d73"} />
          )
        })}
        <line x1={zeroX} y1={0} x2={zeroX} y2={H - BASELINE} stroke="#5b6472" strokeWidth={1} strokeDasharray="3 3" />
      </svg>

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
