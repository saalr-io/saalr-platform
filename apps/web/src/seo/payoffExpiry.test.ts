import { describe, it, expect } from 'vitest'
import { spotGrid, expirationCurve, breakevens, maxPL, type ExLeg } from './payoffExpiry'

const longCall = (strike: number, entry: number): ExLeg =>
  ({ kind: 'option', option_type: 'CALL', side: 'BUY', strike, qty: 1, entry_price: entry })
const shortCall = (strike: number, entry: number): ExLeg =>
  ({ kind: 'option', option_type: 'CALL', side: 'SELL', strike, qty: 1, entry_price: entry })

describe('payoffExpiry', () => {
  it('bull call spread: bounded, breakeven = long strike + net debit', () => {
    const legs = [longCall(100, 6), shortCall(110, 2)]
    const grid = spotGrid(legs)
    const curve = expirationCurve(legs, grid)
    const m = maxPL(curve)
    expect(m.unboundedProfit).toBe(false)
    expect(m.unboundedLoss).toBe(false)
    expect(m.maxProfit).toBeCloseTo(600, 0)
    expect(m.maxLoss).toBeCloseTo(-400, 0)
    const be = breakevens(curve)
    expect(be).toHaveLength(1)
    expect(be[0]).toBeCloseTo(104, 0)
  })

  it('short call: unbounded loss', () => {
    const legs = [shortCall(100, 5)]
    const m = maxPL(expirationCurve(legs, spotGrid(legs)))
    expect(m.unboundedLoss).toBe(true)
    expect(m.maxLoss).toBeNull()
    expect(m.maxProfit).toBeCloseTo(500, 0)
  })

  it('iron condor: two breakevens, bounded', () => {
    const legs: ExLeg[] = [
      { kind: 'option', option_type: 'PUT', side: 'BUY', strike: 80, qty: 1, entry_price: 1 },
      { kind: 'option', option_type: 'PUT', side: 'SELL', strike: 90, qty: 1, entry_price: 3 },
      { kind: 'option', option_type: 'CALL', side: 'SELL', strike: 110, qty: 1, entry_price: 3 },
      { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 120, qty: 1, entry_price: 1 },
    ]
    const curve = expirationCurve(legs, spotGrid(legs))
    const m = maxPL(curve)
    expect(m.unboundedProfit).toBe(false)
    expect(m.unboundedLoss).toBe(false)
    expect(breakevens(curve).length).toBe(2)
  })
})
