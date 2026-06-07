# Contextual Help for ML Models & Strategies — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorming)
**Slice:** Add `InfoHint` contextual help across all ML models and all 21 strategies, each with an
8th-grade-level blurb and a "Learn more in OptionsAcademy →" deep-link, backed by a small set of new
academy lessons.

## Goal

Every ML model surface (volatility forecast, price forecast, Monte-Carlo, sentiment, vol surface)
and every strategy template carries a "?" help popover with a short, plain-language explanation a
middle-schooler can follow, plus a link into a matching Options Academy lesson. All blurbs and links
come from a single shared registry so the copy stays consistent and links can't silently rot.

## Context (existing pieces this builds on)

- `apps/web/src/components/InfoHint.tsx` — a "?" badge → popover with `title`, `body`, optional
  `learnMoreTo` (a react-router path) rendering "Learn more in OptionsAcademy →", plus `label`.
  Already used once (in `features/markets/IvCurves.tsx` for the vol surface).
- Options Academy: lessons are markdown in `packages/content/saalr_content/modules/` with frontmatter
  `slug / title / summary / order / min_tier / est_minutes`; parsed by
  `apps/web/src/academy/parseModule.ts`. The Education page deep-links **by whole-lesson slug** via
  `/education?lesson=<slug>` (no section anchors). Seven lessons exist today; only `volatility-surface`
  (70) and `iron-condor-construction` (60) overlap this feature.
- Strategy templates (21) live in `packages/core/saalr_core/strategies/templates.py`, each with a
  `key` (e.g. `bull_call_spread`); the web app fetches them via `/templates` and renders them in
  `features/strategies/TemplatePicker.tsx`.

**Decisions locked during brainstorming:**
1. **Grouped topic lessons** (not one-per-item, not approximate links): a small set of new lessons,
   each InfoHint deep-links to the matching whole lesson.
2. **Per-strategy help on each card**: all 21 templates get their own 8th-grade blurb on the picker
   card (and on the selected-strategy summary), each linking to the strategy playbook lesson.
3. Reading level (~8th grade / Flesch-Kincaid grade 8) is a **content guideline enforced by review**,
   not an automated check (avoids a new readability dependency). A blurb length budget is the only
   mechanical guard.

## New academy lessons

All `min_tier: free`, written at ~8th-grade level: short sentences, common words, one idea per
sentence, concrete analogies, but accurate (academic = correct, not dumbed-down-wrong). Follow the
voice of the existing `70-volatility-surface.md` lesson.

| File | slug | Covers |
|---|---|---|
| `80-volatility-forecasting.md` | `volatility-forecasting` | what volatility is; **GARCH**, **HV21**, **HAR**; why we forecast it; honest limits |
| `90-price-forecasting.md` | `price-forecasting` | **ARIMA**, **LSTM**, the **naive** baseline, walk-forward testing, why the simple guess often wins |
| `100-monte-carlo-simulation.md` | `monte-carlo-simulation` | thousands of "what-if" price paths; reading POP / EV / the histogram |
| `110-market-sentiment.md` | `market-sentiment` | turning news headlines into a mood score; time-weighting; limits (news is noisy) |
| `120-options-strategy-playbook.md` | `options-strategy-playbook` | all 21 templates grouped by market view (bullish / bearish / neutral / volatility) and risk shape |

`order` continues the existing 10-step numbering (80, 90, 100, 110, 120). `est_minutes` ≈ 5–7.

## Shared help registry — `apps/web/src/content/helpHints.ts`

```ts
export interface HelpHint { title: string; body: string; lessonSlug: string }
export const HELP_HINTS: Record<string, HelpHint> = { /* keyed entries */ }
export function lessonPath(slug: string): string  // -> `/education?lesson=${slug}`
export function hintProps(key: string): { title: string; body: string; learnMoreTo: string }
```

- `body` is the ≤~2-sentence 8th-grade blurb (popover is `w-64`, so keep it short).
- Keys: `vol-forecast`, `price-forecast`, `monte-carlo`, `sentiment`, `vol-surface`, plus **one per
  strategy template key** (all 21 from `templates.py`: `bull_call_spread`, `bear_put_spread`,
  `iron_condor`, … — the registry is the source of truth for the strategy key list).
- `hintProps(key)` is the single call sites use: `<InfoHint {...hintProps('vol-forecast')} />`.
- The five ML keys point at the five model lessons (and `vol-surface` at the existing lesson); all 21
  strategy keys point at `options-strategy-playbook`.

## InfoHint placements (UI edits)

| Component | Hint key | Lesson |
|---|---|---|
| `features/models/ForecastPanel.tsx` (vol forecast title) | `vol-forecast` | volatility-forecasting |
| `features/models/PriceForecastPanel.tsx` (title) | `price-forecast` | price-forecasting |
| `features/models/MonteCarloPanel.tsx` (header) | `monte-carlo` | monte-carlo-simulation |
| `features/models/SentimentGauge.tsx` (header) | `sentiment` | market-sentiment |
| `features/markets/IvCurves.tsx` (existing InfoHint) | `vol-surface` | volatility-surface (refactor inline copy → registry) |
| `features/strategies/TemplatePicker.tsx` (each card) | `template.key` | options-strategy-playbook |
| `features/strategies/SelectedStrategy.tsx` (header) | selected `key` | options-strategy-playbook |

The InfoHint sits inline next to each title/header (it uses `<span>`s, so it nests in a
`figcaption`/header without layout breakage). The TemplatePicker card hint must not trigger the
card's own onPick click (stop propagation on the "?").

## Data flow

Static, build-time content only — no API/runtime changes. Call sites read `hintProps(key)` from the
registry and pass it to `<InfoHint>`. The "Learn more" `<Link>` routes (react-router) to
`/education?lesson=<slug>`, where the existing Education page selects that lesson.

## Error handling / edge cases

- A strategy key with no registry entry → `hintProps` returns a safe fallback (generic title/body, no
  `learnMoreTo`) AND the coverage test fails in CI, so the gap is caught at build, not shown to users.
- A `lessonSlug` not present in the academy set → the registry test fails (dead-link guard).
- TemplatePicker "?" click is isolated from card selection (event.stopPropagation).

## Testing

- `apps/web/src/content/helpHints.test.ts`:
  - every one of the 21 strategy template keys (hardcoded expected list mirrored from `templates.py`)
    has a hint;
  - each hint has non-empty `title` and `body`, and a `lessonSlug` ∈ the known academy slug set;
  - each `body` length ≤ 240 chars (popover-size / readability proxy);
  - `lessonPath`/`hintProps` produce `/education?lesson=<slug>`.
- Extend the academy module parse test to assert the 5 new lessons parse, are `min_tier: free`, and
  expose the expected slugs.
- Component tests: `ForecastPanel`, `PriceForecastPanel`, `MonteCarloPanel`, `SentimentGauge` each
  render an `info-hint`; a `TemplatePicker` card renders a per-strategy `info-hint` whose click does
  NOT fire `onPick`; `SelectedStrategy` renders an `info-hint`.
- Existing Education deep-link test already covers `?lesson=` selection.

## Out of scope (YAGNI)

- Section-anchor deep-linking inside a lesson (Education links whole lessons only).
- Automated readability scoring / a Flesch-Kincaid dependency (guideline + length budget only).
- Free news-source / RSS sentiment integration — tracked as a **separate** sentiment-pipeline slice.
- Any backend/API change (this is static front-end content).
