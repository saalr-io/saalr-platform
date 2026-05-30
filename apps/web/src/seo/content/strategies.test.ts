import { describe, it, expect } from 'vitest'
import { EXPLAINERS } from './strategies'
import { spotGrid, expirationCurve } from '../payoffExpiry'

const REQUIRED_KEYS = [
  'bull_call_spread', 'bear_put_spread', 'long_straddle', 'long_strangle',
  'iron_condor', 'iron_butterfly', 'covered_call', 'cash_secured_put', 'long_calendar',
]

describe('EXPLAINERS content map', () => {
  it('covers all nine template keys', () => {
    expect(new Set(EXPLAINERS.map((e) => e.key))).toEqual(new Set(REQUIRED_KEYS))
  })

  it('every entry has unique slug + complete required fields + an FAQ', () => {
    const slugs = new Set<string>()
    for (const e of EXPLAINERS) {
      expect(e.slug).toMatch(/^[a-z0-9-]+$/)
      expect(slugs.has(e.slug)).toBe(false)
      slugs.add(e.slug)
      expect(e.title.length).toBeGreaterThan(3)
      expect(e.summary.length).toBeGreaterThan(20)
      expect(e.whenToUse.length).toBeGreaterThan(10)
      expect(e.riskProfile.length).toBeGreaterThan(10)
      expect(['bullish', 'bearish', 'neutral']).toContain(e.category)
      expect(e.faq.length).toBeGreaterThanOrEqual(1)
      for (const f of e.faq) { expect(f.q.length).toBeGreaterThan(3); expect(f.a.length).toBeGreaterThan(10) }
      expect(e.legs.length).toBeGreaterThanOrEqual(1)
    }
  })

  it('every entry produces a non-empty payoff curve', () => {
    for (const e of EXPLAINERS) {
      const curve = expirationCurve(e.legs, spotGrid(e.legs))
      expect(curve.length).toBeGreaterThan(2)
    }
  })
})
