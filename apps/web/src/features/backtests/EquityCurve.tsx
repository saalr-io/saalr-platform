import type { EquityPoint } from '../../lib/backtests'

const W = 520
const H = 220
// asymmetric padding leaves room for the $ axis (left) and date axis (bottom)
const PAD = { l: 52, r: 12, t: 12, b: 24 }

function scaler(min: number, max: number, lo: number, hi: number) {
  const span = max - min || 1
  return (v: number) => lo + (hi - lo) * ((v - min) / span)
}

const usdK = (v: number) => {
  const k = v / 1000
  return `$${Math.abs(k) >= 100 ? Math.round(k) : k.toFixed(1)}k`
}

export function EquityCurve({ series, initialCapital }: { series: EquityPoint[]; initialCapital: number }) {
  const eq = series.map((p) => p.equity)
  const n = eq.length
  const ys = [...eq, initialCapital]
  const minEq = Math.min(...ys)
  const maxEq = Math.max(...ys)
  const sx = scaler(0, Math.max(1, n - 1), PAD.l, W - PAD.r)
  const sy = scaler(minEq, maxEq, H - PAD.b, PAD.t)
  const pts = series.map((p, i) => `${sx(i).toFixed(1)},${sy(p.equity).toFixed(1)}`).join(' ')
  const baseY = sy(initialCapital)
  const last = eq[n - 1] ?? initialCapital
  const up = last >= initialCapital

  const yVals = minEq === maxEq ? [initialCapital] : [maxEq, initialCapital, minEq]
  const xIdx = n <= 1 ? [0] : [0, Math.floor((n - 1) / 2), n - 1]

  return (
    <figure className="rounded-lg border border-line bg-panel p-4" data-testid="equity-curve">
      <figcaption className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Equity curve</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <g fontFamily="monospace" fontSize={9}>
          <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} stroke="#2c3340" strokeWidth={1} />
          <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} stroke="#2c3340" strokeWidth={1} />
          {yVals.map((v, i) => {
            const y = sy(v)
            const emphasize = v === initialCapital
            return (
              <g key={`y${i}`}>
                <line x1={PAD.l - 3} y1={y} x2={PAD.l} y2={y} stroke="#2c3340" strokeWidth={1} />
                <text x={PAD.l - 5} y={y + 3} textAnchor="end" fill={emphasize ? '#cbd5e1' : '#7b8494'}>{usdK(v)}</text>
              </g>
            )
          })}
          {xIdx.map((idx, i) => {
            const x = sx(idx)
            const anchor = i === 0 ? 'start' : i === xIdx.length - 1 ? 'end' : 'middle'
            return (
              <g key={`x${i}`}>
                <line x1={x} y1={H - PAD.b} x2={x} y2={H - PAD.b + 3} stroke="#2c3340" strokeWidth={1} />
                <text x={x} y={H - PAD.b + 13} textAnchor={anchor} fill="#7b8494">{series[idx].date}</text>
              </g>
            )
          })}
          <text x={(PAD.l + W - PAD.r) / 2} y={H - 1} textAnchor="middle" fill="#5b6472">date</text>
          <text x={4} y={PAD.t - 2} textAnchor="start" fill="#5b6472">equity</text>
        </g>
        <line data-testid="equity-baseline" x1={PAD.l} y1={baseY} x2={W - PAD.r} y2={baseY} stroke="#5b6472" strokeWidth={1} strokeDasharray="3 3" />
        <polyline data-testid="equity-line" points={pts} fill="none" stroke={up ? "#37c98b" : "#ff5d73"} strokeWidth={1.8} />
      </svg>
    </figure>
  )
}
