# Vol Surface Contextual Help + Academy Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable `InfoHint` `?`-popovers teaching the vol surface on `/app/markets`, wire three onto `IvCurves`, add a free `volatility-surface` OptionsAcademy lesson, and deep-link Education so the hints open that lesson.

**Architecture:** One new presentational React component (`InfoHint`), additive wiring into `IvCurves`, a small `?lesson=` query-param read in `Education`, and one static markdown lesson compiled into the existing generated academy bundle. No API/DB/backend code change.

**Tech Stack:** React 18 + TS strict + Tailwind (theme tokens only) + Vitest + @testing-library/react; academy lessons are markdown in `packages/content/saalr_content/modules/` compiled by `apps/web/scripts/gen-academy.ts`. **pnpm/npm — NOT yarn.**

**Spec:** `docs/superpowers/specs/2026-06-05-vol-surface-contextual-help-design.md`

**Conventions:** commit footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`; theme tokens only for Tailwind class colors (`border-line`, `bg-panel2`, `text-txt/txtDim/txtFaint`, `text-accent`, `hover:border-accent` — all valid); double-quote JSX strings; NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`; branch `feat/scaffold-data-layer`. Web: from `apps/web`, `npx vitest run <file>`; gate `npm run typecheck` (runs `gen-academy`) / `npm run lint`.

---

## File Structure

- **Create** `apps/web/src/components/InfoHint.tsx` — reusable `?`-popover.
- **Create** `apps/web/src/components/InfoHint.test.tsx`.
- **Modify** `apps/web/src/features/markets/IvCurves.tsx` — three `InfoHint`s + a "model-priced · approximate" caption.
- **Modify** `apps/web/src/features/markets/IvCurves.test.tsx` — assert the hints render.
- **Modify** `apps/web/src/pages/Education.tsx` — `?lesson=<slug>` deep-link.
- **Create** `apps/web/src/pages/Education.test.tsx` — deep-link selects the lesson.
- **Create** `packages/content/saalr_content/modules/70-volatility-surface.md` — the lesson (free).
- **Regenerated** `apps/web/src/academy/modules.generated.ts` — via `gen-academy` (commit the regenerated file).

---

## Task 1: InfoHint component

**Files:** Create `apps/web/src/components/InfoHint.tsx`, Test `apps/web/src/components/InfoHint.test.tsx`.

- [ ] **Step 1: Write the failing test** `apps/web/src/components/InfoHint.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { InfoHint } from './InfoHint'

describe('InfoHint', () => {
  it('opens the popover on click and shows title + body', () => {
    render(<InfoHint title="IV smile" body="Implied vol by strike." />)
    expect(screen.queryByTestId('info-hint-popover')).toBeNull()
    fireEvent.click(screen.getByTestId('info-hint'))
    const pop = screen.getByTestId('info-hint-popover')
    expect(pop.textContent).toContain('IV smile')
    expect(pop.textContent).toContain('Implied vol by strike.')
  })

  it('renders a learn-more link when href is provided', () => {
    render(<InfoHint title="t" body="b" learnMoreHref="/app/education?lesson=volatility-surface" />)
    fireEvent.click(screen.getByTestId('info-hint'))
    expect(screen.getByText(/learn more/i).getAttribute('href')).toBe('/app/education?lesson=volatility-surface')
  })

  it('omits the link when no href is given', () => {
    render(<InfoHint title="t" body="b" />)
    fireEvent.click(screen.getByTestId('info-hint'))
    expect(screen.queryByText(/learn more/i)).toBeNull()
  })

  it('closes on Escape', () => {
    render(<InfoHint title="t" body="b" />)
    fireEvent.click(screen.getByTestId('info-hint'))
    expect(screen.getByTestId('info-hint-popover')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByTestId('info-hint-popover')).toBeNull()
  })
})
```

- [ ] **Step 2: Run the test, verify it fails**

Run (from `apps/web`): `npx vitest run src/components/InfoHint.test.tsx`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Create** `apps/web/src/components/InfoHint.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'

/**
 * A small "?" badge that opens a styled help popover. Reusable app-wide.
 * Uses span elements so it can sit inline inside a figcaption or label.
 */
export function InfoHint({
  title, body, learnMoreHref, label,
}: {
  title: string; body: string; learnMoreHref?: string; label?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement | null>(null)

  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <span ref={ref} className="relative inline-block align-middle">
      <button
        type="button"
        data-testid="info-hint"
        aria-label={label ?? `More about ${title}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="grid h-3.5 w-3.5 place-items-center rounded-full border border-line text-[9px] font-semibold text-txtFaint transition-colors hover:border-accent hover:text-accent"
      >
        ?
      </button>
      {open && (
        <span
          role="dialog"
          data-testid="info-hint-popover"
          className="absolute left-0 top-5 z-20 block w-64 space-y-1.5 rounded-lg border border-line bg-panel2 p-3 text-left shadow-lg"
        >
          <span className="block text-[11px] font-semibold text-txt">{title}</span>
          <span className="block text-[11px] leading-snug text-txtDim">{body}</span>
          {learnMoreHref && (
            <a href={learnMoreHref} className="block text-[11px] text-accent hover:underline">
              Learn more in OptionsAcademy →
            </a>
          )}
        </span>
      )}
    </span>
  )
}
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `npx vitest run src/components/InfoHint.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/InfoHint.tsx apps/web/src/components/InfoHint.test.tsx
git commit -m "feat(web): reusable InfoHint help popover (? badge -> styled card + learn-more link)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Wire InfoHints into IvCurves

**Files:** Modify `apps/web/src/features/markets/IvCurves.tsx`, Test `apps/web/src/features/markets/IvCurves.test.tsx`.

- [ ] **Step 1: Add an assertion to** `apps/web/src/features/markets/IvCurves.test.tsx` — add this test inside the `describe('IvCurves', ...)` block (keep all existing tests):

```tsx
  it('shows contextual info hints on the charts', () => {
    render(<IvCurves surface={SURFACE} expiry="2026-07-17" />)
    expect(screen.getAllByTestId('info-hint').length).toBeGreaterThanOrEqual(3)
  })
```

- [ ] **Step 2: Run it, verify it fails**

Run: `npx vitest run src/features/markets/IvCurves.test.tsx`
Expected: FAIL on the new test (no `info-hint` yet); the existing tests still pass.

- [ ] **Step 3: Wire the hints in** `apps/web/src/features/markets/IvCurves.tsx`:

Add the import near the top (after the existing `import type ...` line):
```tsx
import { InfoHint } from '../../components/InfoHint'

const LESSON = '/app/education?lesson=volatility-surface'
```

Replace the `return (...)` JSX (the final block, currently `<div className="grid gap-4 lg:grid-cols-2"> ... </div>`) with:

```tsx
  return (
    <div className="space-y-3">
      <div className="grid gap-4 lg:grid-cols-2">
        <figure className="rounded-lg border border-line bg-panel p-3">
          <figcaption className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
            Smile · {expiry}
            <InfoHint
              title="IV smile"
              body="The smile plots implied volatility by strike for one expiry. Its slope — the skew — shows where the market prices risk: out-of-the-money puts usually carry higher IV as crash insurance."
              learnMoreHref={LESSON}
            />
          </figcaption>
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="iv-smile">
            <polyline data-testid="iv-smile-calls" points={pointsAttr(callPts)} fill="none" stroke="#37c98b" strokeWidth={1.8} />
            <polyline data-testid="iv-smile-puts" points={pointsAttr(putPts)} fill="none" stroke="#ff5d73" strokeWidth={1.8} strokeDasharray="4 3" />
          </svg>
        </figure>
        <figure className="rounded-lg border border-line bg-panel p-3">
          <figcaption className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
            ATM term structure
            <InfoHint
              title="ATM term structure"
              body="This plots at-the-money IV across expiries. An upward slope means the market expects more movement later (or before an event); an inverted slope signals near-term stress."
              learnMoreHref={LESSON}
            />
          </figcaption>
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="iv-term-structure">
            <polyline data-testid="iv-term-line" points={pointsAttr(termPts)} fill="none" stroke="#4da3ff" strokeWidth={1.8} />
            {termPts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={2.5} fill="#4da3ff" />)}
          </svg>
        </figure>
      </div>
      <p className="flex items-center gap-1.5 font-mono text-[10px] text-txtFaint">
        Model-priced IV · approximate
        <InfoHint
          title="Model-priced IV"
          body="Saalr derives IV from a Black-Scholes fit to option mid-prices, not vendor greeks. It is directionally accurate and great for reading shape, but a single number is not an exact dealer quote."
          learnMoreHref={LESSON}
        />
      </p>
    </div>
  )
```

(The SVG contents and all existing testids — `iv-smile`, `iv-smile-calls`, `iv-smile-puts`, `iv-term-structure`, `iv-term-line` — are byte-for-byte the same; only the wrapping `<div>` + the two figcaptions changed, and the new caption line was added.)

- [ ] **Step 4: Run the test, verify it passes**

Run: `npx vitest run src/features/markets/IvCurves.test.tsx`
Expected: PASS (all existing tests + the new hints test). Then `npm run typecheck` + `npm run lint` clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/markets/IvCurves.tsx apps/web/src/features/markets/IvCurves.test.tsx
git commit -m "feat(web): contextual help on the vol surface — smile, term structure, model-priced IV

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Education `?lesson=` deep-link

**Files:** Modify `apps/web/src/pages/Education.tsx`, Test `apps/web/src/pages/Education.test.tsx`.

- [ ] **Step 1: Write the failing test** `apps/web/src/pages/Education.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Education } from './Education'

vi.mock('../features/academy/hooks', () => ({
  useModules: () => ({
    data: {
      modules: [
        { slug: 'what-is-an-option', title: 'What is an option?', summary: 's', order: 10, minTier: 'free', estMinutes: 5 },
        { slug: 'volatility-surface', title: 'The volatility surface', summary: 's', order: 70, minTier: 'free', estMinutes: 6 },
      ],
      completed: 0, total: 2,
    },
    isLoading: false,
  }),
}))
vi.mock('../features/academy/ModuleReader', () => ({ ModuleReader: ({ slug }: { slug: string }) => <div data-testid="reader-slug">{slug}</div> }))
vi.mock('../features/academy/ModuleList', () => ({ ModuleList: () => <div /> }))
vi.mock('../features/academy/SearchBox', () => ({ SearchBox: () => <div /> }))
vi.mock('../features/academy/AskAssistant', () => ({ AskAssistant: () => <div /> }))

function wrap(initial: string) {
  return render(<MemoryRouter initialEntries={[initial]}><Education /></MemoryRouter>)
}

describe('Education deep-link', () => {
  it('opens the lesson named in ?lesson=', () => {
    wrap('/?lesson=volatility-surface')
    expect(screen.getByTestId('reader-slug').textContent).toBe('volatility-surface')
  })

  it('falls back to the first lesson without the param', () => {
    wrap('/')
    expect(screen.getByTestId('reader-slug').textContent).toBe('what-is-an-option')
  })
})
```

- [ ] **Step 2: Run it, verify it fails**

Run: `npx vitest run src/pages/Education.test.tsx`
Expected: FAIL on the deep-link case (the param is ignored today).

- [ ] **Step 3: Add the deep-link to** `apps/web/src/pages/Education.tsx`:

Change the first import line to add `useEffect`:
```tsx
import { useEffect, useState } from 'react'
```
Add the router import after it:
```tsx
import { useSearchParams } from 'react-router-dom'
```
Inside `Education()`, right after `const [selectedSlug, setSelectedSlug] = useState<string | null>(null)`, add:
```tsx
  const [searchParams] = useSearchParams()
  useEffect(() => {
    const lesson = searchParams.get('lesson')
    if (lesson) setSelectedSlug(lesson)
  }, [searchParams])
```
(`activeSlug = selectedSlug ?? modules[0]?.slug ?? null` already feeds `ModuleReader`, so a set `selectedSlug` wins; absent the param it falls back to the first module.)

- [ ] **Step 4: Run the test, verify it passes**

Run: `npx vitest run src/pages/Education.test.tsx`
Expected: PASS (2 tests). Then `npm run typecheck` + `npm run lint` clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/Education.tsx apps/web/src/pages/Education.test.tsx
git commit -m "feat(web): Education deep-link (?lesson=slug) so contextual help opens the right lesson

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: The volatility-surface academy lesson

**Files:** Create `packages/content/saalr_content/modules/70-volatility-surface.md`; regenerate `apps/web/src/academy/modules.generated.ts`.

- [ ] **Step 1: Create** `packages/content/saalr_content/modules/70-volatility-surface.md`:

```markdown
---
slug: volatility-surface
title: "The volatility surface"
summary: The volatility surface maps implied volatility across strikes and expiries — its smile and term structure reveal how the market prices risk.
order: 70
min_tier: free
est_minutes: 6
---
# The volatility surface

Building on the **implied volatility** lesson, you know option prices carry the market's forecast of
future movement. The **volatility surface** is that forecast laid out in two dimensions at once:
implied volatility for every **strike** and every **expiry**. Reading it tells you where the market
thinks risk lives.

## The smile and the skew

If every option on a name shared one volatility, a plot of IV against strike would be flat. It
almost never is. Plot it and you get a **smile** — a curve that lifts away from the at-the-money
strike. In equity and index options the smile is lopsided: out-of-the-money **puts** trade at higher
implied volatility than equidistant calls. That tilt is the **skew**, and it exists because
investors pay up for downside crash protection. A steep skew says the market is nervous about a
drop; a flat skew says it is calm.

## The term structure

Now hold the strike near the money and walk across expiries instead. That curve is the **term
structure** of volatility. When far-dated options carry more IV than near-dated ones (an upward,
*contango* slope), the market expects movement to build over time. When near-dated IV spikes above
longer-dated — an **inverted**, *backwardated* curve — something is expected soon: an earnings
report, a central-bank meeting, a pending headline. A localized hump on one expiry usually marks a
known event date.

## Implied versus realized

Implied volatility is a *forecast*; **realized volatility** is what actually happened. The two
rarely match, and the gap between them is the **volatility risk premium** — on average implied runs
a little rich, which is why systematically *selling* options has an edge (and a tail risk).
Comparing an option's IV to the underlying's recent realized volatility is the quickest read on
whether premium is cheap or expensive.

## How Saalr prices it

A candid note: Saalr's surface is **model-priced**. We fit a Black-Scholes implied volatility to
each contract's mid price rather than consuming a vendor's published greeks, and we flag every such
number **approximate**. That makes the *shape* — the smile, the skew, the term slope — reliable and
useful for relative comparisons, but a single number is not an exact dealer quote. Use it to read
structure, not to mark a book to the penny.
```

- [ ] **Step 2: Regenerate the academy bundle**

Run (from `apps/web`): `npx tsx scripts/gen-academy.ts`
Expected output: `gen-academy: wrote 7 modules (6 free, 1 pro/premium) → src/academy/modules.generated.ts`
(`apps/web/src/academy/modules.generated.ts` now includes `volatility-surface` with its full body, since it is free.)

- [ ] **Step 3: Verify the lesson parses and nothing regressed**

Run: `npx vitest run pages/academy/academy.test.tsx src/academy/parseModule.test.ts`
Expected: PASS. The academy index test asserts specific slugs (`what-is-an-option`, `implied-volatility`) and the Pro teaser — adding a new free lesson does not remove any of those, so it stays green. If a backend content test asserts a fixed module count, update it (see Task 5 Step 1).

- [ ] **Step 4: Commit**

```bash
git add packages/content/saalr_content/modules/70-volatility-surface.md apps/web/src/academy/modules.generated.ts
git commit -m "feat(content): free OptionsAcademy lesson — the volatility surface (smile, skew, term structure)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Final gate

- [ ] **Step 1: Backend content sanity** — `grep -rn "module" packages/content/tests tests/integration 2>/dev/null | grep -iE "count|len\(|== [0-9]"` (or run the content tests). If a backend test asserts a fixed number of modules, bump it to include `volatility-surface`. (The in-app `/content/modules` API reads the same dir, so the lesson appears there automatically; only a hardcoded count would break.) Run `uv run pytest packages/core/tests packages/content 2>/dev/null -q` and any content integration test if present — green.
- [ ] **Step 2: Web gate** — from `apps/web`: `npm run typecheck && npm run lint && npm run test:run` → green (typecheck re-runs `gen-academy`; ~+9 tests). `npm run build` → "48 HTML documents pre-rendered" (one more than before: the new `/academy/volatility-surface` SSG page).
- [ ] **Step 3 (optional, local stack running): visual check** — `http://localhost:5174/app/markets` → SPY → Vol Surface: the `?` hints open cards; "Learn more" opens `/app/education` on the volatility-surface lesson. `/app/education` directly also lists the new lesson.

---

## Self-Review notes (for the executor)

- **`InfoHint` uses `<span>` wrappers** (not `<div>`) so it nests legally inside a `<figcaption>`/inline text; the popover is `position: absolute` so it overlays without shifting layout.
- **`learnMoreHref` is a full `/app/...` path** rendered as a plain `<a>` — a raw anchor ignores the router `basename`, so the `/app` prefix is required (matching the existing `/app/billing` upgrade links).
- **IvCurves wiring is additive** — the SVG bodies and every existing testid are unchanged; only the wrapper `<div>`, the two figcaptions (now `flex items-center gap-1.5`), and the new caption line changed. The early `iv-empty` return path is untouched, so the empty-state tests still pass.
- **Education fallback** — `activeSlug = selectedSlug ?? modules[0]?.slug` already defaults to the first lesson; the `useEffect` only sets `selectedSlug` when `?lesson=` is present, so the no-param case is unchanged.
- **`modules.generated.ts` is committed** (the public academy `+Page.tsx` imports it at build/SSG time). Regenerate with `gen-academy` and commit it alongside the `.md`; `pretypecheck`/`prebuild` also regenerate it, so it stays in sync.
- **Module count is now 7 (6 free / 1 pro).** `academy.test.tsx` keys off specific slugs, not a count, so it is unaffected; only a hardcoded backend count assertion (if any) needs bumping.
