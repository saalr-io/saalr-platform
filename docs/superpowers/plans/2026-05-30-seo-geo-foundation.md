# SEO/GEO Foundation + Strategy Explainers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Vike-powered statically-generated public surface to the existing Vite/React app — 9 strategy-explainer pages with server-rendered payoff + structured Q&A — plus the GEO/SEO essentials (JSON-LD, sitemap, robots, llms.txt, meta/OG).

**Architecture:** Pure, framework-independent modules first (payoff math, content map, JSON-LD/meta builders, sitemap/llms generators) — all TDD'd with no Vike knowledge. Then the Vike integration: SSG for public routes (`/`, `/learn`, `/learn/<slug>`), the existing authed app rebased client-only under `/app/*`. Reuses the React `PayoffChart`.

**Tech Stack:** Vike + vike-react, Vite, React 18, TypeScript, Tailwind, vitest. SSG output is a static dir for CDN hosting.

**Spec:** `docs/superpowers/specs/2026-05-30-seo-geo-foundation-design.md`

**Run web commands from `apps/web/`.** Tailwind tokens available: `bg-canvas/panel`, `border-line`, `text-txt/txtDim/txtFaint`, `text-pos`.

> **Vike version note (Tasks 5–8):** Vike's `+config`/`+Page`/`+Head` API is version-sensitive. The code below targets `vike` + `vike-react` (the standard React integration). If a config detail differs from the installed version, follow https://vike.dev/ — the acceptance criteria (public routes prerender to static HTML containing H1 + JSON-LD + `<svg>`; the authed app works under `/app`) are what must hold, not the exact config lines.

## File structure

```
apps/web/
  src/seo/payoffExpiry.ts            # pure TS expiration payoff
  src/seo/content/strategies.ts      # 9 explainer content entries (typed)
  src/seo/jsonld.ts                  # TechArticle + FAQPage + BreadcrumbList builders
  src/seo/meta.ts                    # <head> meta/OG/canonical builder
  src/seo-build/sitemap.ts           # sitemap.xml generator
  src/seo-build/llms.ts              # llms.txt generator
  scripts/gen-seo.ts                 # post-build: write sitemap.xml + llms.txt
  public/robots.txt                  # static
  vite.config.ts                     # MODIFY: add vike()
  package.json                       # MODIFY: deps + build scripts
  pages/                             # Vike pages (new)
    +config.ts  +Layout.tsx
    index/+Page.tsx
    learn/+Page.tsx
    learn/@strategy/+Page.tsx  learn/@strategy/+onBeforePrerenderStart.ts
    app/+Page.tsx  app/+config.ts  app/+route.ts
  src/main.tsx                       # MODIFY/RETIRE: routing moves into pages/app
  src/components/Sidebar.tsx         # MODIFY: rebase nav links under /app
```

---

## Task 1: Pure expiration-payoff math

**Files:**
- Create: `apps/web/src/seo/payoffExpiry.ts`
- Test: `apps/web/src/seo/payoffExpiry.test.ts`

- [ ] **Step 1: Write failing tests**

Create `apps/web/src/seo/payoffExpiry.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { spotGrid, expirationCurve, breakevens, maxPL, type ExLeg } from './payoffExpiry'

const longCall = (strike: number, entry: number): ExLeg =>
  ({ kind: 'option', option_type: 'CALL', side: 'BUY', strike, qty: 1, entry_price: entry })
const shortCall = (strike: number, entry: number): ExLeg =>
  ({ kind: 'option', option_type: 'CALL', side: 'SELL', strike, qty: 1, entry_price: entry })

describe('payoffExpiry', () => {
  it('bull call spread: bounded, breakeven = long strike + net debit', () => {
    const legs = [longCall(100, 6), shortCall(110, 2)]
    const grid = spotGrid(legs)
    const curve = expirationCurve(legs, grid)
    const m = maxPL(curve)
    expect(m.unboundedProfit).toBe(false)
    expect(m.unboundedLoss).toBe(false)
    expect(m.maxProfit).toBeCloseTo(600, 0)
    expect(m.maxLoss).toBeCloseTo(-400, 0)
    const be = breakevens(curve)
    expect(be).toHaveLength(1)
    expect(be[0]).toBeCloseTo(104, 0)
  })

  it('short call: unbounded loss', () => {
    const legs = [shortCall(100, 5)]
    const m = maxPL(expirationCurve(legs, spotGrid(legs)))
    expect(m.unboundedLoss).toBe(true)
    expect(m.maxLoss).toBeNull()
    expect(m.maxProfit).toBeCloseTo(500, 0)
  })

  it('iron condor: two breakevens, bounded', () => {
    const legs: ExLeg[] = [
      { kind: 'option', option_type: 'PUT', side: 'BUY', strike: 80, qty: 1, entry_price: 1 },
      { kind: 'option', option_type: 'PUT', side: 'SELL', strike: 90, qty: 1, entry_price: 3 },
      { kind: 'option', option_type: 'CALL', side: 'SELL', strike: 110, qty: 1, entry_price: 3 },
      { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 120, qty: 1, entry_price: 1 },
    ]
    const curve = expirationCurve(legs, spotGrid(legs))
    const m = maxPL(curve)
    expect(m.unboundedProfit).toBe(false)
    expect(m.unboundedLoss).toBe(false)
    expect(breakevens(curve).length).toBe(2)
  })
})
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/seo/payoffExpiry.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement payoffExpiry.ts**

Create `apps/web/src/seo/payoffExpiry.ts`:

```ts
export type OptionType = 'CALL' | 'PUT'
export type Side = 'BUY' | 'SELL'
export interface OptionLeg { kind: 'option'; option_type: OptionType; side: Side; strike: number; qty: number; entry_price: number }
export interface EquityLeg { kind: 'equity'; side: Side; qty: number; entry_price: number }
export interface CashLeg { kind: 'cash'; amount: number }
export type ExLeg = OptionLeg | EquityLeg | CashLeg

export interface Pt { spot: number; pnl: number }
const MULT = 100
const TOL = 1e-6
const sign = (s: Side) => (s === 'BUY' ? 1 : -1)

export function spotGrid(legs: ExLeg[], points = 161): number[] {
  const strikes = legs.flatMap((l) => (l.kind === 'option' ? [l.strike] : []))
  const hi = Math.max(100, ...strikes) * 2
  const step = hi / (points - 1)
  const grid = Array.from({ length: points }, (_, i) => i * step)
  for (const s of strikes) if (s >= 0 && s <= hi) grid.push(s)
  return Array.from(new Set(grid)).sort((a, b) => a - b)
}

function legPnl(leg: ExLeg, s: number): number {
  if (leg.kind === 'option') {
    const intrinsic = leg.option_type === 'CALL' ? Math.max(s - leg.strike, 0) : Math.max(leg.strike - s, 0)
    return sign(leg.side) * (intrinsic - leg.entry_price) * MULT * leg.qty
  }
  if (leg.kind === 'equity') return sign(leg.side) * (s - leg.entry_price) * leg.qty
  return 0
}

export function expirationCurve(legs: ExLeg[], grid: number[]): Pt[] {
  return grid.map((spot) => ({ spot, pnl: legs.reduce((a, l) => a + legPnl(l, spot), 0) }))
}

export function breakevens(curve: Pt[]): number[] {
  const out: number[] = []
  for (let i = 0; i < curve.length - 1; i++) {
    const [a, b] = [curve[i], curve[i + 1]]
    if (a.pnl === 0) out.push(a.spot)
    else if ((a.pnl < 0 && b.pnl > 0) || (b.pnl < 0 && a.pnl > 0))
      out.push(a.spot + ((b.spot - a.spot) * (0 - a.pnl)) / (b.pnl - a.pnl))
  }
  return out
}

export interface MaxPL { maxProfit: number | null; maxLoss: number | null; unboundedProfit: boolean; unboundedLoss: boolean }
export function maxPL(curve: Pt[]): MaxPL {
  const pnls = curve.map((p) => p.pnl)
  const rightSlope = curve[curve.length - 1].pnl - curve[curve.length - 2].pnl
  const unboundedProfit = rightSlope > TOL
  const unboundedLoss = rightSlope < -TOL
  return {
    maxProfit: unboundedProfit ? null : Math.max(...pnls),
    maxLoss: unboundedLoss ? null : Math.min(...pnls),
    unboundedProfit,
    unboundedLoss,
  }
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/seo/payoffExpiry.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/seo/payoffExpiry.ts apps/web/src/seo/payoffExpiry.test.ts
git commit -m "feat(seo): pure TS expiration payoff (matches python engine)"
```

---

## Task 2: Explainer content map

**Files:**
- Create: `apps/web/src/seo/content/strategies.ts`
- Test: `apps/web/src/seo/content/strategies.test.ts`

- [ ] **Step 1: Write the validation test**

Create `apps/web/src/seo/content/strategies.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { EXPLAINERS } from './strategies'
import { spotGrid, expirationCurve } from '../payoffExpiry'

const REQUIRED_KEYS = [
  'bull_call_spread', 'bear_put_spread', 'long_straddle', 'long_strangle',
  'iron_condor', 'iron_butterfly', 'covered_call', 'cash_secured_put', 'long_calendar',
]

describe('EXPLAINERS content map', () => {
  it('covers all nine template keys', () => {
    expect(new Set(EXPLAINERS.map((e) => e.key))).toEqual(new Set(REQUIRED_KEYS))
  })

  it('every entry has unique slug + complete required fields + an FAQ', () => {
    const slugs = new Set<string>()
    for (const e of EXPLAINERS) {
      expect(e.slug).toMatch(/^[a-z0-9-]+$/)
      expect(slugs.has(e.slug)).toBe(false)
      slugs.add(e.slug)
      expect(e.title.length).toBeGreaterThan(3)
      expect(e.summary.length).toBeGreaterThan(20)
      expect(e.whenToUse.length).toBeGreaterThan(10)
      expect(e.riskProfile.length).toBeGreaterThan(10)
      expect(['bullish', 'bearish', 'neutral']).toContain(e.category)
      expect(e.faq.length).toBeGreaterThanOrEqual(1)
      for (const f of e.faq) { expect(f.q.length).toBeGreaterThan(3); expect(f.a.length).toBeGreaterThan(10) }
      expect(e.legs.length).toBeGreaterThanOrEqual(1)
    }
  })

  it('every entry produces a non-empty payoff curve', () => {
    for (const e of EXPLAINERS) {
      const curve = expirationCurve(e.legs, spotGrid(e.legs))
      expect(curve.length).toBeGreaterThan(2)
    }
  })
})
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/seo/content/strategies.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the content map**

Create `apps/web/src/seo/content/strategies.ts`. Define the type, then **author all nine entries** to that schema. Two complete exemplars are given; author the remaining seven (`bear_put_spread`, `long_straddle`, `long_strangle`, `iron_butterfly`, `covered_call`, `cash_secured_put`, `long_calendar`) following the same shape — the validation test in Step 1 enforces completeness (all nine keys, unique slugs, non-empty fields, ≥1 FAQ, ≥1 leg). Use accurate, plain-English options content; pick illustrative round-number `entry_price`s consistent with the legs.

```ts
import type { ExLeg } from '../payoffExpiry'

export interface Faq { q: string; a: string }
export interface ExplainerContent {
  key: string
  slug: string
  title: string
  summary: string
  category: 'bullish' | 'bearish' | 'neutral'
  whenToUse: string
  riskProfile: string
  faq: Faq[]
  legs: ExLeg[]
}

const C = (strike: number, side: 'BUY' | 'SELL', entry: number): ExLeg =>
  ({ kind: 'option', option_type: 'CALL', side, strike, qty: 1, entry_price: entry })
const P = (strike: number, side: 'BUY' | 'SELL', entry: number): ExLeg =>
  ({ kind: 'option', option_type: 'PUT', side, strike, qty: 1, entry_price: entry })

export const EXPLAINERS: ExplainerContent[] = [
  {
    key: 'bull_call_spread', slug: 'bull-call-spread', title: 'Bull Call Spread',
    summary: 'A bull call spread buys a call and sells a higher-strike call with the same expiry — a defined-risk, defined-reward bet that the underlying rises moderately.',
    category: 'bullish',
    whenToUse: 'Use it when you are moderately bullish and want to cap cost by giving up upside beyond the short strike. Cheaper than a naked long call.',
    riskProfile: 'Risk is limited to the net debit paid; reward is limited to the strike width minus the debit. Both are known at entry.',
    faq: [
      { q: 'What is the maximum loss on a bull call spread?', a: 'The most you can lose is the net premium (debit) you pay to open the spread, which happens if the underlying finishes at or below the long call strike.' },
      { q: 'When does a bull call spread reach maximum profit?', a: 'Maximum profit is reached at expiration when the underlying is at or above the short (higher) call strike; profit equals the strike width minus the net debit.' },
      { q: 'What is the breakeven of a bull call spread?', a: 'Breakeven at expiration is the long call strike plus the net debit paid.' },
    ],
    legs: [C(100, 'BUY', 6), C(110, 'SELL', 2)],
  },
  {
    key: 'iron_condor', slug: 'iron-condor', title: 'Iron Condor',
    summary: 'An iron condor sells an out-of-the-money put spread and an out-of-the-money call spread — a defined-risk, range-bound income strategy that profits when the underlying stays between the short strikes.',
    category: 'neutral',
    whenToUse: 'Use it when you expect low volatility and a range-bound underlying through expiry, and you want to collect premium with capped risk.',
    riskProfile: 'Risk is limited to the wider spread width minus the net credit; maximum profit is the net credit received, kept if price stays between the short strikes.',
    faq: [
      { q: 'How does an iron condor make money?', a: 'You collect a net credit up front. If the underlying stays between the two short strikes through expiration, all four options expire worthless and you keep the credit.' },
      { q: 'What is the maximum loss on an iron condor?', a: 'The maximum loss is the width of one spread minus the net credit received, incurred if the underlying moves beyond either long strike.' },
      { q: 'Why use an iron condor instead of a short strangle?', a: 'The long wings of an iron condor cap your risk, turning the unlimited risk of a short strangle into a defined, smaller maximum loss.' },
    ],
    legs: [P(80, 'BUY', 1), P(90, 'SELL', 3), C(110, 'SELL', 3), C(120, 'BUY', 1)],
  },
  // TODO(author): add the remaining 7 entries (bear_put_spread, long_straddle, long_strangle,
  // iron_butterfly, covered_call, cash_secured_put, long_calendar) to this same schema.
  // The Step-1 validation test fails until all nine REQUIRED_KEYS are present and complete.
]
```

> This is the one task whose body is content-authoring, not logic: the schema + the Step-1 validation test are the contract. The two exemplars show the exact shape; complete the other seven so the test passes. (For `covered_call` use an equity leg `{ kind: 'equity', side: 'BUY', qty: 100, entry_price: <spot> }` + a short call; for `cash_secured_put` use a short put + `{ kind: 'cash', amount: <strike*100> }`.)

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/seo/content/strategies.test.ts`
Expected: 3 passed (only after all nine entries are authored).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/seo/content/strategies.ts apps/web/src/seo/content/strategies.test.ts
git commit -m "feat(seo): strategy-explainer content map (9 entries) + validation"
```

---

## Task 3: JSON-LD + meta builders

**Files:**
- Create: `apps/web/src/seo/jsonld.ts`, `apps/web/src/seo/meta.ts`
- Test: `apps/web/src/seo/jsonld.test.ts`

- [ ] **Step 1: Write failing tests**

Create `apps/web/src/seo/jsonld.test.ts`:

```ts
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
    const j = articleJsonLd(content, 'https://saalr.com/learn/bull-call-spread')
    expect(j['@context']).toBe('https://schema.org')
    expect(j['@type']).toBe('TechArticle')
    expect(j.headline).toBe('Bull Call Spread')
    expect(j.url).toContain('/learn/bull-call-spread')
  })

  it('faqJsonLd maps each FAQ to a Question/Answer', () => {
    const j = faqJsonLd(content)
    expect(j['@type']).toBe('FAQPage')
    expect(j.mainEntity).toHaveLength(1)
    expect(j.mainEntity[0]['@type']).toBe('Question')
    expect(j.mainEntity[0].acceptedAnswer['@type']).toBe('Answer')
    expect(j.mainEntity[0].acceptedAnswer.text).toContain('net debit')
  })

  it('breadcrumbJsonLd builds an itemListElement', () => {
    const j = breadcrumbJsonLd([{ name: 'Learn', url: '/learn' }, { name: 'Bull Call Spread', url: '/learn/bull-call-spread' }])
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
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/seo/jsonld.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement jsonld.ts + meta.ts**

Create `apps/web/src/seo/jsonld.ts`:

```ts
import type { ExplainerContent } from './content/strategies'

export function articleJsonLd(c: ExplainerContent, url: string): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'TechArticle',
    headline: c.title,
    description: c.summary,
    url,
    articleSection: 'Options strategies',
    about: c.title,
  }
}

export function faqJsonLd(c: ExplainerContent): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: c.faq.map((f) => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a },
    })),
  }
}

export function breadcrumbJsonLd(trail: { name: string; url: string }[]): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((t, i) => ({ '@type': 'ListItem', position: i + 1, name: t.name, item: t.url })),
  }
}
```

Create `apps/web/src/seo/meta.ts`:

```ts
export interface PageMeta {
  title: string
  description: string
  canonical: string
  og: Record<string, string>
  twitter: Record<string, string>
}

export function pageMeta(input: { title: string; description: string; canonical: string; image?: string }): PageMeta {
  const og: Record<string, string> = {
    'og:title': input.title,
    'og:description': input.description,
    'og:type': 'article',
    'og:url': input.canonical,
  }
  if (input.image) og['og:image'] = input.image
  return {
    title: input.title,
    description: input.description,
    canonical: input.canonical,
    og,
    twitter: { 'twitter:card': 'summary_large_image', 'twitter:title': input.title, 'twitter:description': input.description },
  }
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/seo/jsonld.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/seo/jsonld.ts apps/web/src/seo/meta.ts apps/web/src/seo/jsonld.test.ts
git commit -m "feat(seo): JSON-LD (TechArticle/FAQPage/Breadcrumb) + meta builders"
```

---

## Task 4: Sitemap + llms.txt generators

**Files:**
- Create: `apps/web/src/seo-build/sitemap.ts`, `apps/web/src/seo-build/llms.ts`
- Test: `apps/web/src/seo-build/seoBuild.test.ts`

- [ ] **Step 1: Write failing tests**

Create `apps/web/src/seo-build/seoBuild.test.ts`:

```ts
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
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run src/seo-build/seoBuild.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement sitemap.ts + llms.ts**

Create `apps/web/src/seo-build/sitemap.ts`:

```ts
export function buildSitemap(site: string, urls: string[]): string {
  const entries = urls
    .map((u) => `  <url>\n    <loc>${site}${u}</loc>\n  </url>`)
    .join('\n')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries}\n</urlset>\n`
}
```

Create `apps/web/src/seo-build/llms.ts`:

```ts
export interface LlmsPage { url: string; title: string; description: string }

export function buildLlmsTxt(site: string, name: string, summary: string, pages: LlmsPage[]): string {
  const lines = pages.map((p) => `- [${p.title}](${site}${p.url}): ${p.description}`)
  return `# ${name}\n\n${summary}\n\n## Pages\n\n${lines.join('\n')}\n`
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run src/seo-build/seoBuild.test.ts`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/seo-build/ apps/web/src/seo-build/seoBuild.test.ts
git commit -m "feat(seo): sitemap.xml + llms.txt generators"
```

---

## Task 5: Vike install + config + layout + public home + `/app` rebase

**Files:**
- Modify: `apps/web/package.json`, `apps/web/vite.config.ts`, `apps/web/src/components/Sidebar.tsx`
- Create: `apps/web/pages/+config.ts`, `+Layout.tsx`, `index/+Page.tsx`, `app/+Page.tsx`, `app/+config.ts`, `app/+route.ts`
- Modify/retire: `apps/web/src/main.tsx`

> This is the framework-integration task. Verify config specifics against https://vike.dev/ for the installed version. **Acceptance criteria:** `pnpm build` prerenders `/` to `dist/client/index.html` (contains real HTML, not an empty `<div id="root">`); the existing authed app loads under `/app/*`; the existing app test suite still passes.

- [ ] **Step 1: Install Vike**

Run: `cd apps/web && pnpm add vike vike-react`

- [ ] **Step 2: Add the Vike plugin** — in `apps/web/vite.config.ts`, add `import vike from 'vike/plugin'` and put `vike()` in `plugins` after `react()`. Keep the `server.proxy` and `test` blocks unchanged.

- [ ] **Step 3: Global config** — create `apps/web/pages/+config.ts`:

```ts
import vikeReact from 'vike-react/config'
import type { Config } from 'vike/types'

export default {
  extends: vikeReact,
  prerender: true,
  title: 'Saalr — research-grade options analytics',
} satisfies Config
```

- [ ] **Step 4: Shared layout** — create `apps/web/pages/+Layout.tsx` that renders children inside the app's theme wrapper and imports `../src/index.css` (the existing global stylesheet). Keep it minimal (a `<div className="min-h-screen bg-canvas text-txt">{children}</div>`).

- [ ] **Step 5: Public home stub** — create `apps/web/pages/index/+Page.tsx`: a small server-rendered landing with an `<h1>Saalr</h1>`, a one-paragraph description, a link to `/learn`, and a "Go to app" link to `/app`. Plain semantic HTML (real `<a>` tags).

- [ ] **Step 6: Authed app under `/app`** — create:
  - `apps/web/pages/app/+config.ts`: `export default { ssr: false, prerender: false }`
  - `apps/web/pages/app/+route.ts`: `export default '/app/@@rest'` (catch-all so client-side routing owns `/app/*`; adjust to the installed Vike's catch-all syntax if different)
  - `apps/web/pages/app/+Page.tsx`: mounts the existing React app — wrap the current `<Routes>` from `main.tsx` in a `<BrowserRouter basename="/app">` and render `<AuthProvider>` + the route table (Dashboard, markets, strategies, models, etc.) exactly as before. Move the routing JSX out of `src/main.tsx` into this page (or a `src/app/Router.tsx` that both can import). Keep `RequireAuth`, `AuthProvider`, all existing pages unchanged.

- [ ] **Step 7: Retire the old SPA entry** — `src/main.tsx` is replaced by Vike's entry. If anything still imports it, remove the dangling `ReactDOM.createRoot` bootstrap (Vike renders pages). The `index.html` at app root is also superseded by Vike's generated HTML; delete `apps/web/index.html` if Vike requires it gone (per vike.dev), otherwise leave it.

- [ ] **Step 8: Rebase nav links** — in `apps/web/src/components/Sidebar.tsx`, change the `SECTIONS` route targets from `'/'`, `'/markets'`, `'/strategies'`, … to `'/app'`, `'/app/markets'`, `'/app/strategies'`, … (and the `end={to === '/'}` becomes `end={to === '/app'}`). Update any login/magic-link redirect target (`web_base_url`-driven or hardcoded `/`) that should now land on `/app`.

- [ ] **Step 9: Build + verify**

Run: `cd apps/web && pnpm build`
Expected: build succeeds; `apps/web/dist/client/index.html` exists and contains `<h1>Saalr</h1>` (server-rendered), not just an empty root div.
Run: `cd apps/web && pnpm test:run`
Expected: existing suite still passes (fix any import paths broken by the main.tsx move).

- [ ] **Step 10: Commit**

```bash
git add apps/web/package.json apps/web/pnpm-lock.yaml apps/web/vite.config.ts apps/web/pages apps/web/src/main.tsx apps/web/src/components/Sidebar.tsx
git commit -m "feat(seo): adopt Vike — SSG public routes + authed app under /app"
```

---

## Task 6: Learn index + explainer pages

**Files:**
- Create: `apps/web/pages/learn/+Page.tsx`, `apps/web/pages/learn/@strategy/+Page.tsx`, `apps/web/pages/learn/@strategy/+onBeforePrerenderStart.ts`
- Test: `apps/web/pages/learn/explainer.test.tsx`

- [ ] **Step 1: Write a render test for the explainer page body**

Create `apps/web/pages/learn/explainer.test.tsx` (renders the explainer body component directly, no Vike runtime):

```tsx
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
```

- [ ] **Step 2: Run to verify fail**

Run: `cd apps/web && pnpm test:run pages/learn/explainer.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement the article component + pages**

Create `apps/web/pages/learn/@strategy/ExplainerArticle.tsx` — a pure presentational component (no Vike imports) that the page and the test both use:

```tsx
import { PayoffChart } from '../../../src/features/strategies/PayoffChart'
import { spotGrid, expirationCurve, breakevens, maxPL } from '../../../src/seo/payoffExpiry'
import { articleJsonLd, faqJsonLd, breadcrumbJsonLd } from '../../../src/seo/jsonld'
import type { ExplainerContent } from '../../../src/seo/content/strategies'

export function ExplainerArticle({ content, origin }: { content: ExplainerContent; origin: string }) {
  const url = `${origin}/learn/${content.slug}`
  const grid = spotGrid(content.legs)
  const curve = expirationCurve(content.legs, grid)
  const m = maxPL(curve)
  const be = breakevens(curve)
  const jsonld = [
    articleJsonLd(content, url),
    faqJsonLd(content),
    breadcrumbJsonLd([{ name: 'Learn', url: `${origin}/learn` }, { name: content.title, url }]),
  ]
  return (
    <article className="mx-auto max-w-3xl p-6">
      <nav className="mb-2 text-xs text-txtDim"><a href="/learn">Learn</a> / {content.title}</nav>
      <h1 className="text-2xl font-semibold">{content.title}</h1>
      <p className="mt-2 text-txtDim">{content.summary}</p>
      <div className="mt-4">
        <PayoffChart expirationCurve={curve.map((p) => ({ spot: p.spot, pnl: p.pnl }))} breakevens={be} />
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <dt className="text-txtFaint">Max profit</dt><dd>{m.unboundedProfit ? 'Unbounded' : m.maxProfit?.toFixed(0)}</dd>
        <dt className="text-txtFaint">Max loss</dt><dd>{m.unboundedLoss ? 'Unbounded' : m.maxLoss?.toFixed(0)}</dd>
        <dt className="text-txtFaint">Breakeven(s)</dt><dd>{be.map((b) => b.toFixed(1)).join(', ') || '—'}</dd>
      </dl>
      <h2 className="mt-6 text-lg font-semibold">When to use</h2>
      <p className="text-txtDim">{content.whenToUse}</p>
      <h2 className="mt-6 text-lg font-semibold">Risk profile</h2>
      <p className="text-txtDim">{content.riskProfile}</p>
      <h2 className="mt-6 text-lg font-semibold">FAQ</h2>
      {content.faq.map((f, i) => (
        <section key={i} className="mt-3">
          <h3 className="font-medium">{f.q}</h3>
          <p className="text-txtDim">{f.a}</p>
        </section>
      ))}
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonld) }} />
    </article>
  )
}
```

Create `apps/web/pages/learn/@strategy/+Page.tsx` — reads the route param, finds the content, renders `<ExplainerArticle>`, and sets the page `<Head>`/title via vike-react (`+Head` or the `usePageContext` documented mechanism); origin from an env/config constant (`https://saalr.com` default). Create `apps/web/pages/learn/@strategy/+onBeforePrerenderStart.ts`:

```ts
import { EXPLAINERS } from '../../../src/seo/content/strategies'
export function onBeforePrerenderStart() {
  return EXPLAINERS.map((e) => `/learn/${e.slug}`)
}
```

Create `apps/web/pages/learn/+Page.tsx` — a server-rendered index listing all `EXPLAINERS` as links (`<a href={`/learn/${e.slug}`}>{e.title}</a>`) grouped by category, with an H1 and intro paragraph.

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/web && pnpm test:run pages/learn/explainer.test.tsx`
Expected: passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/pages/learn
git commit -m "feat(seo): /learn index + strategy explainer pages (payoff + JSON-LD)"
```

---

## Task 7: robots.txt + sitemap/llms build wiring

**Files:**
- Create: `apps/web/public/robots.txt`, `apps/web/scripts/gen-seo.ts`
- Modify: `apps/web/package.json` (build script)

- [ ] **Step 1: robots.txt** — create `apps/web/public/robots.txt`:

```
User-agent: *
Allow: /
Disallow: /app
Disallow: /api
Sitemap: https://saalr.com/sitemap.xml
```

- [ ] **Step 2: gen-seo script** — create `apps/web/scripts/gen-seo.ts` that imports `buildSitemap`/`buildLlmsTxt` and `EXPLAINERS`, assembles the public page list (`/`, `/learn`, and `/learn/<slug>`×9), and writes `dist/client/sitemap.xml` + `dist/client/llms.txt`:

```ts
import { writeFileSync } from 'node:fs'
import { buildSitemap } from '../src/seo-build/sitemap'
import { buildLlmsTxt } from '../src/seo-build/llms'
import { EXPLAINERS } from '../src/seo/content/strategies'

const SITE = process.env.SITE_ORIGIN ?? 'https://saalr.com'
const pages = [
  { url: '/', title: 'Saalr', description: 'Research-grade options analytics for retail traders.' },
  { url: '/learn', title: 'Learn options strategies', description: 'Explainers for common options strategies.' },
  ...EXPLAINERS.map((e) => ({ url: `/learn/${e.slug}`, title: e.title, description: e.summary })),
]
writeFileSync('dist/client/sitemap.xml', buildSitemap(SITE, pages.map((p) => p.url)))
writeFileSync('dist/client/llms.txt', buildLlmsTxt(SITE, 'Saalr', 'Research-grade options analytics for retail traders.', pages))
console.log(`wrote sitemap.xml + llms.txt (${pages.length} pages)`)
```

- [ ] **Step 3: Wire the build script** — in `apps/web/package.json`, change `"build"` so the SEO generator runs after the Vike build, e.g. `"build": "vike build && tsx scripts/gen-seo.ts"` (add `tsx` as a devDependency: `pnpm add -D tsx`). If the project already runs TS scripts a particular way, match it.

- [ ] **Step 4: Build + verify the artifacts**

Run: `cd apps/web && pnpm build`
Expected: `dist/client/sitemap.xml` contains `<loc>https://saalr.com/learn/bull-call-spread</loc>`; `dist/client/llms.txt` lists the learn pages; `dist/client/robots.txt` was copied from `public/`.

- [ ] **Step 5: Commit**

```bash
git add apps/web/public/robots.txt apps/web/scripts/gen-seo.ts apps/web/package.json apps/web/pnpm-lock.yaml
git commit -m "feat(seo): robots.txt + build-time sitemap.xml & llms.txt"
```

---

## Task 8: Prerender smoke + full gate

**Files:**
- Create: `apps/web/scripts/check-prerender.mjs`

- [ ] **Step 1: Prerender smoke check** — create `apps/web/scripts/check-prerender.mjs`:

```js
import { readFileSync } from 'node:fs'
const html = readFileSync('dist/client/learn/bull-call-spread/index.html', 'utf8')
const checks = [['<h1', html.includes('<h1')], ['Bull Call Spread', html.includes('Bull Call Spread')],
  ['ld+json', html.includes('application/ld+json')], ['<svg', html.includes('<svg')]]
const failed = checks.filter(([, ok]) => !ok)
if (failed.length) { console.error('prerender smoke FAILED:', failed.map(([n]) => n)); process.exit(1) }
console.log('prerender smoke OK')
```

- [ ] **Step 2: Run the smoke against a fresh build**

Run: `cd apps/web && pnpm build && node scripts/check-prerender.mjs`
Expected: `prerender smoke OK` (the explainer page prerendered with H1 + JSON-LD + SVG).

- [ ] **Step 3: Full web gate**

Run: `cd apps/web && pnpm test:run`
Expected: all suites pass (SEO units + existing app tests).
Run: `cd apps/web && pnpm typecheck`
Expected: no errors.
Run: `cd apps/web && pnpm lint`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/web/scripts/check-prerender.mjs
git commit -m "test(seo): prerender smoke check + full gate green"
```

---

## Self-review checklist (completed)

- **Spec coverage:** payoffExpiry (T1), content map ×9 (T2), JSON-LD TechArticle+FAQPage+Breadcrumb & meta (T3), sitemap+llms (T4), Vike SSG + `/app` rebase + home stub (T5), `/learn` index + explainer pages with server-rendered payoff (T6), robots + build wiring (T7), prerender smoke + gate (T8). All spec sections covered.
- **Placeholder scan:** the only non-literal-code task is T2 (content authoring) — explicitly a schema + machine-checked validation contract with two complete exemplars, which is the correct shape for content data, not a logic placeholder. T5/T6 Vike config is concrete with a documented "verify against vike.dev" escape hatch because the API is version-sensitive and unrunnable here.
- **Type consistency:** `ExLeg`/`OptionLeg`, `ExplainerContent`, `Pt`, `MaxPL`, `PageMeta`, the JSON-LD builder signatures, and `EXPLAINERS` are used consistently across tasks; `ExplainerArticle` consumes `payoffExpiry` + `jsonld` exactly as defined; `PayoffChart` is reused with its existing `{expirationCurve, breakevens}` props.

## Known risks / notes for the implementer

- **Vike API drift (T5–T7):** the biggest unknown. If `+route.ts` catch-all syntax, `+Head`, or `onBeforePrerenderStart` differ in the installed version, follow vike.dev; the acceptance criteria (prerendered HTML with H1/JSON-LD/SVG; app under `/app`) are the contract.
- **`/app` rebase ripple:** any test or code that navigates to `/strategies` etc. must move to `/app/strategies`; the existing app tests render components directly (not via the router), so they should be unaffected, but check `main.tsx`-dependent imports.
- **`PayoffChart` server rendering:** it uses `useState` for hover — fine for `renderToStaticMarkup`/SSG (renders initial state; hover hydrates client-side). The SVG is in the static HTML, which is what crawlers/LLMs read.
- **Origin constant:** `https://saalr.com` is the assumed production origin for canonical/sitemap; override via `SITE_ORIGIN` env in the build. Adjust if the real domain differs.
```
