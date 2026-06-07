# Vol Surface Contextual Help + Academy Module — Design Spec

**Date:** 2026-06-05
**Slice:** In-app contextual help (Markets vol surface) + an OptionsAcademy volatility-surface lesson
**Status:** Approved design, ready for implementation plan

## Context

The Markets page (`/app/markets`) renders a model-priced IV surface — a smile and an ATM term structure (`apps/web/src/features/markets/IvCurves.tsx`) — with no explanation of what the charts mean or that the IV is model-derived. New users can't read the surface, and the OptionsAcademy has no lesson on it (it stops at `50-implied-volatility`). This slice adds (A) reusable in-context help on the surface and (B) a free academy lesson, linked together.

### Decisions locked during brainstorming
- **Help mechanism:** a reusable `InfoHint` `?`-popover (not native title tooltips or a single panel).
- **Academy module tier:** free (the concept is free; the live surface tool stays Pro-gated — best upgrade funnel).
- **Linkage:** each `InfoHint` links to the new lesson, opened in-app via an Education deep-link.

## Goal

Teach the vol surface in two places that reinforce each other: concise `?`-popovers on the charts, and a free academy lesson the popovers link to.

## Components

### A. `InfoHint` — reusable popover (`apps/web/src/components/InfoHint.tsx`)
A self-contained, app-wide help affordance. Props:
```ts
interface InfoHintProps {
  title: string
  body: string
  learnMoreHref?: string   // e.g. "/app/education?lesson=volatility-surface"
  label?: string           // aria-label; defaults to `More about ${title}`
}
```
Behavior:
- Renders a small circular `?` button (`data-testid="info-hint"`, the `label` as `aria-label`).
- Click toggles a popover card (`role="dialog"`, `data-testid="info-hint-popover"`) showing `title` (bold), `body`, and — when `learnMoreHref` is set — a "Learn more in OptionsAcademy →" link.
- Closes on a second click, on `Escape`, and on blur/click-outside (a `useEffect` document `mousedown`/`keydown` listener removed on unmount).
- Positioned relative to the trigger (absolute card, `z-20`), theme tokens only (`border-line`, `bg-panel2`, `text-txt/txtDim`, accent link). No external deps.

### B. Vol-surface help wiring (`IvCurves.tsx`)
Add three `InfoHint`s, each with `learnMoreHref="/app/education?lesson=volatility-surface"`:
1. **Smile** (next to the "Smile · {expiry}" figcaption) — *"The IV smile plots implied volatility by strike for one expiry. Its slope — the skew — shows where the market prices risk: out-of-the-money puts usually carry higher IV as crash insurance."*
2. **ATM term structure** (next to that figcaption) — *"ATM term structure plots at-the-money IV across expiries. An upward slope means the market expects more movement later (or before an event); an inverted slope signals near-term stress."*
3. **Model-priced IV** — a new caption line under the charts, *"Model-priced IV · approximate"*, with an `InfoHint`: *"Saalr derives IV from a Black-Scholes fit to option mid-prices, not vendor greeks. It's directionally accurate but not an exact vendor quote."*

These are additive; the existing chart rendering, testids (`iv-smile`, `iv-term-structure`, `iv-smile-calls`, `iv-term-line`, `iv-empty`), and the empty-state behaviour are unchanged.

### C. Academy lesson (`packages/content/saalr_content/modules/70-volatility-surface.md`)
Frontmatter: `slug: volatility-surface`, `title: "The volatility surface"`, `summary` (one line), `order: 70`, `min_tier: free`, `est_minutes: 6`. Markdown body sections:
- **Recap: implied volatility** — what IV is, one paragraph, linking the idea back to the `50-implied-volatility` lesson.
- **The smile and skew** — why IV varies by strike; equity skew (OTM puts bid up for crash protection); what a steep vs flat skew implies.
- **The term structure** — ATM IV across expiries; contango vs backwardation; event/earnings humps.
- **IV vs realized volatility** — implied is the market's forward guess; realized is what actually happened; the gap is the vol-risk premium.
- **How Saalr prices it (honesty)** — our IV is a Black-Scholes fit to mid-prices (model-priced, `approximate`), not vendor greeks; good for shape/relative reads, not an exact quote.

`scripts/gen-academy.ts` regenerates `apps/web/src/academy/modules.generated.ts` (it runs in the `pretypecheck` and `prebuild` hooks, so the build picks the lesson up automatically). The module is free, so its full body ships in the bundle.

### D. Education deep-link (`apps/web/src/pages/Education.tsx`)
Read `?lesson=<slug>` via `useSearchParams` once on mount; if present and it matches a known module, set it as the selected slug so the reader opens that lesson. Falls back to the existing default (first module) when absent. This makes the `InfoHint` "Learn more" link open the volatility-surface lesson directly instead of the first lesson.

## Data flow
No API, DB, or backend change. `InfoHint` is pure presentational. The lesson is static markdown compiled into the existing generated bundle. The Education deep-link reads a query param client-side.

## Error / edge handling
- `InfoHint` with no `learnMoreHref` simply omits the link.
- Education `?lesson=` pointing to an unknown slug → ignored (falls back to default); never throws.
- The lesson is plain markdown rendered by the existing `ModuleReader`; no new rendering path.

## Testing
- **`InfoHint.test.tsx`:** the `?` trigger renders; clicking opens the popover (title + body visible); a `learnMoreHref` renders the link with the right `href`; `Escape` closes it.
- **`IvCurves`:** the three `info-hint` triggers are present alongside the existing charts; the existing smile/term/empty tests still pass (update the test to assert hint presence).
- **`Education`:** rendering at `/app/education?lesson=volatility-surface` (MemoryRouter initial entry) selects that lesson — the reader shows its title; absent param falls back to the first lesson.
- **Academy:** `parseModule` already covers frontmatter/body parsing; if `academy.test.tsx` asserts a fixed module count or slug list, update it to include `volatility-surface` (now 7 modules, 6 free / 1 pro).

## Out of scope (deferred)
- A 3D/interactive surface visualization.
- Per-data-point crosshair tooltips on the SVG charts.
- Rewriting the public SSG `/academy/{slug}` pages (the lesson appears there automatically via the shared generated bundle, but no redesign).
- Contextual help on other Markets surfaces (chain, greeks) — `InfoHint` is built reusable so they can adopt it later, but only the vol surface is wired here.

## Build sequence (for the plan)
1. `InfoHint.tsx` + test (reusable component first).
2. Wire `InfoHint`s into `IvCurves.tsx` + update its test.
3. Education `?lesson=` deep-link + test.
4. The `70-volatility-surface.md` lesson; regenerate the bundle; fix any academy count assertion.
5. Gate: web typecheck (runs gen-academy) + lint + test:run + build green.
