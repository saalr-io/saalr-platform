import { describe, it, expect } from 'vitest'
import { parseModule } from './parseModule'

const SAMPLE_FREE = `---
slug: implied-volatility
title: "Implied volatility"
summary: Implied volatility is the market's forecast of future movement, baked into option prices.
order: 50
min_tier: free
est_minutes: 8
---
# Implied volatility

**Implied volatility (IV)** is the volatility the market is pricing into an option.
`

const SAMPLE_PRO = `---
slug: iron-condor-construction
title: "Constructing an iron condor"
summary: An iron condor sells an out-of-the-money call spread and put spread to profit from range-bound markets.
order: 60
min_tier: pro
est_minutes: 12
---
# Constructing an iron condor

An **iron condor** combines a short out-of-the-money call spread.
`

const SAMPLE_CRLF = SAMPLE_FREE.replace(/\n/g, '\r\n')

describe('parseModule', () => {
  it('parses slug correctly', () => {
    const m = parseModule(SAMPLE_FREE)
    expect(m.slug).toBe('implied-volatility')
  })

  it('strips quotes from title', () => {
    const m = parseModule(SAMPLE_FREE)
    expect(m.title).toBe('Implied volatility')
  })

  it('parses summary without quotes', () => {
    const m = parseModule(SAMPLE_FREE)
    expect(m.summary).toContain("market's forecast")
  })

  it('parses order as number', () => {
    const m = parseModule(SAMPLE_FREE)
    expect(m.order).toBe(50)
  })

  it('parses minTier: free', () => {
    const m = parseModule(SAMPLE_FREE)
    expect(m.minTier).toBe('free')
  })

  it('parses minTier: pro', () => {
    const m = parseModule(SAMPLE_PRO)
    expect(m.minTier).toBe('pro')
  })

  it('parses estMinutes as number', () => {
    const m = parseModule(SAMPLE_FREE)
    expect(m.estMinutes).toBe(8)
  })

  it('extracts the body (after second ---)', () => {
    const m = parseModule(SAMPLE_FREE)
    expect(m.body).toContain('Implied volatility (IV)')
    expect(m.body).not.toContain('min_tier')
  })

  it('handles CRLF line endings', () => {
    const m = parseModule(SAMPLE_CRLF)
    expect(m.slug).toBe('implied-volatility')
    expect(m.title).toBe('Implied volatility')
    expect(m.order).toBe(50)
    expect(m.body).toContain('Implied volatility (IV)')
  })

  it('throws on missing opening fence', () => {
    expect(() => parseModule('slug: foo\n---\nbody')).toThrow('missing opening')
  })

  it('throws (fails loud) on an unrecognized min_tier — never silently publishes as free', () => {
    const typo = SAMPLE_PRO.replace('min_tier: pro', 'min_tier: Pro')
    expect(() => parseModule(typo)).toThrow('invalid or missing min_tier')
  })

  it('throws on a missing min_tier rather than defaulting to free', () => {
    const noTier = SAMPLE_FREE.replace('min_tier: free\n', '')
    expect(() => parseModule(noTier)).toThrow('invalid or missing min_tier')
  })

  it('throws on a missing slug or title', () => {
    const noSlug = SAMPLE_FREE.replace('slug: implied-volatility\n', '')
    expect(() => parseModule(noSlug)).toThrow('missing slug or title')
  })
})

const ALL_MODULE_RAWS = import.meta.glob(
  '../../../../packages/content/saalr_content/modules/*.md',
  { eager: true, query: '?raw', import: 'default' },
) as Record<string, string>

const NEW_LESSONS = [
  ['80-volatility-forecasting.md', 'volatility-forecasting'],
  ['90-price-forecasting.md', 'price-forecasting'],
  ['100-monte-carlo-simulation.md', 'monte-carlo-simulation'],
  ['110-market-sentiment.md', 'market-sentiment'],
  ['120-options-strategy-playbook.md', 'options-strategy-playbook'],
] as const

describe('new help lessons', () => {
  it('the modules directory resolves', () => {
    const keys = Object.keys(ALL_MODULE_RAWS)
    expect(keys.some((k) => k.includes('70-volatility-surface.md'))).toBe(true)
  })

  it.each(NEW_LESSONS)('%s parses, is free, and has the expected slug', (file, slug) => {
    const key = Object.keys(ALL_MODULE_RAWS).find((k) => k.endsWith(file))
    expect(key).toBeTruthy()
    const m = parseModule(ALL_MODULE_RAWS[key!])
    expect(m.slug).toBe(slug)
    expect(m.minTier).toBe('free')
    expect(m.title.length).toBeGreaterThan(0)
    expect(m.body.length).toBeGreaterThan(200)
  })
})
