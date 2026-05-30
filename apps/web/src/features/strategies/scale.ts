import type { CurvePoint } from '../../lib/strategies'

export interface Bounds { minS: number; maxS: number; minP: number; maxP: number }
export interface Dims { width: number; height: number; padX: number; padY: number }

export function computeBounds(curves: CurvePoint[][]): Bounds {
  const pts = curves.flat()
  if (pts.length === 0) return { minS: 0, maxS: 1, minP: -1, maxP: 1 }
  let minS = Infinity, maxS = -Infinity, minP = Infinity, maxP = -Infinity
  for (const p of pts) {
    if (p.spot < minS) minS = p.spot
    if (p.spot > maxS) maxS = p.spot
    if (p.pnl < minP) minP = p.pnl
    if (p.pnl > maxP) maxP = p.pnl
  }
  if (minS === maxS) { minS -= 1; maxS += 1 }
  if (minP === maxP) { minP -= 1; maxP += 1 }
  return { minS, maxS, minP, maxP }
}

export function xForSpot(spot: number, b: Bounds, d: Dims): number {
  const inner = d.width - 2 * d.padX
  return d.padX + ((spot - b.minS) / (b.maxS - b.minS)) * inner
}

export function yForPnl(pnl: number, b: Bounds, d: Dims): number {
  const inner = d.height - 2 * d.padY
  return d.padY + (1 - (pnl - b.minP) / (b.maxP - b.minP)) * inner
}

export function toPixels(curve: CurvePoint[], b: Bounds, d: Dims): { x: number; y: number }[] {
  return curve.map((p) => ({ x: xForSpot(p.spot, b, d), y: yForPnl(p.pnl, b, d) }))
}
