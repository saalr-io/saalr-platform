import { useState } from 'react'
import type { CurvePoint } from '../../lib/strategies'
import { computeBounds, toPixels, xForSpot, yForPnl, type Dims } from './scale'

const W = 720, H = 240
const DIMS: Dims = { width: W, height: H, padX: 44, padY: 18 }

function pathFrom(points: { x: number; y: number }[]): string {
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
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
