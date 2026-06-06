import { describe, it, expect } from 'vitest'
import { HELP_HINTS, hintProps, lessonPath, ACADEMY_SLUGS } from './helpHints'

const STRATEGY_KEYS = [
  'bull_call_spread', 'bear_put_spread', 'long_straddle', 'long_strangle', 'iron_condor',
  'iron_butterfly', 'covered_call', 'cash_secured_put', 'long_calendar', 'bull_put_spread',
  'bear_call_spread', 'short_straddle', 'short_strangle', 'protective_put', 'collar',
  'call_ratio_spread', 'put_ratio_spread', 'jade_lizard', 'call_butterfly', 'put_butterfly',
  'broken_wing_butterfly',
]
const ML_KEYS = ['vol-forecast', 'price-forecast', 'monte-carlo', 'sentiment', 'vol-surface']

describe('helpHints registry', () => {
  it('covers all ML keys and all 21 strategy keys', () => {
    for (const k of [...ML_KEYS, ...STRATEGY_KEYS]) {
      expect(HELP_HINTS[k], `missing hint for ${k}`).toBeDefined()
    }
  })

  it('every hint has a non-empty title/body, a known lesson slug, and a short body', () => {
    for (const [key, h] of Object.entries(HELP_HINTS)) {
      expect(h.title.trim().length, `${key} title`).toBeGreaterThan(0)
      expect(h.body.trim().length, `${key} body`).toBeGreaterThan(0)
      expect(h.body.length, `${key} body too long`).toBeLessThanOrEqual(240)
      expect(ACADEMY_SLUGS, `${key} slug`).toContain(h.lessonSlug)
    }
  })

  it('hintProps returns InfoHint-ready props with an /education deep-link', () => {
    const p = hintProps('vol-forecast')
    expect(p.title.length).toBeGreaterThan(0)
    expect(p.learnMoreTo).toBe(lessonPath('volatility-forecasting'))
    expect(lessonPath('x')).toBe('/education?lesson=x')
  })

  it('all 21 strategy hints point at the playbook lesson', () => {
    for (const k of STRATEGY_KEYS) {
      expect(HELP_HINTS[k].lessonSlug).toBe('options-strategy-playbook')
    }
  })
})
