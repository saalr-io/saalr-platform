import { describe, it, expect } from 'vitest'
import {
  articleJsonLd, faqJsonLd, breadcrumbJsonLd,
  organizationJsonLd, softwareAppJsonLd, websiteJsonLd,
} from './jsonld'
import { pageMeta } from './meta'

const content = {
  key: 'bull_call_spread', slug: 'bull-call-spread', title: 'Bull Call Spread',
  summary: 'A defined-risk bullish spread.', category: 'bullish' as const,
  whenToUse: 'x', riskProfile: 'y',
  faq: [{ q: 'Max loss?', a: 'The net debit paid.' }], legs: [],
}

describe('jsonld', () => {
  it('articleJsonLd has TechArticle type and headline', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const j = articleJsonLd(content, 'https://saalr.com/learn/bull-call-spread') as any
    expect(j['@context']).toBe('https://schema.org')
    expect(j['@type']).toBe('TechArticle')
    expect(j.headline).toBe('Bull Call Spread')
    expect(j.url).toContain('/learn/bull-call-spread')
  })

  it('faqJsonLd maps each FAQ to a Question/Answer', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const j = faqJsonLd(content) as any
    expect(j['@type']).toBe('FAQPage')
    expect(j.mainEntity).toHaveLength(1)
    expect(j.mainEntity[0]['@type']).toBe('Question')
    expect(j.mainEntity[0].acceptedAnswer['@type']).toBe('Answer')
    expect(j.mainEntity[0].acceptedAnswer.text).toContain('net debit')
  })

  it('breadcrumbJsonLd builds an itemListElement', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

  it('pageMeta defaults og:type to article but honours an override', () => {
    expect(pageMeta({ title: 'T', description: 'D', canonical: 'u' }).og['og:type']).toBe('article')
    expect(
      pageMeta({ title: 'T', description: 'D', canonical: 'u', type: 'website' }).og['og:type'],
    ).toBe('website')
  })
})

describe('landing JSON-LD builders', () => {
  const SITE = 'https://saalr.com'

  it('organization carries context, type, and url', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const o = organizationJsonLd(SITE) as any
    expect(o['@context']).toBe('https://schema.org')
    expect(o['@type']).toBe('Organization')
    expect(o.url).toBe(SITE)
  })

  it('software application is a FinanceApplication on the Web with no price/offers', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const s = softwareAppJsonLd(SITE) as any
    expect(s['@type']).toBe('SoftwareApplication')
    expect(s.applicationCategory).toBe('FinanceApplication')
    expect(s.operatingSystem).toBe('Web')
    expect(s).not.toHaveProperty('offers')
  })

  it('website carries type and url', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = websiteJsonLd(SITE) as any
    expect(w['@type']).toBe('WebSite')
    expect(w.url).toBe(SITE)
  })
})
