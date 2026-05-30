import { describe, it, expect } from 'vitest'
import { buildSitemap } from './sitemap'
import { buildLlmsTxt } from './llms'

const SITE = 'https://saalr.com'
const pages = [
  { url: '/', title: 'Saalr', description: 'Options analytics' },
  { url: '/learn/bull-call-spread', title: 'Bull Call Spread', description: 'A bullish spread' },
]

describe('seo-build', () => {
  it('sitemap lists every page loc with the site origin', () => {
    const xml = buildSitemap(SITE, pages.map((p) => p.url))
    expect(xml).toContain('<loc>https://saalr.com/learn/bull-call-spread</loc>')
    expect(xml).toContain('<loc>https://saalr.com/</loc>')
    expect(xml.trim().startsWith('<?xml')).toBe(true)
  })

  it('llms.txt lists the learn pages with descriptions', () => {
    const txt = buildLlmsTxt(SITE, 'Saalr', 'Research-grade options analytics.', pages)
    expect(txt).toContain('# Saalr')
    expect(txt).toContain('https://saalr.com/learn/bull-call-spread')
    expect(txt).toContain('Bull Call Spread')
  })
})
