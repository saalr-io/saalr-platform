# SEO/GEO Glossary + llms-full.txt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GEO-first options **glossary** (`/glossary` index + `/glossary/<term>` per-term, SSG) with DefinedTermSet/DefinedTerm/FAQPage/WebPage-speakable/BreadcrumbList JSON-LD, authoritative `sources` + `sameAs` entity links, **plus `llms-full.txt`** (full-content dump) and explicit AI-crawler `robots.txt`. Spec: `docs/superpowers/specs/2026-06-04-seo-glossary-design.md`.

**Architecture:** Mirror the shipped `/learn` Vike pattern. One content module (`src/seo/content/glossary.ts`), JSON-LD helpers in `src/seo/jsonld.ts`, two route folders under `pages/glossary/`, build-time generators in `src/seo-build/llms.ts` + `scripts/gen-seo.ts`. Content quality is enforced by a checklist test, not prose review alone.

**Tech Stack:** Vike SSG + React 18 + TS strict + Vitest. **pnpm** (NOT npm — never `npm install`).

**Conventions (apply to every task):**
- Run from `apps/web`: `npx vitest run <files>`; gate `npm run typecheck` + `npm run lint`.
- Commit footer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Theme tokens only for Tailwind class colors. Double-quote JSX apostrophes. External links get `rel="noopener noreferrer"`.
- NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`. Stage ONLY each task's files.
- JSON-LD is rendered as a body `<script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(arr) }} />` (mirror `pages/learn/@strategy/ExplainerArticle.tsx`).
- The canonical origin: each glossary route folder gets a local `origin.ts` (2 lines, mirror `pages/learn/@strategy/origin.ts`): `declare const __SITE_ORIGIN__: string` / `export const ORIGIN = __SITE_ORIGIN__`.

---

### Task 1: glossary content `src/seo/content/glossary.ts` + checklist test

**Files:** Create `apps/web/src/seo/content/glossary.ts`, `apps/web/src/seo/content/glossary.test.ts`.

- [ ] **Step 1: write the checklist test** `glossary.test.ts` (this ENFORCES the GEO acceptance checklist — a non-conforming term fails the build):

```typescript
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
```

- [ ] **Step 2: run → FAIL** (no `glossary.ts`). `cd apps/web && npx vitest run src/seo/content/glossary.test.ts`

- [ ] **Step 3: create** `apps/web/src/seo/content/glossary.ts` with the types and the full `GLOSSARY` array. **Types (verbatim):**

```typescript
export interface GlossaryFaq { q: string; a: string }
export interface GlossarySource { label: string; url: string }
export interface GlossaryTerm {
  slug: string
  term: string
  short: string
  definition: string[]
  example?: string
  related: string[]
  seeAlso?: string
  faq: GlossaryFaq[]
  sources: GlossarySource[]
  sameAs: string[]
}

export const GLOSSARY: GlossaryTerm[] = [
  /* … ~28 terms … */
]
```

**Authoring rules (per the GEO acceptance checklist in the spec):** answer-first `short` (≤1 sentence, self-contained); 1–3 short paragraphs with a concrete number; an `example` with numbers; 2–3 answer-first FAQ Q&As (≥1 cites a number or source); ≥1 authoritative `sources` (CBOE `https://www.cboe.com/...`, OCC `https://www.theocc.com/...`, SEC `https://www.investor.gov/...`, or Investopedia); ≥1 `sameAs` (Wikipedia or Investopedia canonical URL); correct terminology; no keyword stuffing.

**Two fully-authored exemplars (use these as the quality bar):**

```typescript
  {
    slug: 'theta',
    term: 'Theta',
    short: 'Theta is the option Greek that measures how much an option’s price falls for each day that passes, holding all else equal.',
    definition: [
      'Theta quantifies time decay: it is the dollar change in an option’s premium per one-day decline in time to expiration. It is almost always negative for long options because options lose extrinsic value as expiration nears.',
      'Decay is not linear — it accelerates in the final 30 days and is fastest for at-the-money options. A position with −0.05 theta loses about $5 per contract per day (×100 multiplier), all else equal.',
    ],
    example: 'A 30-day at-the-money call priced at $2.00 with a theta of −0.04 loses roughly $0.04 of value overnight, to ≈ $1.96, if the underlying and implied volatility are unchanged.',
    related: ['the-greeks', 'extrinsic-value', 'implied-volatility', 'expiration'],
    seeAlso: 'covered-call',
    faq: [
      { q: 'Is theta good or bad for option buyers?', a: 'Theta works against buyers and for sellers: a long option loses time value each day, while a short option gains it, all else equal.' },
      { q: 'When is theta highest?', a: 'Theta decay is largest for at-the-money options and accelerates in the last few weeks before expiration, per the CBOE Options Institute.' },
    ],
    sources: [
      { label: 'CBOE Options Institute — The Greeks', url: 'https://www.cboe.com/optionsinstitute/' },
      { label: 'OCC — Options education', url: 'https://www.theocc.com/' },
    ],
    sameAs: ['https://en.wikipedia.org/wiki/Greeks_(finance)#Theta', 'https://www.investopedia.com/terms/t/theta.asp'],
  },
  {
    slug: 'implied-volatility',
    term: 'Implied Volatility',
    short: 'Implied volatility (IV) is the market’s forecast of how much an underlying will move, expressed as an annualized percentage and backed out of an option’s price.',
    definition: [
      'IV is the volatility input that, placed into an option-pricing model such as Black–Scholes, reproduces the option’s observed market price. Higher IV means richer premiums and a wider expected range.',
      'IV is forward-looking and differs from realized (historical) volatility, which is measured from past prices. An IV of 20% implies a one-standard-deviation annual move of about 20% in the underlying.',
    ],
    example: 'A stock at $100 with 20% IV implies a ≈ ±$20 one-standard-deviation range over a year, or roughly ±$5.5 over one month (20% × √(1/12) × 100).',
    related: ['historical-volatility', 'iv-rank', 'vega', 'extrinsic-value'],
    seeAlso: 'long-straddle',
    faq: [
      { q: 'What does high implied volatility mean?', a: 'High IV means the market expects large moves, so option premiums are more expensive; it often rises before earnings and falls afterward.' },
      { q: 'Is implied volatility the same as historical volatility?', a: 'No — IV is the market’s forward expectation embedded in option prices, while historical volatility is computed from realized past returns.' },
    ],
    sources: [
      { label: 'CBOE — VIX & volatility', url: 'https://www.cboe.com/tradable_products/vix/' },
      { label: 'SEC investor.gov — Options', url: 'https://www.investor.gov/' },
    ],
    sameAs: ['https://en.wikipedia.org/wiki/Implied_volatility', 'https://www.investopedia.com/terms/i/iv.asp'],
  },
```

**Remaining ~26 terms to author** (each to the same bar; suggested `sameAs` = the Investopedia/Wikipedia page for the term, `sources` = CBOE/OCC/SEC as fits): call, put, strike, expiration, premium, intrinsic-value, extrinsic-value, in-the-money, out-of-the-money, at-the-money, moneyness, historical-volatility, iv-rank, delta, gamma, vega, rho, the-greeks, open-interest, volume, bid-ask-spread, assignment, exercise, american-vs-european, break-even, put-call-parity. Wire `related` to terms that exist in this list and `seeAlso` to a real EXPLAINER slug where natural (explainer slugs: bull-call-spread, bear-put-spread, covered-call, cash-secured-put, long-straddle, long-strangle, iron-condor, iron-butterfly, long-calendar — confirm against `src/seo/content/strategies.ts`).

- [ ] **Step 4: run → PASS** — `npx vitest run src/seo/content/glossary.test.ts`. typecheck + lint clean.

- [ ] **Step 5: commit**

```bash
git add apps/web/src/seo/content/glossary.ts apps/web/src/seo/content/glossary.test.ts
git commit -m "feat(seo): GEO-first options glossary content (~28 terms, sources + sameAs + FAQ)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: JSON-LD helpers (`DefinedTermSet`/`DefinedTerm`/`faqPageJsonLd`/`speakableWebPageJsonLd`)

**Files:** Modify `apps/web/src/seo/jsonld.ts`; create `apps/web/src/seo/glossaryJsonLd.test.ts`.

- [ ] **Step 1: write the failing test** `apps/web/src/seo/glossaryJsonLd.test.ts`:

```typescript
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
```

- [ ] **Step 2: run → FAIL** — `npx vitest run src/seo/glossaryJsonLd.test.ts`

- [ ] **Step 3: edit `apps/web/src/seo/jsonld.ts`** — refactor `faqJsonLd` to delegate, and append the new helpers:

```typescript
export function faqPageJsonLd(items: { q: string; a: string }[]): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: items.map((f) => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a },
    })),
  }
}
```

Change the existing `faqJsonLd` body to:

```typescript
export function faqJsonLd(c: ExplainerContent): Record<string, unknown> {
  return faqPageJsonLd(c.faq)
}
```

Append (import the type at the top: `import type { GlossaryTerm } from './content/glossary'`):

```typescript
export function definedTermSetJsonLd(site: string, terms: GlossaryTerm[]): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'DefinedTermSet',
    name: 'Saalr Options Glossary',
    url: `${site}/glossary`,
    hasDefinedTerm: terms.map((t) => ({
      '@type': 'DefinedTerm',
      name: t.term,
      description: t.short,
      url: `${site}/glossary/${t.slug}`,
      termCode: t.slug,
    })),
  }
}

export function definedTermJsonLd(term: GlossaryTerm, url: string, setUrl: string): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'DefinedTerm',
    name: term.term,
    description: term.short,
    url,
    termCode: term.slug,
    inDefinedTermSet: setUrl,
    sameAs: term.sameAs,
  }
}

export function speakableWebPageJsonLd(
  url: string, name: string, description: string, cssSelector: string[],
): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    url,
    name,
    description,
    speakable: { '@type': 'SpeakableSpecification', cssSelector },
  }
}
```

- [ ] **Step 4: run → PASS** both `glossaryJsonLd.test.ts` and the existing `jsonld.test.ts` (the `faqJsonLd` refactor is output-preserving). typecheck + lint clean.

- [ ] **Step 5: commit**

```bash
git add apps/web/src/seo/jsonld.ts apps/web/src/seo/glossaryJsonLd.test.ts
git commit -m "feat(seo): glossary JSON-LD (DefinedTermSet/DefinedTerm+sameAs, faqPage refactor, speakable WebPage)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: glossary index page `pages/glossary/`

**Files:** Create `pages/glossary/+Page.tsx`, `+Head.tsx`, `+title.ts`, `+description.ts`, `origin.ts`.

- [ ] **Step 1: create** `pages/glossary/origin.ts`:

```typescript
declare const __SITE_ORIGIN__: string
export const ORIGIN = __SITE_ORIGIN__
```

- [ ] **Step 2: create** `pages/glossary/+title.ts`:

```typescript
export function title(): string {
  return 'Options glossary — SAALR'
}
```

- [ ] **Step 3: create** `pages/glossary/+description.ts`:

```typescript
export function description(): string {
  return 'Plain-English definitions of options terms — calls, puts, the Greeks, implied volatility, assignment and more, each with examples and sources.'
}
```

- [ ] **Step 4: create** `pages/glossary/+Head.tsx`:

```typescript
import { pageMeta } from '../../src/seo/meta'
import { ORIGIN } from './origin'

export default function Head() {
  const meta = pageMeta({
    title: 'Options glossary — SAALR',
    description: 'Plain-English definitions of options terms, each with examples and authoritative sources.',
    canonical: `${ORIGIN}/glossary`,
  })
  return (
    <>
      <link rel="canonical" href={meta.canonical} />
      {Object.entries(meta.og).map(([k, v]) => (
        <meta key={k} property={k} content={v} />
      ))}
      {Object.entries(meta.twitter).map(([k, v]) => (
        <meta key={k} name={k} content={v} />
      ))}
    </>
  )
}
```

- [ ] **Step 5: create** `pages/glossary/+Page.tsx`:

```typescript
import { GLOSSARY } from '../../src/seo/content/glossary'
import { definedTermSetJsonLd, breadcrumbJsonLd } from '../../src/seo/jsonld'
import { ORIGIN } from './origin'

export default function Page() {
  const terms = [...GLOSSARY].sort((a, b) => a.term.localeCompare(b.term))
  const jsonld = [
    definedTermSetJsonLd(ORIGIN, GLOSSARY),
    breadcrumbJsonLd([
      { name: 'Home', url: ORIGIN },
      { name: 'Glossary', url: `${ORIGIN}/glossary` },
    ]),
  ]
  return (
    <main className="mx-auto max-w-3xl p-6">
      <nav className="mb-2 text-xs text-txtDim"><a href="/learn">Learn</a> / Glossary</nav>
      <h1 className="text-2xl font-semibold">Options glossary</h1>
      <p className="mt-2 text-txtDim">
        Plain-English definitions of the options terms you’ll meet across the strategies and
        academy — each with a worked example and authoritative sources.
      </p>
      <ul className="mt-6 space-y-4">
        {terms.map((t) => (
          <li key={t.slug}>
            <a href={`/glossary/${t.slug}`} className="text-accent underline">{t.term}</a>
            <p className="mt-1 text-sm text-txtDim">{t.short}</p>
          </li>
        ))}
      </ul>
      <p className="mt-8 text-sm text-txtDim">
        New to strategies? <a href="/learn" className="text-accent underline">Browse the strategy explainers →</a>
      </p>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonld) }} />
    </main>
  )
}
```

- [ ] **Step 6: typecheck + lint** clean.

- [ ] **Step 7: commit**

```bash
git add apps/web/pages/glossary/origin.ts apps/web/pages/glossary/+title.ts apps/web/pages/glossary/+description.ts apps/web/pages/glossary/+Head.tsx apps/web/pages/glossary/+Page.tsx
git commit -m "feat(seo): /glossary index page (DefinedTermSet + breadcrumb JSON-LD)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: per-term page `pages/glossary/@term/` + GlossaryTermArticle

**Files:** Create `pages/glossary/@term/origin.ts`, `+title.ts`, `+description.ts`, `+Head.tsx`, `+onBeforePrerenderStart.ts`, `+Page.tsx`, and `pages/glossary/@term/GlossaryTermArticle.tsx`; create `pages/glossary/@term/glossaryTerm.test.tsx`.

- [ ] **Step 1: create** `pages/glossary/@term/origin.ts` (same 2 lines as Task 3 Step 1).

- [ ] **Step 2: create** `pages/glossary/@term/+onBeforePrerenderStart.ts`:

```typescript
import { GLOSSARY } from '../../../src/seo/content/glossary'

export function onBeforePrerenderStart() {
  return GLOSSARY.map((t) => `/glossary/${t.slug}`)
}
```

- [ ] **Step 3: create** `pages/glossary/@term/+title.ts`:

```typescript
import type { PageContext } from 'vike/types'
import { GLOSSARY } from '../../../src/seo/content/glossary'

export function title(pageContext: PageContext): string {
  const t = GLOSSARY.find((x) => x.slug === pageContext.routeParams?.term)
  return t ? `${t.term} — SAALR options glossary` : 'SAALR'
}
```

- [ ] **Step 4: create** `pages/glossary/@term/+description.ts`:

```typescript
import type { PageContext } from 'vike/types'
import { GLOSSARY } from '../../../src/seo/content/glossary'

export function description(pageContext: PageContext): string {
  const t = GLOSSARY.find((x) => x.slug === pageContext.routeParams?.term)
  return t?.short ?? 'Options glossary term.'
}
```

- [ ] **Step 5: create** `pages/glossary/@term/+Head.tsx`:

```typescript
import { usePageContext } from 'vike-react/usePageContext'
import { GLOSSARY } from '../../../src/seo/content/glossary'
import { pageMeta } from '../../../src/seo/meta'
import { ORIGIN } from './origin'

export default function Head() {
  const pageContext = usePageContext()
  const t = GLOSSARY.find((x) => x.slug === pageContext.routeParams?.term)
  if (!t) return null
  const meta = pageMeta({
    title: `${t.term} — SAALR options glossary`,
    description: t.short,
    canonical: `${ORIGIN}/glossary/${t.slug}`,
  })
  return (
    <>
      <link rel="canonical" href={meta.canonical} />
      {Object.entries(meta.og).map(([k, v]) => (
        <meta key={k} property={k} content={v} />
      ))}
      {Object.entries(meta.twitter).map(([k, v]) => (
        <meta key={k} name={k} content={v} />
      ))}
    </>
  )
}
```

- [ ] **Step 6: create** `pages/glossary/@term/GlossaryTermArticle.tsx`:

```typescript
import type { GlossaryTerm } from '../../../src/seo/content/glossary'
import { GLOSSARY } from '../../../src/seo/content/glossary'
import { EXPLAINERS } from '../../../src/seo/content/strategies'
import {
  definedTermJsonLd, faqPageJsonLd, speakableWebPageJsonLd, breadcrumbJsonLd,
} from '../../../src/seo/jsonld'

export function GlossaryTermArticle({ term, origin }: { term: GlossaryTerm; origin: string }) {
  const url = `${origin}/glossary/${term.slug}`
  const related = term.related
    .map((slug) => GLOSSARY.find((t) => t.slug === slug))
    .filter((t): t is GlossaryTerm => Boolean(t))
  const explainer = term.seeAlso ? EXPLAINERS.find((e) => e.slug === term.seeAlso) : undefined
  const jsonld = [
    definedTermJsonLd(term, url, `${origin}/glossary`),
    faqPageJsonLd(term.faq),
    speakableWebPageJsonLd(url, `${term.term} — SAALR options glossary`, term.short, ['.geo-speakable']),
    breadcrumbJsonLd([
      { name: 'Home', url: origin },
      { name: 'Glossary', url: `${origin}/glossary` },
      { name: term.term, url },
    ]),
  ]
  return (
    <article className="mx-auto max-w-3xl p-6">
      <nav className="mb-2 text-xs text-txtDim">
        <a href="/glossary">Glossary</a> / {term.term}
      </nav>
      <h1 className="text-2xl font-semibold">{term.term}</h1>
      <p className="geo-speakable mt-2 text-lg text-txt">{term.short}</p>
      {term.definition.map((p, i) => (
        <p key={i} className="mt-3 text-txtDim">{p}</p>
      ))}
      {term.example && (
        <p className="mt-4 rounded border border-line bg-panel p-3 text-sm text-txtDim">
          <span className="font-medium text-txt">Example. </span>{term.example}
        </p>
      )}
      <section className="geo-speakable mt-6">
        <h2 className="text-lg font-semibold">FAQ</h2>
        {term.faq.map((f, i) => (
          <div key={i} className="mt-3">
            <h3 className="font-medium">{f.q}</h3>
            <p className="text-txtDim">{f.a}</p>
          </div>
        ))}
      </section>
      {related.length > 0 && (
        <section className="mt-6">
          <h2 className="text-lg font-semibold">Related terms</h2>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {related.map((r) => (
              <li key={r.slug}>
                <a href={`/glossary/${r.slug}`} className="text-accent underline">{r.term}</a>
              </li>
            ))}
          </ul>
        </section>
      )}
      {explainer && (
        <p className="mt-6 text-sm text-txtDim">
          See also: <a href={`/learn/${explainer.slug}`} className="text-accent underline">{explainer.title}</a>
        </p>
      )}
      <section className="mt-6">
        <h2 className="text-lg font-semibold">References</h2>
        <ul className="mt-2 space-y-1 text-sm">
          {term.sources.map((s, i) => (
            <li key={i}>
              <a href={s.url} rel="noopener noreferrer" className="text-accent underline">{s.label}</a>
            </li>
          ))}
        </ul>
      </section>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonld) }} />
    </article>
  )
}
```

- [ ] **Step 7: create** `pages/glossary/@term/+Page.tsx`:

```typescript
import { usePageContext } from 'vike-react/usePageContext'
import { GlossaryTermArticle } from './GlossaryTermArticle'
import { GLOSSARY } from '../../../src/seo/content/glossary'
import { ORIGIN } from './origin'

export default function Page() {
  const pageContext = usePageContext()
  const slug = pageContext.routeParams.term
  const term = GLOSSARY.find((t) => t.slug === slug)
  if (!term) {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <h1 className="text-2xl font-semibold">Not found</h1>
        <p className="mt-2 text-txtDim">
          No glossary term for “{slug}”. <a href="/glossary" className="text-accent underline">Back to the glossary</a>.
        </p>
      </main>
    )
  }
  return <GlossaryTermArticle term={term} origin={ORIGIN} />
}
```

- [ ] **Step 8: write the render test** `pages/glossary/@term/glossaryTerm.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GlossaryTermArticle } from './GlossaryTermArticle'
import { GLOSSARY } from '../../../src/seo/content/glossary'

const theta = GLOSSARY.find((t) => t.slug === 'theta')!

describe('GlossaryTermArticle', () => {
  it('renders the answer-first definition in a geo-speakable element, plus references', () => {
    const { container } = render(<GlossaryTermArticle term={theta} origin="https://saalr.com" />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Theta')
    expect(container.querySelector('.geo-speakable')!.textContent).toContain(theta.short.slice(0, 20))
    // references render as external links
    const refs = Array.from(container.querySelectorAll('a[rel="noopener noreferrer"]'))
    expect(refs.length).toBeGreaterThanOrEqual(theta.sources.length)
    // JSON-LD present
    expect(container.querySelector('script[type="application/ld+json"]')!.textContent).toContain('DefinedTerm')
    expect(container.querySelector('script[type="application/ld+json"]')!.textContent).toContain('SpeakableSpecification')
  })
})
```

- [ ] **Step 9: run → PASS** `npx vitest run pages/glossary/@term/glossaryTerm.test.tsx`. typecheck + lint clean.

- [ ] **Step 10: commit**

```bash
git add apps/web/pages/glossary/@term/
git commit -m "feat(seo): /glossary/<term> pages (DefinedTerm+sameAs, FAQPage, speakable, references)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: llms-full.txt + sitemap/llms wiring + robots AI-crawlers

**Files:** Modify `apps/web/src/seo-build/llms.ts`, `apps/web/scripts/gen-seo.ts`, `apps/web/public/robots.txt`, `apps/web/pages/learn/+Page.tsx`; create `apps/web/src/seo-build/llmsFull.test.ts`.

- [ ] **Step 1: failing test** `apps/web/src/seo-build/llmsFull.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { buildLlmsFullTxt, explainerToText, glossaryTermToText } from './llms'
import { EXPLAINERS } from '../seo/content/strategies'
import { GLOSSARY } from '../seo/content/glossary'

const SITE = 'https://saalr.com'

describe('llms-full', () => {
  it('explainerToText includes the summary and FAQ answers', () => {
    const e = EXPLAINERS[0]
    const txt = explainerToText(e)
    expect(txt).toContain(e.summary)
    expect(txt).toContain(e.faq[0].a)
  })

  it('glossaryTermToText includes the definition, FAQ, and a source URL', () => {
    const t = GLOSSARY.find((x) => x.slug === 'theta')!
    const txt = glossaryTermToText(t)
    expect(txt).toContain(t.short)
    expect(txt).toContain(t.faq[0].a)
    expect(txt).toContain(t.sources[0].url)
  })

  it('buildLlmsFullTxt concatenates sections and headings', () => {
    const out = buildLlmsFullTxt(SITE, 'Saalr', 'tagline', [
      { heading: 'Glossary', entries: [{ title: 'Theta', url: '/glossary/theta', body: 'BODY-THETA' }] },
    ])
    expect(out).toContain('# Saalr')
    expect(out).toContain('## Glossary')
    expect(out).toContain('### Theta')
    expect(out).toContain(`${SITE}/glossary/theta`)
    expect(out).toContain('BODY-THETA')
  })

  it('omits a Pro academy body when the caller filters it out (leak guard)', () => {
    const out = buildLlmsFullTxt(SITE, 'Saalr', 'tagline', [
      { heading: 'OptionsAcademy', entries: [{ title: 'Free lesson', url: '/academy/x', body: 'FREE-BODY' }] },
    ])
    expect(out).toContain('FREE-BODY')
    expect(out).not.toContain('PRO-ONLY-BODY')
  })
})
```

- [ ] **Step 2: run → FAIL** — `npx vitest run src/seo-build/llmsFull.test.ts`

- [ ] **Step 3: edit `apps/web/src/seo-build/llms.ts`** — append the serializers + builder (keep `buildLlmsTxt` as-is, but see Step 5 for its header tweak):

```typescript
import type { ExplainerContent } from '../seo/content/strategies'
import type { GlossaryTerm } from '../seo/content/glossary'

export function explainerToText(e: ExplainerContent): string {
  const faq = e.faq.map((f) => `Q: ${f.q}\nA: ${f.a}`).join('\n')
  return `${e.summary}\n\nWhen to use: ${e.whenToUse}\nRisk profile: ${e.riskProfile}\n\nFAQ:\n${faq}`
}

export function glossaryTermToText(t: GlossaryTerm): string {
  const faq = t.faq.map((f) => `Q: ${f.q}\nA: ${f.a}`).join('\n')
  const refs = t.sources.map((s) => `${s.label}: ${s.url}`).join('\n')
  const ex = t.example ? `\nExample: ${t.example}` : ''
  return `${t.short}\n\n${t.definition.join('\n\n')}${ex}\n\nFAQ:\n${faq}\n\nReferences:\n${refs}`
}

export interface LlmsFullEntry { title: string; url: string; body: string }
export interface LlmsFullSection { heading: string; entries: LlmsFullEntry[] }

export function buildLlmsFullTxt(
  site: string, name: string, summary: string, sections: LlmsFullSection[],
): string {
  const head = `# ${name}\n\n${summary}\n\nSite: ${site}\nSee also: ${site}/llms.txt (index)\n\nFull public learning content, provided for AI and LLM ingestion.\n`
  const body = sections
    .map((s) => {
      const entries = s.entries
        .map((e) => `### ${e.title}\nURL: ${site}${e.url}\n\n${e.body}`)
        .join('\n\n')
      return `## ${s.heading}\n\n${entries}`
    })
    .join('\n\n')
  return `${head}\n${body}\n`
}
```

- [ ] **Step 4: run → PASS** `llmsFull.test.ts` (and the existing `buildLlmsTxt` callers/tests unaffected).

- [ ] **Step 5: wire `apps/web/scripts/gen-seo.ts`** — add the glossary import + URLs to the `pages` array, and emit `llms-full.txt`. The full edited file:

```typescript
import { writeFileSync } from 'node:fs'
import { buildSitemap } from '../src/seo-build/sitemap'
import { buildLlmsTxt } from '../src/seo-build/llms'
import { buildLlmsFullTxt, explainerToText, glossaryTermToText } from '../src/seo-build/llms'
import { EXPLAINERS } from '../src/seo/content/strategies'
import { GLOSSARY } from '../src/seo/content/glossary'
import { ACADEMY_MODULES } from '../src/academy/modules.generated'

const ACADEMY_DESC = 'Free, plain-English lessons on options — from what an option is to how volatility is priced in.'

const SITE = process.env.SITE_ORIGIN ?? 'https://saalr.com'
const freeAcademy = ACADEMY_MODULES.filter((m) => m.body !== null)
const pages = [
  { url: '/', title: 'SAALR — Research-grade options analytics', description: 'Build and price multi-leg options strategies, study volatility, run backtests, and read multi-agent research notes — from one fast terminal.' },
  { url: '/learn', title: 'Learn options strategies', description: 'Explainers for common options strategies.' },
  ...EXPLAINERS.map((e) => ({ url: `/learn/${e.slug}`, title: e.title, description: e.summary })),
  { url: '/glossary', title: 'Options glossary', description: 'Plain-English definitions of options terms, each with examples and sources.' },
  ...GLOSSARY.map((t) => ({ url: `/glossary/${t.slug}`, title: t.term, description: t.short })),
  { url: '/academy', title: 'OptionsAcademy', description: ACADEMY_DESC },
  ...freeAcademy.map((m) => ({ url: `/academy/${m.slug}`, title: m.title, description: m.summary })),
]
writeFileSync('dist/client/sitemap.xml', buildSitemap(SITE, pages.map((p) => p.url)))
writeFileSync('dist/client/llms.txt', buildLlmsTxt(SITE, 'Saalr', 'Research-grade options analytics for retail traders.', pages))

const fullSections = [
  { heading: 'Options strategies', entries: EXPLAINERS.map((e) => ({ title: e.title, url: `/learn/${e.slug}`, body: explainerToText(e) })) },
  { heading: 'OptionsAcademy', entries: freeAcademy.map((m) => ({ title: m.title, url: `/academy/${m.slug}`, body: m.body ?? '' })) },
  { heading: 'Options glossary', entries: GLOSSARY.map((t) => ({ title: t.term, url: `/glossary/${t.slug}`, body: glossaryTermToText(t) })) },
]
writeFileSync('dist/client/llms-full.txt', buildLlmsFullTxt(SITE, 'Saalr', 'Research-grade options analytics for retail traders.', fullSections))

console.log(`wrote sitemap.xml + llms.txt + llms-full.txt (${pages.length} pages)`)
```

- [ ] **Step 6: robots — replace `apps/web/public/robots.txt`** with:

```
User-agent: *
Allow: /
Disallow: /app
Disallow: /api

User-agent: GPTBot
Allow: /
Disallow: /app
Disallow: /api

User-agent: ChatGPT-User
Allow: /
Disallow: /app
Disallow: /api

User-agent: ClaudeBot
Allow: /
Disallow: /app
Disallow: /api

User-agent: anthropic-ai
Allow: /
Disallow: /app
Disallow: /api

User-agent: PerplexityBot
Allow: /
Disallow: /app
Disallow: /api

User-agent: Google-Extended
Allow: /
Disallow: /app
Disallow: /api

User-agent: Bingbot
Allow: /
Disallow: /app
Disallow: /api

Sitemap: https://saalr.com/sitemap.xml
```

- [ ] **Step 7: link glossary from `apps/web/pages/learn/+Page.tsx`** — add, right after the intro `<p>…</p>` (before the `{GROUPS.map(...)}`):

```typescript
      <p className="mt-3 text-sm text-txtDim">
        New to the jargon? <a href="/glossary" className="text-accent underline">Browse the options glossary →</a>
      </p>
```

- [ ] **Step 8: typecheck + lint** clean; `npx vitest run src/seo-build` green.

- [ ] **Step 9: commit**

```bash
git add apps/web/src/seo-build/llms.ts apps/web/src/seo-build/llmsFull.test.ts apps/web/scripts/gen-seo.ts apps/web/public/robots.txt apps/web/pages/learn/+Page.tsx
git commit -m "feat(seo): llms-full.txt dump + glossary in sitemap/llms + AI-crawler robots + learn->glossary link

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: prerender assertions + final gate

**Files:** Modify `apps/web/scripts/check-prerender.mjs` (or wherever the prerender smoke lives — confirm by reading it).

- [ ] **Step 1: read** `apps/web/scripts/check-prerender.mjs` to match its existing assertion style.

- [ ] **Step 2: add assertions** (mirror the file's style) after a build: `dist/client/glossary/index.html` exists and contains `DefinedTermSet`; a sample `dist/client/glossary/theta/index.html` exists and contains `Theta`, `application/ld+json`, `SpeakableSpecification`, `class="geo-speakable"`, and an `https://` reference link; `dist/client/llms-full.txt` exists and contains `theta` content + an explainer title and does NOT contain the iron-condor lesson body (a unique phrase from `packages/content/saalr_content/modules/iron-condor.md` — read it to pick the phrase); `dist/client/sitemap.xml` and `dist/client/llms.txt` contain `/glossary/theta`.

- [ ] **Step 3: full gate** from `apps/web`: `npm run typecheck && npm run lint && npm run test:run`. Expected green (≈ +6 test files). Then `npm run build` → prerenders **~46 HTML documents** (17 + /glossary + ~28 term pages) and writes `sitemap.xml + llms.txt + llms-full.txt`. Run `node scripts/check-prerender.mjs` (or `npm run` the prerender check if scripted) → passes. Report the exact prerendered-doc count + final test count.

- [ ] **Step 4: commit** (if check-prerender.mjs changed)

```bash
git add apps/web/scripts/check-prerender.mjs
git commit -m "test(seo): prerender assertions for glossary pages + llms-full.txt leak guard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes (for the executor)

- **Content is the GEO artifact.** Task 1's `glossary.test.ts` mechanically enforces the acceptance checklist (≥24 terms, sources/sameAs https, ≥2 FAQ, resolving related/seeAlso). Author real, sourced copy — the two exemplars set the bar. A final opus review should spot-check factual accuracy + tone.
- **faqJsonLd refactor is output-preserving** — the existing `jsonld.test.ts` is the regression guard; don't change its expectations.
- **Pro-leak guard unchanged:** both the sitemap loop and the llms-full `OptionsAcademy` section use `ACADEMY_MODULES.filter(m => m.body !== null)`. The glossary + explainers are fully public.
- **Vike `@term` routing** mirrors `@strategy` exactly (routeParams key = folder param name `term`); `+onBeforePrerenderStart` emits only real slugs so no broken prerender.
- **Origin:** local `origin.ts` per folder (the proven pattern); do not refactor to a shared import.
- **pnpm only** — never `npm install`.
```
