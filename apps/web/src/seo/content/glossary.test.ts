import { describe, it, expect } from 'vitest'
import { GLOSSARY } from './glossary'
import { EXPLAINERS } from './strategies'

const slugs = new Set(GLOSSARY.map((t) => t.slug))
const explainerSlugs = new Set(EXPLAINERS.map((e) => e.slug))

describe('glossary content', () => {
  it('has a healthy number of terms', () => {
    expect(GLOSSARY.length).toBeGreaterThanOrEqual(24)
  })

  it('slugs are unique and url-safe', () => {
    expect(slugs.size).toBe(GLOSSARY.length)
    for (const t of GLOSSARY) expect(t.slug).toMatch(/^[a-z0-9-]+$/)
  })

  it('every term satisfies the GEO acceptance checklist', () => {
    for (const t of GLOSSARY) {
      expect(t.term.length, t.slug).toBeGreaterThan(0)
      expect(t.short.trim().length, `${t.slug}.short`).toBeGreaterThan(0)
      expect(t.definition.length, `${t.slug}.definition`).toBeGreaterThanOrEqual(1)
      expect(t.definition.every((p) => p.trim().length > 0), `${t.slug}.definition empty para`).toBe(true)
      expect(t.faq.length, `${t.slug}.faq`).toBeGreaterThanOrEqual(2)
      expect(t.faq.every((f) => f.q.trim() && f.a.trim()), `${t.slug}.faq blank`).toBe(true)
      expect(t.sources.length, `${t.slug}.sources`).toBeGreaterThanOrEqual(1)
      expect(t.sources.every((s) => /^https:\/\//.test(s.url) && s.label.trim()), `${t.slug}.sources url`).toBe(true)
      expect(t.sameAs.length, `${t.slug}.sameAs`).toBeGreaterThanOrEqual(1)
      expect(t.sameAs.every((u) => /^https:\/\//.test(u)), `${t.slug}.sameAs url`).toBe(true)
    }
  })

  it('related slugs and seeAlso resolve', () => {
    for (const t of GLOSSARY) {
      for (const r of t.related) expect(slugs.has(r), `${t.slug} -> related ${r}`).toBe(true)
      if (t.seeAlso) expect(explainerSlugs.has(t.seeAlso), `${t.slug} -> seeAlso ${t.seeAlso}`).toBe(true)
    }
  })
})
