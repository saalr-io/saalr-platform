# Frontends + public surface — band design

**Status:** FE-1, FE-2, FE-3, FE-4 ALL DONE (committed on `feat/scaffold-data-layer`, not pushed) —
autonomous `/ralph` run, 2026-06-03, with a `/frontend-design` aesthetic pass. The whole band is
complete. Out of band (separate follow-on): the `/app/{markets,models,portfolio}`/dashboard analytics
placeholders, which need market-data/OMS clients.

## Context

The SEO/GEO *foundation* already shipped (`docs/superpowers/specs/2026-05-30-seo-geo-foundation-design.md`):
`apps/web` is a **Vike + React 18** hybrid — public pages are SSG-prerendered (`/`, `/learn`,
`/learn/<slug>` ×9 strategy explainers), the authenticated app under `/app` is a client-only SPA
(React Router 6). SEO artifacts (`sitemap.xml`, `robots.txt`, `llms.txt`, JSON-LD, OG) are generated
by `scripts/gen-seo.ts` at build. Styling = Tailwind dark theme (`canvas/panel/txt/txtDim/accent/
pos/neg/warn` tokens, IBM Plex). Data = TanStack Query over a fetch wrapper (`src/lib/*.ts`) that
maps 401→logout and 402→`EntitlementError`. Auth = `AuthContext` (`me.tier`, `me.entitlements`).

That foundation's own "out of scope" list named the work this band does: **marketing landing** and
**OptionsAcademy education**. In parallel, several `/app/*` routes are still `PlaceholderPage` even
though their backends are complete. This band fills those gaps. It does **not** touch the analytics
placeholders (`/app/markets`, `/app/models`, `/app/portfolio`, `/app` dashboard) — those need
market-data/OMS clients and are a separate analytics-frontend band.

## Backends already available (verified)

- **Content / OptionsAcademy** (`apps/api/saalr_api/content/router.py`): `GET /content/modules`
  (list + progress aggregate), `GET /content/modules/{slug}` (body; 402 if pro module + free tier),
  `POST /content/modules/{slug}/complete`, `GET /content/progress`, `GET /content/search?q=&mode=&limit=`
  (keyword|semantic|hybrid), `POST /content/ask` (RAG Q&A, **Pro+** via `require_ml_forecast`).
- **Research Agent** (`apps/api/saalr_api/research/router.py`, **Premium** via `require_research_agent`):
  `POST /research/run` (200 cached | 202 queued+poll_url), `GET /research/notes` (cursor list),
  `GET /research/notes/{id}` (poll/result: summary markdown + signals{spot,vol_forecast,sentiment} +
  sources), `GET /research/notes/{id}/transcript` (multi-agent steps).
- **Tiers**: `free` / `pro` / `premium` (`packages/core/saalr_core/tiers.py`).
- **Academy content source**: 6 markdown modules under `packages/content/saalr_content/modules/`
  (frontmatter: slug/title/summary/order/min_tier/est_minutes), all currently `min_tier: free`.

## Decomposition (each its own spec/plan-compressed → build → review → memory)

1. **FE-1 — Marketing landing** (public SSG, replaces the `/` stub). No backend, no auth. Highest
   SEO/GEO value, zero coupling → first.
2. **FE-2 — In-app OptionsAcademy** (`/app/education`): list/read(markdown)/complete/progress/search,
   `ask` Pro-gated. Consumes `/content/*`.
3. **FE-3 — In-app Research Agent** (`/app/research`, Premium): ticker → run → poll → render note
   (summary + signal cards + sources) → transcript. Consumes `/research/*`. 402 → upgrade nudge.
4. **FE-4 — Public OptionsAcademy SSG** (GEO extension). **Decisions (2026-06-03):**
   - **Routes** `/academy` (index) + `/academy/<slug>` (one per FREE module), parallel to `/learn`.
   - **Pro-leak avoidance:** only FREE module bodies are published. Pro modules appear on the index as
     locked teasers (title + summary + "Pro" badge → `/app/education`) — NO body, NO page. A build-time
     generator `scripts/gen-academy.ts` reads `packages/content/saalr_content/modules/*.md`, parses
     frontmatter via a pure testable `parseModule`, and writes `src/academy/modules.generated.ts` with
     `body: null` for non-free modules, so Pro lesson text never enters the bundle or prerendered HTML.
     The generated file is gitignored (new `apps/web/.gitignore`) and produced by npm pre-hooks
     (`pretypecheck`/`pretest`/`pretest:run`/`predev`/`prebuild` → `tsx scripts/gen-academy.ts`).
   - Pages reuse the FE-2 `Markdown` renderer for bodies and emit `TechArticle` + `BreadcrumbList`
     JSON-LD (no FAQ — modules have none). `scripts/gen-seo.ts` also lists `/academy` + free
     `/academy/<slug>` in `sitemap.xml` + `llms.txt`. Robots already `Allow: /`.
   - **Leak guard test:** the build smoke greps `dist/` to assert a Pro-only phrase is ABSENT and no
     `dist/client/academy/iron-condor-construction/` page exists.

## Cross-cutting decisions (autonomous defaults)

- **Reuse, don't reinvent**: `pageMeta`/JSON-LD helpers (`src/seo/`), the `request()` wrapper +
  `EntitlementError`, TanStack Query hooks-per-feature, `PlaceholderPage` → real page swap in
  `src/app/Router.tsx`. New API clients live in `src/lib/{content,research}.ts`; feature UIs in
  `src/features/{academy,research,marketing}/`; pages stay thin.
- **Testing**: vitest + @testing-library/react render tests for components and client unit tests
  (mock `fetch`), mirroring the existing strategies feature. Gate per slice = `npm run typecheck`
  (`tsc --noEmit`) + `npm run test:run` (vitest) + `npm run lint` (eslint), all from `apps/web`.
- **No invented data**: the landing tier table lists feature bullets but **no dollar prices**
  (pre-revenue); CTA = "Start free". Markdown rendering uses a minimal safe renderer (no raw HTML
  injection) — add a tiny dep only if needed, preferring a hand-rolled constrained renderer.
- **Authoring**: controller-inline (frontend has no docker-init stall); a final opus code review per
  slice, matching the project's per-slice review discipline.

## FE-1 — Marketing landing (this slice)

**Goal:** replace `pages/index/+Page.tsx` (a 20-line stub) with a real, crawlable marketing landing
that converts visitors to `/app` (start) or `/learn` (educate), and emits Organization +
SoftwareApplication + WebSite JSON-LD for SEO/GEO.

**Files:**
- `apps/web/src/features/marketing/copy.ts` — typed content (hero, features[], tiers[], footer links).
  Pure data so it's unit-testable and the page/JSON-LD share one source of truth.
- `apps/web/src/features/marketing/Hero.tsx`, `Features.tsx`, `Tiers.tsx`, `Footer.tsx` — presentational
  components (props in, dark-theme classes), each render-tested.
- `apps/web/src/seo/jsonld.ts` — add `organizationJsonLd()`, `softwareAppJsonLd()`, `websiteJsonLd()`
  (alongside the existing article/faq/breadcrumb builders).
- `apps/web/pages/index/+Page.tsx` — compose the sections.
- `apps/web/pages/index/+Head.tsx` — `pageMeta` (canonical `/`, OG) + the three JSON-LD blocks as
  `<script type="application/ld+json">`.
- Tests: `*.test.tsx` per component + `copy.test.ts` + a `jsonld` test for the new builders.

**Sections (single scroll, dark):**
- **Hero**: product name + one-line positioning ("Research-grade options analytics for retail
  traders"), sub-paragraph, two CTAs — "Open the terminal" → `/app`, "Learn strategies" → `/learn`.
- **Features** (grid of 6, drawn from real platform capabilities): Strategy builder (multi-leg payoff/
  POP/Greeks), Greeks & IV surface, Backtesting, ML vol forecasts (GARCH) + Monte-Carlo POP, Research
  Agent (multi-agent notes), OptionsAcademy. Each: title + one-line + a `/learn` or `/app` deep link
  where natural.
- **Tiers**: Free / Pro / Premium as three cards with feature bullets (Pro = market data, Greeks/IV,
  ML forecasts; Premium adds the Research Agent + higher limits). **No prices.** CTA "Start free" → `/app`.
- **Footer**: links to `/learn`, `/app`, and a short honesty line ("Educational analytics, not
  investment advice").

**JSON-LD (GEO):**
- `Organization` (name Saalr, url, description).
- `SoftwareApplication` (name, applicationCategory FinanceApplication, operatingSystem Web, description,
  offers omitted — no price).
- `WebSite` (name, url, potentialAction SearchAction pointing at `/learn` — optional, include if cheap).

**Error handling / edge cases:** none at runtime (static). Build: page must prerender with no window/
fetch access — keep it pure. `/` is already registered in `gen-seo.ts`; update its title/description
there to match the new hero copy.

**Out of scope for FE-1:** pricing numbers, testimonials, blog, contact form, analytics scripts.
