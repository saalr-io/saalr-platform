import { describe, it, expect } from 'vitest'
import { GLOSSARY } from './content/glossary'
import {
  definedTermSetJsonLd, definedTermJsonLd, faqPageJsonLd, speakableWebPageJsonLd, faqJsonLd,
} from './jsonld'

const SITE = 'https://saalr.com'
/* eslint-disable @typescript-eslint/no-explicit-any */

describe('glossary JSON-LD', () => {
  it('DefinedTermSet lists one DefinedTerm per glossary term', () => {
    const j = definedTermSetJsonLd(SITE, GLOSSARY) as any
    expect(j['@type']).toBe('DefinedTermSet')
    expect(j.url).toBe(`${SITE}/glossary`)
    expect(j.hasDefinedTerm).toHaveLength(GLOSSARY.length)
    expect(j.hasDefinedTerm[0]['@type']).toBe('DefinedTerm')
  })

  it('DefinedTerm carries inDefinedTermSet and a non-empty sameAs', () => {
    const t = GLOSSARY[0]
    const j = definedTermJsonLd(t, `${SITE}/glossary/${t.slug}`, `${SITE}/glossary`) as any
    expect(j['@type']).toBe('DefinedTerm')
    expect(j.inDefinedTermSet).toBe(`${SITE}/glossary`)
    expect(j.sameAs.length).toBeGreaterThanOrEqual(1)
    expect(j.termCode).toBe(t.slug)
  })

  it('faqPageJsonLd maps items to Question/Answer', () => {
    const j = faqPageJsonLd([{ q: 'Q1', a: 'A1' }]) as any
    expect(j['@type']).toBe('FAQPage')
    expect(j.mainEntity).toHaveLength(1)
    expect(j.mainEntity[0].acceptedAnswer.text).toBe('A1')
  })

  it('faqJsonLd (explainer) still delegates to the same FAQPage shape', () => {
    const j = faqJsonLd({ faq: [{ q: 'Q', a: 'A' }] } as any) as any
    expect(j['@type']).toBe('FAQPage')
    expect(j.mainEntity[0].name).toBe('Q')
  })

  it('speakableWebPageJsonLd is a WebPage with a SpeakableSpecification', () => {
    const j = speakableWebPageJsonLd(`${SITE}/glossary/theta`, 'Theta', 'd', ['.geo-speakable']) as any
    expect(j['@type']).toBe('WebPage')
    expect(j.speakable['@type']).toBe('SpeakableSpecification')
    expect(j.speakable.cssSelector).toEqual(['.geo-speakable'])
  })
})
