import { describe, it, expect } from 'vitest'
import { TIERS, TIER_RANK } from './tiers'

describe('tiers', () => {
  it('exposes the three tiers in order with lowercase keys', () => {
    expect(TIERS.map((t) => t.key)).toEqual(['free', 'pro', 'premium'])
    expect(TIERS.map((t) => t.name)).toEqual(['Free', 'Pro', 'Premium'])
  })
  it('ranks free < pro < premium', () => {
    expect(TIER_RANK.free).toBeLessThan(TIER_RANK.pro)
    expect(TIER_RANK.pro).toBeLessThan(TIER_RANK.premium)
  })
  it('quotes no dollar prices', () => {
    const text = TIERS.flatMap((t) => [t.tagline, ...t.features]).join(' ')
    expect(text).not.toContain('$')
  })
})
