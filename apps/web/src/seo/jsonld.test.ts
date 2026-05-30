import { describe, it, expect } from 'vitest'
import { articleJsonLd, faqJsonLd, breadcrumbJsonLd } from './jsonld'
import { pageMeta } from './meta'

const content = {
  key: 'bull_call_spread', slug: 'bull-call-spread', title: 'Bull Call Spread',
  summary: 'A defined-risk bullish spread.', category: 'bullish' as const,
  whenToUse: 'x', riskProfile: 'y',
  faq: [{ q: 'Max loss?', a: 'The net debit paid.' }], legs: [],
}

describe('jsonld', () => {
  it('articleJsonLd has TechArticle type and headline', () => {
    const j = articleJsonLd(content, 'https://saalr.com/learn/bull-call-spread') as any
    expect(j['@context']).toBe('https://schema.org')
    expect(j['@type']).toBe('TechArticle')
    expect(j.headline).toBe('Bull Call Spread')
    expect(j.url).toContain('/learn/bull-call-spread')
  })

  it('faqJsonLd maps each FAQ to a Question/Answer', () => {
    const j = faqJsonLd(content) as any
    expect(j['@type']).toBe('FAQPage')
    expect(j.mainEntity).toHaveLength(1)
    expect(j.mainEntity[0]['@type']).toBe('Question')
    expect(j.mainEntity[0].acceptedAnswer['@type']).toBe('Answer')
    expect(j.mainEntity[0].acceptedAnswer.text).toContain('net debit')
  })

  it('breadcrumbJsonLd builds an itemListElement', () => {
    const j = breadcrumbJsonLd([{ name: 'Learn', url: '/learn' }, { name: 'Bull Call Spread', url: '/learn/bull-call-spread' }]) as any
    expect(j['@type']).toBe('BreadcrumbList')
    expect(j.itemListElement).toHaveLength(2)
    expect(j.itemListElement[1].position).toBe(2)
  })

  it('pageMeta builds canonical + OG tags', () => {
    const m = pageMeta({ title: 'T', description: 'D', canonical: 'https://saalr.com/learn/x' })
    expect(m.title).toBe('T')
    expect(m.canonical).toBe('https://saalr.com/learn/x')
    expect(m.og['og:title']).toBe('T')
  })
})
