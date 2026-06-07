import { describe, it, expect } from 'vitest'
import { HERO, FEATURES, TIERS, FOOTER_LINKS, DISCLAIMER } from './copy'

describe('marketing copy', () => {
  it('hero links into the app and learn surfaces', () => {
    expect(HERO.primary.href).toBe('/app')
    expect(HERO.secondary.href).toBe('/learn')
  })

  it('every feature deep-links to a real public/app route', () => {
    expect(FEATURES.length).toBeGreaterThanOrEqual(6)
    for (const f of FEATURES) {
      expect(f.href).toMatch(/^\/(app|learn)/)
      expect(f.title.length).toBeGreaterThan(0)
      expect(f.blurb.length).toBeGreaterThan(0)
    }
  })

  it('lists the three real tiers with the highest plan being premium', () => {
    expect(TIERS.map((t) => t.name)).toEqual(['Free', 'Pro', 'Premium'])
    expect(TIERS.every((t) => t.features.length > 0)).toBe(true)
  })

  it('quotes no dollar prices anywhere (pre-revenue)', () => {
    const allText = [
      HERO.sub,
      ...FEATURES.map((f) => f.blurb),
      ...TIERS.flatMap((t) => [t.tagline, ...t.features]),
    ].join(' ')
    expect(allText).not.toContain('$')
  })

  it('keeps the not-investment-advice disclaimer and basic footer links', () => {
    expect(DISCLAIMER.toLowerCase()).toContain('not investment advice')
    expect(FOOTER_LINKS.map((l) => l.href)).toEqual(['/learn', '/app'])
  })
})
