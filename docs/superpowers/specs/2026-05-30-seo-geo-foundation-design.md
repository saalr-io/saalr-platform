# SEO/GEO foundation + strategy explainers — design

**Date:** 2026-05-30
**Slice:** SEO/GEO public-surface (first slice). Makes Saalr visible to search engines and
generative engines (ChatGPT/Perplexity/Gemini/Google AI) by adding a statically-generated
public surface to the currently client-only SPA.
**Status:** Approved design, pre-plan.
**Builds on:** the React web app (`apps/web/`), the strategy builder UI (7b: `PayoffChart`),
and the 7a templates catalog.

## Purpose

The web app is a pure client-side SPA, so crawlers and AI engines see an empty shell — zero
SEO, zero GEO. This slice adds **Vike-powered static generation (SSG)** for public pages and
ships the first high-value content: **nine strategy-explainer pages** (one per ready-made
template) with a server-rendered payoff diagram and structured Q&A, plus the GEO/SEO essentials
(JSON-LD, meta/OG, `sitemap.xml`, `robots.txt`, `llms.txt`).

The authenticated app is **not** an SEO target and stays client-only and behavior-unchanged.

## Decisions (locked during brainstorming)

1. **Framework = Vike (SSG) in the existing Vite/React app** — one codebase/deploy, direct
   reuse of React components (`PayoffChart`) + TS types. (Astro and a thin prerender plugin
   were the considered alternatives.)
2. **Rendering = static generation (SSG)** to a static directory hostable on a CDN/S3 — content
   is non-personal and static; no Node SSR server required.
3. **Scope = foundation + strategy explainers.** Marketing landing and OptionsAcademy education
   are deferred to fast-follow slices. A minimal real `/` home stub is included so the root
   isn't an empty shell.
4. **Explainer payoff is computed at build in pure TS** from hand-picked illustrative legs — no
   backend dependency at build, deterministic, crawlable.

## Architecture

Adopt Vike: routing moves from `main.tsx`'s `<BrowserRouter>` into Vike pages. Public routes
prerender to static HTML; the authed app is a client-only Vike page wrapping the existing React
Router subtree.

```
apps/web/
  vite.config.ts                 # MODIFY: add vike() plugin
  package.json                   # MODIFY: add vike + build/prerender scripts
  pages/                         # Vike pages (file-based)
    +config.ts                   # global config (prerender on, title default)
    +Layout.tsx                  # shared <html> shell, theme, fonts
    index/+Page.tsx              # public home stub (prerender)
    learn/+Page.tsx              # /learn index of explainers (prerender)
    learn/@strategy/+Page.tsx    # /learn/<slug> explainer (prerender, one per template)
    learn/@strategy/+onBeforePrerenderStart.ts  # enumerate the 9 slugs to prerender
    app/+Page.tsx                # authed SPA mount (ssr:false) — renders existing AppShell/router
    app/+config.ts               # ssr:false (client-only)
  src/                           # EXISTING app code (unchanged)
    seo/
      content/strategies.ts      # the 9 explainer content entries
      payoffExpiry.ts            # pure TS expiration payoff (curve/breakevens/maxPL)
      jsonld.ts                  # JSON-LD builders (TechArticle + FAQPage + BreadcrumbList)
      meta.ts                    # <head> meta/OG/canonical builder
    seo-build/
      sitemap.ts                 # sitemap.xml generator (from route+content list)
      llms.ts                    # llms.txt generator
  public/robots.txt              # static (allow public, disallow /api + /app, link sitemap)
  scripts/gen-seo.ts             # writes sitemap.xml + llms.txt into the build output
```

> The existing `src/pages`, `src/features`, `src/components`, `AuthContext`, `RequireAuth`,
> `tokenStore` are reused as-is. The authed routes move under `/app/*` (client-only) or are
> mounted by `app/+Page.tsx`; public SEO routes are new.

### Routing boundary
- **Prerendered (public):** `/`, `/learn`, `/learn/<slug>` (×9).
- **Client-only (authed, `ssr:false`):** the existing app, **rebased under `/app/*`** (today's
  root dashboard `/` and `/strategies`, `/markets`, … become `/app`, `/app/strategies`,
  `/app/markets`, …). This is required because the public landing now owns `/`. Concrete ripples
  (in scope): the `Sidebar` NavLink targets and the React Router `basename`/route paths move to
  `/app`; `RequireAuth` still guards them; the magic-link/login redirect targets update to
  `/app`. No component behavior changes — only the route base. A logged-in visitor on the public
  `/` sees a "Go to app" link to `/app`.
- **Build:** `vike build` → static HTML for public routes + SPA bundle; `scripts/gen-seo.ts`
  writes `sitemap.xml` + `llms.txt`. Output is a static dir for CDN hosting. Dev keeps the
  `/api` proxy.

## Components

### `src/seo/content/strategies.ts`
A typed array `EXPLAINERS: ExplainerContent[]`, one per ready-made template key. Each:
`{ key, slug, title, summary, category, whenToUse: string, riskProfile: string,
   faq: {q,a}[], legs: ExplainerLeg[] }` where `legs` carry illustrative `entry_price`s so the
payoff is concrete. `slug` is the URL segment (e.g. `bull-call-spread`).

### `src/seo/payoffExpiry.ts` (pure)
`expirationCurve(legs, grid)`, `breakevens`, `maxPL`, `spotGrid` — a faithful TS port of the
Python expiration math (option intrinsic `±(intrinsic − entry)·100·qty`; equity linear; cash 0;
unbounded-tail detection). Returns the curve + stats the page renders. Pure, unit-tested to
match the Python on canonical strategies.

### `src/seo/jsonld.ts`
`articleJsonLd(content, url)` → `TechArticle`; `faqJsonLd(content)` → `FAQPage`;
`breadcrumbJsonLd(trail)` → `BreadcrumbList`. Each returns a plain JS object serialised into a
`<script type="application/ld+json">`.

### `src/seo/meta.ts`
`pageMeta({title, description, canonical, image?})` → the tags a Vike `+Head` renders
(title, description, canonical, Open Graph, Twitter card).

### `pages/learn/@strategy/+Page.tsx`
Server-rendered `<article>`: H1 = title, summary, the existing `PayoffChart` fed the
build-time curve (SVG lands in static HTML; hydrated for hover), a definition list
(what / when to use / max profit / max loss / breakevens), and an FAQ `<section>`. Emits the
JSON-LD + meta via `+Head`. `+onBeforePrerenderStart` enumerates the nine slugs.

### `src/seo-build/sitemap.ts` + `llms.ts`
`buildSitemap(urls)` → `sitemap.xml` string; `buildLlmsTxt(site, pages)` → markdown `llms.txt`
(site summary + the `/learn` URLs with one-line descriptions). Invoked by `scripts/gen-seo.ts`
post-build with the public URL list.

### `public/robots.txt`
Allows `/`, `/learn`; disallows `/api` and `/app`; `Sitemap:` line to the sitemap URL.

## Data flow (build)
1. `vike build` prerenders `/`, `/learn`, and `/learn/<slug>`×9 — each page computes its payoff
   via `payoffExpiry` from the content map and renders `PayoffChart` + JSON-LD + meta to HTML.
2. `scripts/gen-seo.ts` reads the public route/content list → writes `sitemap.xml` and
   `llms.txt` into the build output (`robots.txt` is static in `public/`).
3. The static output deploys to a CDN; the authed SPA loads under `/app`.

## Error handling / edge cases
- An unknown `/learn/<slug>` (not in the content map) → Vike 404 page (only the nine known
  slugs are prerendered; no dynamic fallback).
- The `PayoffChart` already guards an empty curve (returns null); content legs always produce a
  non-empty curve.
- Build fails loudly if a template key in the content map has no payoff or a slug collides
  (a content-map validation test catches this pre-build).

## Testing (vitest)
- **`payoffExpiry.ts`**: bull call spread (breakeven = long strike + net debit; max profit/loss
  bounded), iron condor (two breakevens, bounded), short call (unbounded loss) — values match
  the Python engine's canonical cases.
- **Content map**: every entry has a unique slug + non-empty required fields + at least one FAQ;
  all nine template keys are covered (no missing explainer).
- **`jsonld.ts`**: `articleJsonLd`/`faqJsonLd`/`breadcrumbJsonLd` produce objects with the right
  `@context`/`@type` and the FAQ maps each `{q,a}` to a `Question`/`Answer`.
- **`sitemap.ts` / `llms.ts`**: given the route list, the sitemap contains every `/learn/<slug>`
  `<loc>`; `llms.txt` lists the learn pages.
- **`meta.ts`**: builds canonical + OG tags from inputs.
- **Prerender smoke**: after `pnpm build`, assert `dist/client/learn/bull-call-spread/index.html`
  exists and contains the H1 text, a `application/ld+json` script, and an `<svg`.
- **Regression**: the existing web suite stays green; authed routes behave unchanged.
- **Gate**: `cd apps/web && pnpm test:run && pnpm typecheck && pnpm lint && pnpm build`.

## Out of scope
- Marketing/landing page content (next slice) and OptionsAcademy education (later slice).
- SSR (per-request) rendering and any Node server; this slice is SSG-only.
- A CMS / MDX authoring pipeline — content is typed TS for the nine explainers.
- Hosting/CDN provisioning (Terraform/infra) — this slice produces the static output; wiring it
  to a CDN is an infra task.
- Live/quote-driven payoff on explainer pages — illustrative static payoff only.
- i18n / non-US content.
