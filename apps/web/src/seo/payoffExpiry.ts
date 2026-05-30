export type OptionType = 'CALL' | 'PUT'
export type Side = 'BUY' | 'SELL'
export interface OptionLeg { kind: 'option'; option_type: OptionType; side: Side; strike: number; qty: number; entry_price: number }
export interface EquityLeg { kind: 'equity'; side: Side; qty: number; entry_price: number }
export interface CashLeg { kind: 'cash'; amount: number }
export type ExLeg = OptionLeg | EquityLeg | CashLeg

export interface Pt { spot: number; pnl: number }
const MULT = 100
const TOL = 1e-6
const sign = (s: Side) => (s === 'BUY' ? 1 : -1)

export function spotGrid(legs: ExLeg[], points = 161): number[] {
  const strikes = legs.flatMap((l) => (l.kind === 'option' ? [l.strike] : []))
  const hi = Math.max(100, ...strikes) * 2
  const step = hi / (points - 1)
  const grid = Array.from({ length: points }, (_, i) => i * step)
  for (const s of strikes) if (s >= 0 && s <= hi) grid.push(s)
  return Array.from(new Set(grid)).sort((a, b) => a - b)
}

function legPnl(leg: ExLeg, s: number): number {
  if (leg.kind === 'option') {
    const intrinsic = leg.option_type === 'CALL' ? Math.max(s - leg.strike, 0) : Math.max(leg.strike - s, 0)
    return sign(leg.side) * (intrinsic - leg.entry_price) * MULT * leg.qty
  }
  if (leg.kind === 'equity') return sign(leg.side) * (s - leg.entry_price) * leg.qty
  return 0
}

export function expirationCurve(legs: ExLeg[], grid: number[]): Pt[] {
  return grid.map((spot) => ({ spot, pnl: legs.reduce((a, l) => a + legPnl(l, spot), 0) }))
}

export function breakevens(curve: Pt[]): number[] {
  const out: number[] = []
  for (let i = 0; i < curve.length - 1; i++) {
    const [a, b] = [curve[i], curve[i + 1]]
    if (a.pnl === 0) out.push(a.spot)
    else if ((a.pnl < 0 && b.pnl > 0) || (b.pnl < 0 && a.pnl > 0))
      out.push(a.spot + ((b.spot - a.spot) * (0 - a.pnl)) / (b.pnl - a.pnl))
  }
  return out
}

export interface MaxPL { maxProfit: number | null; maxLoss: number | null; unboundedProfit: boolean; unboundedLoss: boolean }
export function maxPL(curve: Pt[]): MaxPL {
  const pnls = curve.map((p) => p.pnl)
  const rightSlope = curve[curve.length - 1].pnl - curve[curve.length - 2].pnl
  const unboundedProfit = rightSlope > TOL
  const unboundedLoss = rightSlope < -TOL
  return {
    maxProfit: unboundedProfit ? null : Math.max(...pnls),
    maxLoss: unboundedLoss ? null : Math.min(...pnls),
    unboundedProfit,
    unboundedLoss,
  }
}
