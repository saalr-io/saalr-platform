import { describe, it, expect } from 'vitest'
import { computeBounds, toPixels, xForSpot, yForPnl } from './scale'

const DIMS = { width: 100, height: 100, padX: 0, padY: 0 }

describe('scale', () => {
  it('computeBounds spans all curves', () => {
    const b = computeBounds([[{ spot: 80, pnl: -10 }, { spot: 120, pnl: 30 }]])
    expect(b).toEqual({ minS: 80, maxS: 120, minP: -10, maxP: 30 })
  })

  it('xForSpot maps left/right edges', () => {
    const b = { minS: 80, maxS: 120, minP: -10, maxP: 30 }
    expect(xForSpot(80, b, DIMS)).toBeCloseTo(0)
    expect(xForSpot(120, b, DIMS)).toBeCloseTo(100)
  })

  it('yForPnl inverts (max P&L at top)', () => {
    const b = { minS: 80, maxS: 120, minP: -10, maxP: 30 }
    expect(yForPnl(30, b, DIMS)).toBeCloseTo(0)
    expect(yForPnl(-10, b, DIMS)).toBeCloseTo(100)
  })

  it('toPixels maps a curve', () => {
    const b = { minS: 0, maxS: 100, minP: 0, maxP: 100 }
    const px = toPixels([{ spot: 0, pnl: 0 }, { spot: 100, pnl: 100 }], b, DIMS)
    expect(px[0]).toEqual({ x: 0, y: 100 })
    expect(px[1]).toEqual({ x: 100, y: 0 })
  })

  it('flat P&L range does not divide by zero', () => {
    const b = computeBounds([[{ spot: 50, pnl: 5 }, { spot: 60, pnl: 5 }]])
    const y = yForPnl(5, b, DIMS)
    expect(Number.isFinite(y)).toBe(true)
  })

  it('empty curves yield a safe default span', () => {
    const b = computeBounds([])
    expect(Number.isFinite(b.minS) && Number.isFinite(b.maxP)).toBe(true)
  })
})
