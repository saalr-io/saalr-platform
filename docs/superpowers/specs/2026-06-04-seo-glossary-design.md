# SEO/GEO — Glossary surface + llms-full.txt — design

**Status:** approved design, 2026-06-04. Next increment on the SEO/GEO foundation (Vike SSG
landing + `/learn/*` explainers + `/academy/*` lessons + `sitemap.xml`/`llms.txt`/`robots.txt`,
all shipped in PR #1). Informed by the `seo-geo` skill (Princeton GEO methods).

## Goal

Add a crawlable, AI-citable **options glossary** at `/glossary` (index) + `/glossary/<term>`
(per-term), prerendered SSG, with `DefinedTermSet` / `DefinedTerm` / `FAQPage` / `BreadcrumbList`
JSON-LD; **plus an `llms-full.txt`** — a full-content dump of the public learning surface
(explainers + free academy lessons + glossary) for direct AI/LLM ingestion. Wire both into the
existing build (`sitemap.xml` / `llms.txt`), and make AI-crawler access explicit in `robots.txt`.

## GEO rationale (from the seo-geo skill) — this slice is GEO-first

AI engines cite sources rather than rank pages; being cited is the goal. This glossary is
engineered around the skill's highest-scoring Princeton GEO methods, in priority order:

- **Cite Sources → +40%.** EVERY term carries ≥1 authoritative reference (CBOE Options Institute,
  the OCC, SEC investor.gov, or a primary source such as the Black–Scholes paper for the Greeks),
  rendered as a per-term "References" section (external links, `rel="noopener noreferrer"`) and woven
  into copy ("Per the OCC, assignment is random…"). This is the single biggest citation lever and the
  one most glossaries omit.
- **Entity linking via `sameAs` → disambiguation.** Each `DefinedTerm` JSON-LD includes a `sameAs`
  array pointing at the canonical concept (Wikipedia / Investopedia), so engines map "theta" to the
  known options-Greek entity rather than guessing. Strong, low-cost GEO signal.
- **FAQPage schema → +40% AI visibility.** Every term page carries a 2–3 Q&A `FAQPage`, answer-first,
  each answer citing a number and/or a source ("According to the CBOE, …").
- **`speakable` (SpeakableSpecification) → voice / read-aloud surfacing.** Each term page emits a
  `WebPage` node whose `speakable.cssSelector` points at the answer-first definition + the FAQ, marking
  exactly the spans a voice assistant or AI read-aloud should quote — the self-contained, citable bits.
- **Statistics Addition → +37%.** Every definition states concrete numbers (delta 0→1; theta as $/day;
  a 0.30-delta call ≈ $0.30 per $1 move).
- **Authoritative tone → +25% / Technical terms → +18% / Fluency.** Confident, precise, correctly-
  termed prose in short 2–3-sentence paragraphs. The top-scoring combination is Fluency + Statistics.
- **Answer-first structure.** H1 (term) → one-sentence direct definition (`short`) → expansion.
- **No keyword stuffing** (the skill's only negative lever, −10%).
- **AI-crawler access made explicit** in `robots.txt` (GPTBot, ChatGPT-User, ClaudeBot, anthropic-ai,
  PerplexityBot, Google-Extended, Bingbot).
- **`llms-full.txt`** — hands engines the full text (incl. the References) directly.

### GEO acceptance checklist (every term must satisfy)

1. Answer-first `short` ≤ 1 sentence, definitionally complete on its own.
2. ≥ 1 concrete statistic/number in the body or an FAQ answer.
3. ≥ 1 authoritative `sources` entry (https, reputable: CBOE / OCC / SEC / Investopedia / Wikipedia /
   a primary paper) + ≥ 1 `sameAs` canonical entity URL.
4. 2–3 FAQ Q&As, each answer-first; at least one answer cites a number or a source.
5. Correct technical terminology; confident tone; no filler, no keyword repetition.

## Content model — `src/seo/content/glossary.ts`

```ts
export interface GlossaryFaq { q: string; a: string }
export interface GlossarySource { label: string; url: string }  // authoritative reference
export interface GlossaryTerm {
  slug: string          // 'theta'  (URL + DOM id)
  term: string          // 'Theta'
  short: string         // one-sentence answer-first definition (DefinedTerm.description, OG, lists)
  definition: string[]  // 2-3-sentence paragraphs (plain strings → <p>; XSS-safe, no markdown dep)
  example?: string      // a concrete worked example with numbers
  related: string[]     // other term slugs (must resolve)
  seeAlso?: string       // an EXPLAINER slug (must resolve), e.g. 'covered-call'
  faq: GlossaryFaq[]     // 2-3 answer-first Q&As → FAQPage JSON-LD
  sources: GlossarySource[]  // ≥1 authoritative reference (Cite Sources, +40% GEO) → "References" + llms-full.txt
  sameAs: string[]           // ≥1 canonical entity URL (Wikipedia/Investopedia) → DefinedTerm.sameAs
}
export const GLOSSARY: GlossaryTerm[]  // ~28 core terms
```

**Terms (~28):** call, put, strike, expiration, premium, intrinsic-value, extrinsic-value,
in-the-money, out-of-the-money, at-the-money, moneyness, implied-volatility,
historical-volatility, iv-rank, delta, gamma, theta, vega, rho, the-greeks, open-interest,
volume, bid-ask-spread, assignment, exercise, american-vs-european, break-even, put-call-parity.
Copy is authored answer-first to the GEO acceptance checklist above — numbers, correct terminology,
authoritative tone — each term ≤ ~120 words of body + an example + 2–3 FAQ Q&As + `sources` + `sameAs`.

## JSON-LD — extend `src/seo/jsonld.ts`

- `definedTermSetJsonLd(origin, terms)` → `DefinedTermSet` (`name`, `url: ${origin}/glossary`,
  `hasDefinedTerm`: one `DefinedTerm` per term with `name`/`description`/`url`).
- `definedTermJsonLd(term, url, setUrl)` → `DefinedTerm` with `name`/`description`/`url`/
  `inDefinedTermSet: setUrl`/`termCode: term.slug`/**`sameAs: term.sameAs`** (entity disambiguation).
- `faqPageJsonLd(items: {q,a}[])` → `FAQPage` (generalized; the existing `faqJsonLd(c)` is
  refactored to delegate to it so explainers are unchanged in output).
- `speakableWebPageJsonLd(url, name, description, cssSelector)` → `WebPage` with
  `speakable: { '@type': 'SpeakableSpecification', cssSelector }` (default selector `['.geo-speakable']`).
- Reuse the existing `breadcrumbJsonLd(trail)`.

JSON-LD is rendered as a body `<script type="application/ld+json" dangerouslySetInnerHTML>` array,
mirroring `pages/learn/@strategy/ExplainerArticle.tsx`.

## Pages (mirror `/learn`) — under `apps/web/pages/glossary/`

- **Index** `+Page.tsx` / `+Head.tsx` / `+title.ts` / `+description.ts`:
  - `+Page` renders an H1, intro, an alphabetical term list (`<a href="/glossary/${slug}">{term}</a>`
    + `short`), a "Back to Learn" link, and a body script with `[definedTermSetJsonLd, breadcrumb]`.
  - `+Head` emits `pageMeta({ title:'Options glossary — SAALR', description, canonical:${ORIGIN}/glossary })`
    → canonical + OG + twitter (same shape as the learn index/explainer Heads).
- **Per-term** `@term/+Page.tsx` / `+Head.tsx` / `+title.ts` / `+description.ts` / `+onBeforePrerenderStart.ts`:
  - `+onBeforePrerenderStart` returns `GLOSSARY.map(t => `/glossary/${t.slug}`)`.
  - `+Page` finds the term by `routeParams.term`; unknown → a "Not found / back to glossary"
    fallback (same shape as the explainer 404). For a real term: H1 = `term`, immediately followed
    by `short` (answer-first) **in a `<p className="geo-speakable">`**, then `definition` paragraphs,
    an "Example" block, a "Related terms" list (→ `/glossary/<related>`), an optional
    "See also: <Explainer title>" link (→ `/learn/<seeAlso>`), the FAQ rendered in a
    **`<section className="geo-speakable">`** (so `speakable` covers both the lead definition and the
    Q&As), a **"References" section** (`term.sources` as external links, `rel="noopener noreferrer"`,
    with visible attribution labels), and a body script with `[definedTermJsonLd (incl. sameAs),
    faqPageJsonLd(term.faq), speakableWebPageJsonLd(url, `${term} — SAALR options glossary`, short,
    ['.geo-speakable']), breadcrumb(Home→Glossary→Term)]`.
  - `+Head` emits `pageMeta({ title:`${term} — SAALR options glossary`, description: short,
    canonical:${ORIGIN}/glossary/${slug} })`.
  - Reuse the established `ORIGIN` helper (mirror how `pages/learn/@strategy/` imports it).

## llms-full.txt — extend `src/seo-build/llms.ts` + `scripts/gen-seo.ts`

- New pure builder `buildLlmsFullTxt(site, name, summary, sections)` where
  `LlmsFullSection = { heading: string; entries: { title: string; url: string; body: string }[] }`.
  Output: a markdown-ish document — title + summary + `Site:` + a pointer to `llms.txt` (index),
  then per section `## {heading}` and per entry `### {title}\nURL: {site}{url}\n\n{body}`.
- New pure serializers (also in `src/seo-build/llms.ts`, testable):
  - `explainerToText(e)` → `summary` + `When to use: …` + `Risk profile: …` + `FAQ:` Q/A lines.
  - `glossaryTermToText(t)` → `short` + definition paragraphs + `Example: …` + FAQ Q/A lines +
    `References:` lines (`{label}: {url}`) — the citations travel into the AI-ingested dump too.
  - academy bodies are already markdown text (used as-is).
- `scripts/gen-seo.ts`: build three sections — Options strategies (`EXPLAINERS`), OptionsAcademy
  (`ACADEMY_MODULES.filter(m => m.body !== null)` — **the same Pro-leak guard as the sitemap**),
  Glossary (`GLOSSARY`) — and `writeFileSync('dist/client/llms-full.txt', buildLlmsFullTxt(...))`.
  Also append the `/glossary` + every `/glossary/<term>` URL to the existing `pages` array (so they
  enter `sitemap.xml` + `llms.txt`). Add a `See also: {site}/llms-full.txt` line to the `llms.txt`
  header (small change to `buildLlmsTxt` or its caller).

## robots.txt — `apps/web/public/robots.txt`

Keep `User-agent: * / Allow: / / Disallow: /app / Disallow: /api / Sitemap: …`, and **add explicit
named stanzas** for `GPTBot`, `ChatGPT-User`, `ClaudeBot`, `anthropic-ai`, `PerplexityBot`,
`Google-Extended`, `Bingbot` — each `Allow: /` + `Disallow: /app` + `Disallow: /api`. (All are
already allowed via `*`; this is an explicit "please crawl & cite" signal.)

## Internal linking (bounded — no explainer-body rewrites)

`/learn` index → a one-line link to `/glossary`. Per-term → related terms + `seeAlso` explainer.
(Explainer-body deep-linking into glossary terms and a shared nav are out of scope.)

## Error handling

Unknown `/glossary/<term>` → "Not found, back to the glossary" page (mirrors the explainer 404);
`+onBeforePrerenderStart` only emits real slugs, so no broken prerenders. `buildLlmsFullTxt`
includes only `body !== null` academy modules → no Pro lesson body in the dump.

## Testing (vitest + the existing prerender smoke)

- `glossary.test.ts` — **GEO acceptance checklist enforced as tests**: slugs unique; every `related`
  resolves to a real term; every `seeAlso` resolves to a real `EXPLAINER` slug; `short`/`definition`/
  `faq` non-empty; **every term has ≥1 `sources` entry with an `https://` url, and ≥1 `sameAs`
  `https://` url**; every term has ≥2 FAQ Q&As. (A failing term fails the build via the test gate —
  the checklist can't silently rot.)
- `glossaryJsonLd.test.ts` — `DefinedTermSet.hasDefinedTerm.length === GLOSSARY.length`; each
  `DefinedTerm` has `inDefinedTermSet` **and a non-empty `sameAs`**;
  `faqPageJsonLd(term.faq).mainEntity.length === term.faq.length`;
  **`speakableWebPageJsonLd(...)` is a `WebPage` whose `speakable['@type'] === 'SpeakableSpecification'`
  with a non-empty `cssSelector` (default `['.geo-speakable']`)**; the refactored `faqJsonLd` output is
  unchanged for an explainer (snapshot/shape assert); breadcrumb positions 1..n.
- `llmsFull.test.ts` — `buildLlmsFullTxt` includes an explainer title + a glossary term's definition
  text; `explainerToText`/`glossaryTermToText` include the FAQ answers; `glossaryTermToText` includes a
  `sources` reference URL (citations travel into the dump); a Pro academy body string is ABSENT when
  only `body !== null` entries are passed (leak guard).
- Prerender assertions (extend `scripts/check-prerender.mjs` or the prerender test):
  `dist/client/glossary/index.html` and a sample `dist/client/glossary/<term>/index.html` exist and
  contain the term text + `application/ld+json` + a `sameAs`/References external link + a
  `class="geo-speakable"` element (so the `speakable.cssSelector` resolves against real prerendered DOM);
  `dist/client/llms-full.txt` exists and contains a
  glossary term + an explainer, and does NOT contain the iron-condor (Pro) lesson body; the glossary
  URLs appear in `sitemap.xml` + `llms.txt`.
- Gate: `npm run typecheck && npm run lint && npm run test:run` green (≈ +6 tests); `npm run build`
  prerenders **17 → ~46** docs (all public — the academy Pro-leak guard is unchanged).

## Out of scope (later)

sitemap `<lastmod>`; OG images (per-page or default); article `datePublished`/`dateModified`/
`author`/`publisher`/`inLanguage`; `WebSite` `SearchAction`; comparison pages; explainer-body
deep-linking into glossary terms; a shared public nav; per-term payoff diagrams.
