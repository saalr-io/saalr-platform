import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ExplainerArticle } from './@strategy/ExplainerArticle'
import { EXPLAINERS } from '../../src/seo/content/strategies'

describe('ExplainerArticle', () => {
  it('renders H1, FAQ, JSON-LD, and an SVG payoff for a known strategy', () => {
    const content = EXPLAINERS.find((e) => e.slug === 'bull-call-spread')!
    const html = renderToStaticMarkup(<ExplainerArticle content={content} origin="https://saalr.com" />)
    expect(html).toContain('Bull Call Spread')
    expect(html).toContain('application/ld+json')
    expect(html).toContain('<svg')
    expect(html).toContain('FAQPage')
  })
})
