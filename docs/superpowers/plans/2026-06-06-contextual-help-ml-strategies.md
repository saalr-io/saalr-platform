# Contextual Help for ML Models & Strategies — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `InfoHint` "?" help (8th-grade blurbs + OptionsAcademy deep-links) to every ML model and all 21 strategy templates, backed by a shared registry and 5 new free academy lessons.

**Architecture:** Static front-end content only — no API change. A new `helpHints.ts` registry holds every blurb + lesson slug; call sites read `hintProps(key)` and pass it to the existing `InfoHint`. Five new markdown lessons drop into `packages/content/.../modules/` (auto-picked up by the `gen-academy` prebuild hook).

**Tech Stack:** React 18 + TS strict + Tailwind + Vitest (pnpm), markdown lessons parsed by `apps/web/src/academy/parseModule.ts`.

**Spec:** `docs/superpowers/specs/2026-06-06-contextual-help-ml-strategies-design.md`

**Conventions:** Web tests `pnpm -C apps/web test -- run <file>` (or `pnpm -C apps/web vitest run <file>`), typecheck `pnpm -C apps/web typecheck`. Reading level: short sentences, common words, one idea per sentence, accurate. Commit footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Do NOT touch `tools/equity-screener`, root `.gitignore`, `.env`, `.omc`.

---

### Task 1: Five new Options Academy lessons

**Files (create):**
- `packages/content/saalr_content/modules/80-volatility-forecasting.md`
- `packages/content/saalr_content/modules/90-price-forecasting.md`
- `packages/content/saalr_content/modules/100-monte-carlo-simulation.md`
- `packages/content/saalr_content/modules/110-market-sentiment.md`
- `packages/content/saalr_content/modules/120-options-strategy-playbook.md`

Each file MUST start with frontmatter in the exact existing format (see `70-volatility-surface.md`). Use these exact frontmatter blocks, then write the body to the outline (8th-grade voice; ~350–550 words; use `##` subheads, short paragraphs, a concrete analogy each).

- [ ] **Step 1: `80-volatility-forecasting.md`**

```markdown
---
slug: volatility-forecasting
title: "How we forecast volatility"
summary: Volatility is how much a price swings. We forecast it with three methods — HV21, GARCH, and HAR — and let a fair back-test pick the winner.
order: 80
min_tier: free
est_minutes: 6
---
```
Body must cover: volatility = size of price swings (analogy: calm sea vs. stormy sea); why it matters (option prices and risk depend on it); **HV21** = the average swing over the last 21 days; **GARCH** = swings come in clusters (calm stretches and stormy stretches), so it reacts to recent storms; **HAR** = blends yesterday's, last week's, and last month's swings; **walk-forward test** = score each method on past days it never trained on, then show the winner; honesty: these are estimates, not promises.

- [ ] **Step 2: `90-price-forecasting.md`**

```markdown
---
slug: price-forecasting
title: "How we forecast price"
summary: Guessing tomorrow's price is close to a coin flip. We compare ARIMA, an LSTM neural network, and a plain "no change" baseline, and show which actually wins on past data.
order: 90
min_tier: free
est_minutes: 6
---
```
Body must cover: short-term price direction is **almost random**; **ARIMA** = finds patterns in the recent number series; **LSTM** = a small AI that learns from sequences; **naive baseline** = "tomorrow is about the same as today"; **walk-forward** picks the winner on unseen past days; honesty: the naive baseline often wins, so use forecasts as one input, never a guarantee; the confidence band shows how unsure the guess is.

- [ ] **Step 3: `100-monte-carlo-simulation.md`**

```markdown
---
slug: monte-carlo-simulation
title: "Reading a Monte-Carlo simulation"
summary: A Monte-Carlo runs thousands of pretend futures for a price to estimate how a trade might end up — its probability of profit, average result, and range of outcomes.
order: 100
min_tier: free
est_minutes: 5
---
```
Body must cover: rolling the dice thousands of times (analogy: replaying a game many times); each run is one possible price path; **POP** = the share of runs that made money; **EV** = the average result across all runs; the **histogram** shows how often each outcome happened; a capped-risk spread piles up at its max-profit and max-loss edges (two tall bars); honesty: results depend on the volatility assumption you feed it.

- [ ] **Step 4: `110-market-sentiment.md`**

```markdown
---
slug: market-sentiment
title: "How news sentiment works"
summary: We read recent news headlines about a stock and turn the mood into a score from negative to positive, weighting newer headlines more heavily.
order: 110
min_tier: free
est_minutes: 5
---
```
Body must cover: a computer reads recent headlines and scores the mood from −1 (bad news) to +1 (good news); **newer headlines count more** (time-weighting); the label is bearish / neutral / bullish; **confidence** grows with the number of headlines; honesty: news is noisy, can lag the market, and is only one clue — never trade on it alone.

- [ ] **Step 5: `120-options-strategy-playbook.md`**

```markdown
---
slug: options-strategy-playbook
title: "The options strategy playbook"
summary: A tour of every ready-made strategy, grouped by what you expect the market to do — go up, go down, stay flat, or make a big move — and whether your risk is capped.
order: 120
min_tier: free
est_minutes: 7
---
```
Body must cover: what a strategy is (combining calls and puts into one plan); the four **market views** (bullish, bearish, neutral, volatile); **defined vs undefined risk** (is your worst case capped?); a short grouped tour naming the families — vertical spreads (bull/bear call & put spreads), straddles/strangles (long = bet on a big move, short = bet on calm), iron condor / iron butterfly (range-bound), butterflies (pin a price), covered call / cash-secured put / collar / protective put (around shares), ratio spreads, jade lizard, calendar; how to pick one from your view.

- [ ] **Step 6: Verify lessons parse**

Run: `pnpm -C apps/web gen:academy` (regenerates `modules.generated.ts`).
Expected: completes with no parse error (a bad `min_tier` or missing slug/title throws). If it errors, fix the offending frontmatter.

- [ ] **Step 7: Commit**

```bash
git add packages/content/saalr_content/modules/80-volatility-forecasting.md packages/content/saalr_content/modules/90-price-forecasting.md packages/content/saalr_content/modules/100-monte-carlo-simulation.md packages/content/saalr_content/modules/110-market-sentiment.md packages/content/saalr_content/modules/120-options-strategy-playbook.md
git commit -m "feat(content): 5 free academy lessons — forecasting, MC, sentiment, strategy playbook"
```
(Do NOT commit `apps/web/src/academy/modules.generated.ts` — it is a gitignored build artifact.)

---

### Task 2: `helpHints` registry + test

**Files:**
- Create: `apps/web/src/content/helpHints.ts`
- Test: `apps/web/src/content/helpHints.test.ts`

- [ ] **Step 1: Write the failing test** — `apps/web/src/content/helpHints.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { HELP_HINTS, hintProps, lessonPath, ACADEMY_SLUGS } from './helpHints'

const STRATEGY_KEYS = [
  'bull_call_spread', 'bear_put_spread', 'long_straddle', 'long_strangle', 'iron_condor',
  'iron_butterfly', 'covered_call', 'cash_secured_put', 'long_calendar', 'bull_put_spread',
  'bear_call_spread', 'short_straddle', 'short_strangle', 'protective_put', 'collar',
  'call_ratio_spread', 'put_ratio_spread', 'jade_lizard', 'call_butterfly', 'put_butterfly',
  'broken_wing_butterfly',
]
const ML_KEYS = ['vol-forecast', 'price-forecast', 'monte-carlo', 'sentiment', 'vol-surface']

describe('helpHints registry', () => {
  it('covers all ML keys and all 21 strategy keys', () => {
    for (const k of [...ML_KEYS, ...STRATEGY_KEYS]) {
      expect(HELP_HINTS[k], `missing hint for ${k}`).toBeDefined()
    }
  })

  it('every hint has a non-empty title/body, a known lesson slug, and a short body', () => {
    for (const [key, h] of Object.entries(HELP_HINTS)) {
      expect(h.title.trim().length, `${key} title`).toBeGreaterThan(0)
      expect(h.body.trim().length, `${key} body`).toBeGreaterThan(0)
      expect(h.body.length, `${key} body too long`).toBeLessThanOrEqual(240)
      expect(ACADEMY_SLUGS, `${key} slug`).toContain(h.lessonSlug)
    }
  })

  it('hintProps returns InfoHint-ready props with an /education deep-link', () => {
    const p = hintProps('vol-forecast')
    expect(p.title.length).toBeGreaterThan(0)
    expect(p.learnMoreTo).toBe(lessonPath('volatility-forecasting'))
    expect(lessonPath('x')).toBe('/education?lesson=x')
  })

  it('all 21 strategy hints point at the playbook lesson', () => {
    for (const k of STRATEGY_KEYS) {
      expect(HELP_HINTS[k].lessonSlug).toBe('options-strategy-playbook')
    }
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm -C apps/web vitest run src/content/helpHints.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `apps/web/src/content/helpHints.ts`**

```ts
// Single source of truth for contextual-help copy. Blurbs are written at ~8th-grade level
// and kept short (the InfoHint popover is w-64). `lessonSlug` must be a real academy lesson.

export interface HelpHint {
  title: string
  body: string
  lessonSlug: string
}

/** Academy lesson slugs these hints may link to (kept in sync with packages/content modules). */
export const ACADEMY_SLUGS = [
  'volatility-forecasting',
  'price-forecasting',
  'monte-carlo-simulation',
  'market-sentiment',
  'volatility-surface',
  'options-strategy-playbook',
] as const

export function lessonPath(slug: string): string {
  return `/education?lesson=${slug}`
}

const PLAYBOOK = 'options-strategy-playbook'

export const HELP_HINTS: Record<string, HelpHint> = {
  // ── ML models ──
  'vol-forecast': {
    title: 'Volatility forecast',
    body: "This predicts how much the price will swing in the days ahead. It compares three methods (HV21, GARCH, HAR) and marks the one that did best on past data.",
    lessonSlug: 'volatility-forecasting',
  },
  'price-forecast': {
    title: 'Price forecast',
    body: "This guesses where the price may go using two models (ARIMA and an LSTM neural net) plus a simple 'no change' baseline. The baseline often wins — short-term moves are nearly random.",
    lessonSlug: 'price-forecasting',
  },
  'monte-carlo': {
    title: 'Monte-Carlo simulation',
    body: "This runs thousands of pretend futures for the price to see how your trade might end up. POP is the share that made money; the chart shows how often each result happened.",
    lessonSlug: 'monte-carlo-simulation',
  },
  'sentiment': {
    title: 'News sentiment',
    body: "This reads recent headlines and scores the mood from negative to positive, counting newer news more. News is noisy, so treat it as one clue, not a sure thing.",
    lessonSlug: 'market-sentiment',
  },
  'vol-surface': {
    title: 'Volatility surface',
    body: "This shows the market's expected swing for every strike and expiry at once. Its shape — the 'smile' and how it changes over time — reveals where traders see the most risk.",
    lessonSlug: 'volatility-surface',
  },
  // ── Strategies (all link to the playbook) ──
  'bull_call_spread': { title: 'Bull call spread', body: "A bet the stock rises a little. You buy a call and sell a higher one to lower the cost. Both your gain and loss are capped.", lessonSlug: PLAYBOOK },
  'bear_put_spread': { title: 'Bear put spread', body: "A bet the stock falls a little. You buy a put and sell a lower one to cut the cost. Gain and loss are both limited.", lessonSlug: PLAYBOOK },
  'long_straddle': { title: 'Long straddle', body: "A bet on a BIG move either way. You buy a call and a put at the same strike. You win on a large jump or drop; the cost is your most you can lose.", lessonSlug: PLAYBOOK },
  'long_strangle': { title: 'Long strangle', body: "Like a straddle but cheaper: buy a call and a put at different strikes. You need an even bigger move to profit. Loss is limited to what you paid.", lessonSlug: PLAYBOOK },
  'iron_condor': { title: 'Iron condor', body: "A bet the stock stays calm and range-bound. You sell a call spread and a put spread, keeping cash if it stays in the middle. Risk is capped.", lessonSlug: PLAYBOOK },
  'iron_butterfly': { title: 'Iron butterfly', body: "A bet the stock stays near one price. Like an iron condor but tighter, so it pays more if you're right and loses faster if you're wrong. Risk is capped.", lessonSlug: PLAYBOOK },
  'covered_call': { title: 'Covered call', body: "You own 100 shares and sell a call to earn extra cash. If the stock jumps past the strike, your shares may be sold. Good in flat or slightly-up markets.", lessonSlug: PLAYBOOK },
  'cash_secured_put': { title: 'Cash-secured put', body: "You sell a put and set cash aside to buy the stock if it drops. You earn the premium now and may buy shares at a discount. Best when you'd happily own it.", lessonSlug: PLAYBOOK },
  'long_calendar': { title: 'Long calendar', body: "You sell a near-term option and buy a longer-term one at the same strike. It profits from time passing with steady prices. Loss is limited to the cost.", lessonSlug: PLAYBOOK },
  'bull_put_spread': { title: 'Bull put spread', body: "A bet the stock stays up or rises. You sell a put and buy a lower one for protection, keeping cash if it holds. Max loss is capped.", lessonSlug: PLAYBOOK },
  'bear_call_spread': { title: 'Bear call spread', body: "A bet the stock stays down or falls. You sell a call and buy a higher one for protection, keeping cash if it stays below. Risk is capped.", lessonSlug: PLAYBOOK },
  'short_straddle': { title: 'Short straddle', body: "A bet the stock barely moves. You sell a call and a put at the same strike to collect premium. A big move can cause large losses — risk is open-ended.", lessonSlug: PLAYBOOK },
  'short_strangle': { title: 'Short strangle', body: "Like a short straddle but with wider strikes. You collect premium if the stock stays calm. A big surprise move can lose a lot — risk is open-ended.", lessonSlug: PLAYBOOK },
  'protective_put': { title: 'Protective put', body: "Insurance for shares you own: buy a put so a crash can't hurt you below the strike. You pay a premium, like an insurance bill, and your downside is capped.", lessonSlug: PLAYBOOK },
  'collar': { title: 'Collar', body: "Protect shares cheaply: buy a put for safety and sell a call to pay for it. Your loss and gain are both boxed in. Good for guarding gains.", lessonSlug: PLAYBOOK },
  'call_ratio_spread': { title: 'Call ratio spread', body: "You buy one call and sell more calls higher up. Cheap to enter and profits from a small rise, but a big jump can hurt — risk can be open-ended.", lessonSlug: PLAYBOOK },
  'put_ratio_spread': { title: 'Put ratio spread', body: "You buy one put and sell more puts lower down. Cheap to enter and profits from a small drop, but a big crash can hurt — risk can be open-ended.", lessonSlug: PLAYBOOK },
  'jade_lizard': { title: 'Jade lizard', body: "You sell a put and a call spread above. You collect good premium with no risk if the stock rises. Best when you expect calm-to-up and steady volatility.", lessonSlug: PLAYBOOK },
  'call_butterfly': { title: 'Call butterfly', body: "A low-cost bet the stock lands near one price above today. You profit most at the middle strike. Gain and loss are both small and capped.", lessonSlug: PLAYBOOK },
  'put_butterfly': { title: 'Put butterfly', body: "A low-cost bet the stock lands near one price below today. You profit most at the middle strike. Risk and reward are both small and capped.", lessonSlug: PLAYBOOK },
  'broken_wing_butterfly': { title: 'Broken-wing butterfly', body: "A butterfly with uneven wings, so it can be entered for little or no cost and often removes risk on one side. You aim for the stock to land near the middle. Risk is capped.", lessonSlug: PLAYBOOK },
}

export function hintProps(key: string): { title: string; body: string; learnMoreTo?: string } {
  const h = HELP_HINTS[key]
  if (!h) return { title: 'Help', body: 'More information coming soon.' }
  return { title: h.title, body: h.body, learnMoreTo: lessonPath(h.lessonSlug) }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pnpm -C apps/web vitest run src/content/helpHints.test.ts`
Expected: PASS (4 tests). If any `body too long`, trim that blurb to ≤240 chars.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/content/helpHints.ts apps/web/src/content/helpHints.test.ts
git commit -m "feat(web): shared helpHints registry (ML models + 21 strategies)"
```

---

### Task 3: InfoHint on the ML model panels

**Files:**
- Modify: `apps/web/src/features/models/ForecastPanel.tsx`
- Modify: `apps/web/src/features/models/PriceForecastPanel.tsx`
- Modify: `apps/web/src/features/models/MonteCarloPanel.tsx`
- Modify: `apps/web/src/features/models/SentimentGauge.tsx`
- Modify: `apps/web/src/features/markets/IvCurves.tsx`
- Test: `apps/web/src/features/models/HelpHints.panels.test.tsx` (new)

- [ ] **Step 1: Write the failing test** — `apps/web/src/features/models/HelpHints.panels.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ForecastPanel } from './ForecastPanel'
import { PriceForecastPanel } from './PriceForecastPanel'
import { MonteCarloPanel } from './MonteCarloPanel'
import { SentimentGauge } from './SentimentGauge'
import type { VolForecast, PriceForecast, MonteCarloResult, Sentiment } from '../../lib/models'

const wrap = (ui: React.ReactNode) => <MemoryRouter>{ui}</MemoryRouter>

const VOL: VolForecast = {
  horizon_days: 5, primary_model: 'garch', primary_forecast: [20, 20, 20, 20, 20], primary_ci_95: null,
  alternative_models: [], validation: { holdout_days: 40, garch_mae: 0.1, hv21_mae: 0.1, har_mae: 0.1, lift: 0 },
  model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true, params: { omega: 0, alpha: 0.1, beta: 0.8 },
}
const PRICE: PriceForecast = {
  ticker: 'AAPL', market: 'US', as_of: 'x', horizon_days: 3, last_close: 100, primary_model: 'naive',
  models: [{ model: 'naive', path: [100, 100, 100], ci_95: null, expected_return_pct: 0, direction: 'flat', holdout_mae: 1, directional_accuracy: 0.5 }],
  validation: { holdout_days: 60, n_origins: 5, best_model: 'naive' }, approximate: true, disclaimer: 'x',
}
const MC = {
  pop: 0.5, ev: 1, paths: 100, histogram: { counts: [1], bin_edges: [0, 1] }, percentiles: { p5: 0, p50: 0, p95: 0 },
  max_profit_observed: 1, max_loss_observed: -1, model: 'bsm', approximate: true, seed: 0, underlying: 'AAPL',
  market: 'US', spot: 100, sigma: 0.2, sigma_source: 'garch', horizon_days: 5, rate: 0.05,
  sentiment: { applied: false },
} as MonteCarloResult
const SENT: Sentiment = {
  ticker: 'AAPL', market: 'US', score: 0.2, label: 'bullish', confident: true, n_headlines: 5, has_data: true,
  computed_at: null, as_of: null,
}

describe('ML panels carry contextual help', () => {
  it.each([
    ['vol', <ForecastPanel forecast={VOL} />],
    ['price', <PriceForecastPanel forecast={PRICE} />],
    ['mc', <MonteCarloPanel result={MC} />],
    ['sentiment', <SentimentGauge sentiment={SENT} />],
  ])('%s panel renders an info-hint', (_n, ui) => {
    render(wrap(ui))
    expect(screen.getAllByTestId('info-hint').length).toBeGreaterThan(0)
  })
})
```
NOTE: this `.test.tsx` needs `import type React from 'react'` at the top for the JSX in the `it.each` table.

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm -C apps/web vitest run src/features/models/HelpHints.panels.test.tsx`
Expected: FAIL — no `info-hint` in these panels yet.

- [ ] **Step 3: Add the hint to each panel.** Import at top of each file:
```tsx
import { InfoHint } from '../../components/InfoHint'
import { hintProps } from '../../content/helpHints'
```

`ForecastPanel.tsx` — in the `<figcaption>`, after the `Vol forecast · {…}d` text and before/after the primary badge, add:
```tsx
        <InfoHint {...hintProps('vol-forecast')} />
```

`PriceForecastPanel.tsx` — in its `<figcaption>`, after `Price forecast · {horizon_days}d`, add:
```tsx
        <InfoHint {...hintProps('price-forecast')} />
```

`MonteCarloPanel.tsx` — in the first header row (the flex row with POP/EV), prepend an inline hint. Wrap the existing POP/EV row's leading content; simplest is to add, right after the opening `<div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">`:
```tsx
        <span className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">Simulation <InfoHint {...hintProps('monte-carlo')} /></span>
```

`SentimentGauge.tsx` — both the `sentiment-empty` and `sentiment-panel` branches have a `<p>News sentiment</p>` header; append the hint inside each:
```tsx
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">News sentiment <InfoHint {...hintProps('sentiment')} /></p>
```

`IvCurves.tsx` — read the file; find the InfoHint whose `learnMoreTo` targets the volatility-surface lesson (the vol-surface overview hint). Replace its inline `title`/`body`/`learnMoreTo` props with `{...hintProps('vol-surface')}`. Leave the other two InfoHints unchanged. Add the `hintProps` import.

- [ ] **Step 4: Run to verify it passes**

Run: `pnpm -C apps/web vitest run src/features/models/HelpHints.panels.test.tsx`
Expected: PASS. Then run the existing panel tests to confirm no regressions:
`pnpm -C apps/web vitest run src/features/models src/features/markets`
Expected: all pass.

- [ ] **Step 5: Typecheck + commit**

Run: `pnpm -C apps/web typecheck` → clean.
```bash
git add apps/web/src/features/models/ForecastPanel.tsx apps/web/src/features/models/PriceForecastPanel.tsx apps/web/src/features/models/MonteCarloPanel.tsx apps/web/src/features/models/SentimentGauge.tsx apps/web/src/features/markets/IvCurves.tsx apps/web/src/features/models/HelpHints.panels.test.tsx
git commit -m "feat(web): contextual help on vol/price forecast, Monte-Carlo, sentiment, vol surface"
```

---

### Task 4: Per-strategy InfoHint on the picker cards + selected summary

**Files:**
- Modify: `apps/web/src/features/strategies/TemplatePicker.tsx`
- Modify: `apps/web/src/features/strategies/SelectedStrategy.tsx`
- Test: `apps/web/src/features/strategies/TemplatePicker.help.test.tsx` (new)

**Key constraint:** the TemplatePicker card is currently a `<button>`. An `InfoHint` renders its own `<button>`, and nesting `<button>` inside `<button>` is invalid HTML. So convert the card to a `role="button"` div (keeps `data-testid`/`data-selected`/onClick) and wrap the InfoHint in a `stopPropagation` span so clicking "?" does not apply the template.

- [ ] **Step 1: Write the failing test** — `apps/web/src/features/strategies/TemplatePicker.help.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { TemplatePicker } from './TemplatePicker'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

describe('TemplatePicker per-strategy help', () => {
  it('renders an info-hint on a card and clicking it does NOT apply the template', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) return new Response(JSON.stringify({ templates: [
        { key: 'bull_call_spread', name: 'Bull Call Spread', description: 'x', market_view: 'bullish', vol_view: 'neutral', net: 'debit', risk: 'defined', reward: 'defined', legs: 2, complexity: 'beginner' }] }), { status: 200 })
      return new Response('{}', { status: 200 })
    }))
    const onApply = vi.fn(); const onPick = vi.fn()
    render(wrap(<TemplatePicker underlying="AAPL" expiry="2026-12-18" atmStrike={100} onApply={onApply} onPick={onPick} />))
    const hint = await screen.findByTestId('info-hint')
    fireEvent.click(hint)
    expect(onPick).not.toHaveBeenCalled()
    expect(screen.getByTestId('info-hint-popover')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm -C apps/web vitest run src/features/strategies/TemplatePicker.help.test.tsx`
Expected: FAIL — no info-hint in the card.

- [ ] **Step 3: Edit `TemplatePicker.tsx`.** Add imports:
```tsx
import { InfoHint } from '../../components/InfoHint'
import { hintProps } from '../../content/helpHints'
```
Convert the card from `<button …>` to a div-role button, and add the hint in the title row. Replace the whole `<button … >…</button>` card block (the one keyed by `t.key`) with:
```tsx
          <div
            key={t.key}
            role="button"
            tabIndex={0}
            data-testid={`tpl-${t.key}`}
            data-selected={isSelected ? 'true' : undefined}
            onClick={() => apply(t.key)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); apply(t.key) } }}
            title={t.description}
            className={`flex cursor-pointer flex-col gap-1.5 rounded-lg border p-3 text-left transition-colors ${
              isSelected ? 'border-accent bg-accent/10 ring-1 ring-accent/40' : 'border-line bg-panel hover:border-lineSoft'
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className={`text-[13px] font-medium ${isSelected ? 'text-accent' : 'text-txt'}`}>
                {isSelected ? '✓ ' : ''}{t.name}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">{t.complexity}</span>
                <span onClick={(e) => e.stopPropagation()}><InfoHint {...hintProps(t.key)} /></span>
              </span>
            </div>
            <p className="text-[11px] leading-snug text-txtDim">{t.description}</p>
            <div className="flex flex-wrap gap-1.5">
              <Badge>{t.net}</Badge>
              <Badge>{t.legs} legs</Badge>
              <Badge tone={t.risk === 'undefined' ? 'warn' : undefined}>
                {t.risk === 'undefined' ? 'undefined risk' : 'defined risk'}
              </Badge>
            </div>
          </div>
```

- [ ] **Step 4: Edit `SelectedStrategy.tsx`.** It receives `config` (with `underlying` + `legs`) but NOT a template key. Add an optional `templateKey?: string` prop; when present, render a hint in the header. Add imports:
```tsx
import { InfoHint } from '../../components/InfoHint'
import { hintProps } from '../../content/helpHints'
```
Change the signature to `export function SelectedStrategy({ config, onChange, templateKey }: { config: StrategyConfig; onChange?: () => void; templateKey?: string })` and, in the header `<p>` (the "Selected strategy · …" line), append:
```tsx
          {templateKey && <InfoHint {...hintProps(templateKey)} />}
```
Pass `templateKey` from the call sites that know the key: in `pages/Strategies.tsx` ready-made tab, `<SelectedStrategy config={config} templateKey={readyKey ?? undefined} />`; in `pages/Models.tsx` MC tab, `<SelectedStrategy config={config} onChange={clearSelection} templateKey={selectedKey ?? undefined} />`. (Both pages already track the picked key as `readyKey`/`selectedKey`.)

- [ ] **Step 5: Run to verify it passes (and no regressions)**

Run: `pnpm -C apps/web vitest run src/features/strategies src/pages/Strategies src/pages/Models`
Expected: all pass — including the existing `Strategies.test.tsx` (it clicks `tpl-bull_call_spread`, which still works on the role=button div, and asserts `data-selected`).

- [ ] **Step 6: Typecheck + commit**

Run: `pnpm -C apps/web typecheck` → clean.
```bash
git add apps/web/src/features/strategies/TemplatePicker.tsx apps/web/src/features/strategies/SelectedStrategy.tsx apps/web/src/pages/Strategies.tsx apps/web/src/pages/Models.tsx apps/web/src/features/strategies/TemplatePicker.help.test.tsx
git commit -m "feat(web): per-strategy contextual help on template cards + selected summary"
```

---

### Task 5: Academy parse test for the new lessons + final verification

**Files:**
- Modify: `apps/web/src/academy/parseModule.test.ts` (or add a sibling test that loads the new lesson files)

- [ ] **Step 1: Add a test asserting the 5 new lessons parse and are free.** Append to `apps/web/src/academy/parseModule.test.ts`:

```ts
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const MODULES_DIR = join(__dirname, '../../../../packages/content/saalr_content/modules')
const NEW = [
  ['80-volatility-forecasting.md', 'volatility-forecasting'],
  ['90-price-forecasting.md', 'price-forecasting'],
  ['100-monte-carlo-simulation.md', 'monte-carlo-simulation'],
  ['110-market-sentiment.md', 'market-sentiment'],
  ['120-options-strategy-playbook.md', 'options-strategy-playbook'],
] as const

describe('new help lessons', () => {
  it.each(NEW)('%s parses, is free, and has the expected slug', (file, slug) => {
    const m = parseModule(readFileSync(join(MODULES_DIR, file), 'utf8'))
    expect(m.slug).toBe(slug)
    expect(m.minTier).toBe('free')
    expect(m.title.length).toBeGreaterThan(0)
    expect(m.body.length).toBeGreaterThan(200)
  })
})
```
(Confirm `parseModule` is already imported at the top of the file; if not, add `import { parseModule } from './parseModule'`. Adjust the `../../../../` depth if the test resolves the modules dir incorrectly — verify with a quick `existsSync` check while writing.)

- [ ] **Step 2: Run it**

Run: `pnpm -C apps/web vitest run src/academy/parseModule.test.ts`
Expected: PASS.

- [ ] **Step 3: Full regression**

Run: `pnpm -C apps/web vitest run src/content src/features/models src/features/strategies src/features/markets src/academy src/pages` then `pnpm -C apps/web typecheck`.
Expected: all green, typecheck clean.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/academy/parseModule.test.ts
git commit -m "test(content): assert the 5 new help lessons parse as free"
```

- [ ] **Step 5: Note for the running app**

The API caches the content catalog at startup, so the 5 new lessons appear at `/education?lesson=<slug>` only after the **dev API is restarted** (same as any new lesson). Flag this to the user; do not restart without asking.

---

## Final verification (after all tasks)
- [ ] `pnpm -C apps/web vitest run src/content src/features src/academy src/pages` — all pass.
- [ ] `pnpm -C apps/web typecheck` — clean.
- [ ] Dispatch a final code-reviewer over the whole diff.
- [ ] superpowers:finishing-a-development-branch (do NOT push until the user asks).

## Self-review notes (plan author)
- **Spec coverage:** 5 lessons → Task 1; registry + test → Task 2; ML placements + IvCurves refactor → Task 3; 21 strategy + selected-summary placements → Task 4; lesson parse test + regression → Task 5. ✅
- **Type consistency:** `hintProps(key)` returns `{title, body, learnMoreTo?}` matching `InfoHint`'s props (`title`, `body`, `learnMoreTo?`, `label?`); `ACADEMY_SLUGS`/`lessonSlug` used in the registry test match the lesson frontmatter slugs in Task 1. `templateKey` prop added to `SelectedStrategy` is threaded from both call sites. ✅
- **Nested-button hazard** explicitly handled (card → role=button div + stopPropagation on the hint). ✅
- **Honesty:** every blurb names the limitation (baseline often wins, news is noisy, undefined-risk strategies). ✅
