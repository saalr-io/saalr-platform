import type { EquityPoint } from '../../lib/backtests'

const W = 520
const H = 220
const PAD = 8

function scaler(min: number, max: number, lo: number, hi: number) {
  const span = max - min || 1
  return (v: number) => lo + (hi - lo) * ((v - min) / span)
}

export function EquityCurve({ series, initialCapital }: { series: EquityPoint[]; initialCapital: number }) {
  const eq = series.map((p) => p.equity)
  const n = eq.length
  const ys = [...eq, initialCapital]
  const sx = scaler(0, Math.max(1, n - 1), PAD, W - PAD)
  const sy = scaler(Math.min(...ys), Math.max(...ys), H - PAD, PAD)
  const pts = series.map((p, i) => `${sx(i).toFixed(1)},${sy(p.equity).toFixed(1)}`).join(' ')
  const baseY = sy(initialCapital)
  const last = eq[n - 1] ?? initialCapital
  const up = last >= initialCapital
  return (
    <figure className="rounded-lg border border-line bg-panel p-4" data-testid="equity-curve">
      <figcaption className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Equity curve</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <line data-testid="equity-baseline" x1={PAD} y1={baseY} x2={W - PAD} y2={baseY} stroke="#5b6472" strokeWidth={1} strokeDasharray="3 3" />
        <polyline data-testid="equity-line" points={pts} fill="none" stroke={up ? "#37c98b" : "#ff5d73"} strokeWidth={1.8} />
      </svg>
    </figure>
  )
}
