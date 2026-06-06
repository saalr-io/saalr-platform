import { useState } from 'react'
import type { CurvePoint } from '../../lib/strategies'
import { computeBounds, toPixels, xForSpot, yForPnl, type Bounds, type Dims } from './scale'

const W = 720, H = 240
const DIMS: Dims = { width: W, height: H, padX: 44, padY: 24 }

function pathFrom(points: { x: number; y: number }[]): string {
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}

const fmtPnl = (v: number) => (v > 0 ? `+${Math.round(v)}` : String(Math.round(v)))
const fmtPrice = (v: number) => String(Math.round(v))

// Axis frame: P&L ticks (incl. 0) down the left, underlying-price ticks (incl. spot)
// along the bottom, plus axis titles. Drawn behind the curves; labels sit in the margins.
function PayoffAxes({ b, spot }: { b: Bounds; spot?: number }) {
  const x0 = DIMS.padX
  const x1 = W - DIMS.padX
  const yTop = DIMS.padY
  const yBot = H - DIMS.padY
  const pnls = [b.maxP, ...(b.minP < 0 && b.maxP > 0 ? [0] : []), b.minP]
  const prices = [b.minS, ...(spot !== undefined && spot > b.minS && spot < b.maxS ? [spot] : []), b.maxS]
  return (
    <g fontFamily="monospace" fontSize={9}>
      <line x1={x0} y1={yTop} x2={x0} y2={yBot} stroke="#2a3340" strokeWidth={1} />
      {pnls.map((p, i) => {
        const y = yForPnl(p, b, DIMS)
        return (
          <g key={`y${i}`}>
            <line x1={x0 - 3} y1={y} x2={x0} y2={y} stroke="#2a3340" strokeWidth={1} />
            <text x={x0 - 5} y={y + 3} textAnchor="end" fill="#6b7480">{fmtPnl(p)}</text>
          </g>
        )
      })}
      <line x1={x0} y1={yBot} x2={x1} y2={yBot} stroke="#2a3340" strokeWidth={1} />
      {prices.map((s, i) => {
        const x = xForSpot(s, b, DIMS)
        const isSpot = spot !== undefined && s === spot
        return (
          <g key={`x${i}`}>
            <line x1={x} y1={yBot} x2={x} y2={yBot + 3} stroke="#2a3340" strokeWidth={1} />
            <text x={x} y={yBot + 13} textAnchor="middle" fill={isSpot ? '#cbd5e1' : '#6b7480'}>{fmtPrice(s)}</text>
          </g>
        )
      })}
      <text x={(x0 + x1) / 2} y={H - 2} textAnchor="middle" fill="#5b6472">underlying</text>
      <text x={4} y={yTop - 8} textAnchor="start" fill="#5b6472">P&amp;L</text>
    </g>
  )
}

export function PayoffChart({
  expirationCurve, targetDateCurve, breakevens, spot,
}: {
  expirationCurve: CurvePoint[]
  targetDateCurve?: CurvePoint[]
  breakevens: number[]
  spot?: number
}) {
  const [hover, setHover] = useState<CurvePoint | null>(null)
  if (expirationCurve.length === 0) return null
  const curves = targetDateCurve ? [expirationCurve, targetDateCurve] : [expirationCurve]
  const b = computeBounds(curves)
  const zeroY = yForPnl(0, b, DIMS)
  const expPx = toPixels(expirationCurve, b, DIMS)

  const areaPath = (sign: 1 | -1) => {
    const clipped = expPx.map((p, i) => ({
      x: p.x,
      y: sign === 1 ? Math.min(p.y, zeroY) : Math.max(p.y, zeroY),
      pnl: expirationCurve[i].pnl,
    }))
    return `${pathFrom(clipped)} L${clipped[clipped.length - 1].x.toFixed(1)},${zeroY.toFixed(1)} L${clipped[0].x.toFixed(1)},${zeroY.toFixed(1)} Z`
  }

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    let nearest = expirationCurve[0]
    let best = Infinity
    for (const p of expirationCurve) {
      const d = Math.abs(xForSpot(p.spot, b, DIMS) - px)
      if (d < best) { best = d; nearest = p }
    }
    setHover(nearest)
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-md border border-line bg-canvas/60"
         onMouseMove={onMove} onMouseLeave={() => setHover(null)} data-testid="payoff-chart">
      <PayoffAxes b={b} spot={spot} />
      <path d={areaPath(1)} fill="rgba(46,160,110,0.16)" />
      <path d={areaPath(-1)} fill="rgba(220,70,70,0.14)" />
      <line x1={DIMS.padX} y1={zeroY} x2={W - DIMS.padX} y2={zeroY} stroke="#2a3340" />
      {targetDateCurve && (
        <path data-testid="payoff-target" d={pathFrom(toPixels(targetDateCurve, b, DIMS))}
              fill="none" stroke="#5b9bd5" strokeWidth={1.6} strokeDasharray="5 4" />
      )}
      <path data-testid="payoff-expiry" d={pathFrom(expPx)} fill="none" stroke="#37c98b" strokeWidth={2.2} />
      {spot !== undefined && (
        <line data-testid="payoff-spot" x1={xForSpot(spot, b, DIMS)} y1={DIMS.padY}
              x2={xForSpot(spot, b, DIMS)} y2={H - DIMS.padY} stroke="#3a4660" strokeDasharray="3 3" />
      )}
      {breakevens.map((be, i) => (
        <circle key={i} data-testid="payoff-be" cx={xForSpot(be, b, DIMS)} cy={zeroY} r={3.5} fill="#e8c24a" />
      ))}
      {hover && (
        <g>
          <line x1={xForSpot(hover.spot, b, DIMS)} y1={DIMS.padY} x2={xForSpot(hover.spot, b, DIMS)}
                y2={H - DIMS.padY} stroke="#2a3340" />
          <text x={xForSpot(hover.spot, b, DIMS) + 6} y={DIMS.padY + 14} className="fill-txtDim" fontSize="11"
                data-testid="payoff-hover">@ {hover.spot.toFixed(1)} · P&amp;L {hover.pnl.toFixed(0)}</text>
        </g>
      )}
    </svg>
  )
}
