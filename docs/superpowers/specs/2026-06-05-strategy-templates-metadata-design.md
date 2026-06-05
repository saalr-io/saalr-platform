# Strategy Template Library + Metadata — Design Spec

**Date:** 2026-06-05
**Slice:** Strategy templates expansion (Slice A of a two-slice "regime drives templates" effort)
**Status:** Approved design, ready for implementation plan

## Context

Saalr already ships 9 ready-made strategy templates (`packages/core/saalr_core/strategies/templates.py`) surfaced via `GET /v1/strategies/templates` and a flat bullish/bearish/neutral `TemplatePicker` on `/app/strategies`. The goal is a Sensibull-style strategy library: more structures, richer per-template metadata, and a browse/filter UI.

This is **Slice A** of a two-slice effort. **Slice B (separate, next)** adds a rule-based market-regime engine (`/app/ideas`) that *recommends* templates by scoring them against the detected regime. Slice A builds the foundation Slice B's recommender depends on: the expanded library and the structured metadata schema. Slice A ships standalone value (a real strategy browser) with **no regime dependency**.

### Decisions locked during brainstorming
- **Integration vision:** regime drives templates (delivered across A→B; A first).
- **Regime engine (Slice B):** transparent rule-based classifier, not a trained model — fits the platform's validation-first / explainability ethos.
- **Tiering (Slice B):** free base (trend + vol-percentile + momentum from `bars`) + premium layer (GARCH forward-vol, FinBERT sentiment) that degrades gracefully when absent.
- **UI surface (Slice B):** dedicated `/app/ideas` screen.
- **Template scope (this slice):** expand 9 → ~21; include undefined-risk structures with explicit risk badges.

## Goal

Expand the template library to 21 structures, attach a recommender-ready metadata schema to every template, and replace the flat category grouping in `TemplatePicker` with a filter/badge browser. No new API endpoints; metadata flows additively through the existing passthrough route.

## Architecture

Pure-core change plus a typed-frontend change. No new packages, no new endpoints, no DB.

```
saalr_core.strategies.templates   (pure: builders + enriched _REGISTRY + list_templates)
        │  list_templates() -> richer dicts (additive)
        ▼
GET /v1/strategies/templates       (unchanged passthrough: {"templates": [...]})
        │
        ▼
apps/web lib/strategies.ts          (TemplateDescriptor extended with metadata)
        │
        ▼
features/strategies/TemplatePicker  (filter chips + per-template badges)
        │  POST /templates/{key}/build  (unchanged)
        ▼
existing builder / payoff / analyze flow
```

## Metadata schema

Every `_REGISTRY` entry carries these fields (this is the interface Slice B's recommender keys off, so it is fixed now):

| Field | Type / values | Meaning |
|---|---|---|
| `key` | string | registry key (unchanged) |
| `name` | string | display name (unchanged) |
| `description` | string | one-line description (unchanged) |
| `market_view` | `bullish` \| `bearish` \| `neutral` \| `volatile` | directional expectation; `volatile` = expects a big move, direction-agnostic |
| `vol_view` | `long_vol` \| `short_vol` \| `neutral` | buying premium / wants IV up (`long_vol`) vs selling premium / wants IV down (`short_vol`) |
| `net` | `debit` \| `credit` \| `mixed` | net **option premium** at entry (excludes equity/cash-collateral cash flow, so a covered call is `credit` on the short call even though buying 100 shares is a large cash outlay); `mixed` when long and short option premium roughly offset (e.g. collar) |
| `risk` | `defined` \| `undefined` | is maximum loss capped? |
| `reward` | `defined` \| `undefined` | is maximum gain capped? |
| `legs` | int | total leg count including any equity/cash leg |
| `complexity` | `beginner` \| `intermediate` \| `advanced` | UI filtering + retail-safety signposting |

The current `category` field is **replaced** by `market_view` (superset that adds `volatile`). All consumers migrate to `market_view`.

`list_templates()` returns a list of dicts containing every field above.

## Template re-tagging (existing 9)

The existing builders are unchanged; only their registry metadata is enriched. Notable correction:

| key | market_view | vol_view | net | risk | reward | legs | complexity |
|---|---|---|---|---|---|---|---|
| bull_call_spread | bullish | neutral | debit | defined | defined | 2 | beginner |
| bear_put_spread | bearish | neutral | debit | defined | defined | 2 | beginner |
| long_straddle | **volatile** | long_vol | debit | defined | undefined | 2 | intermediate |
| long_strangle | **volatile** | long_vol | debit | defined | undefined | 2 | intermediate |
| iron_condor | neutral | short_vol | credit | defined | defined | 4 | intermediate |
| iron_butterfly | neutral | short_vol | credit | defined | defined | 4 | intermediate |
| covered_call | bullish | short_vol | credit | undefined | defined | 2 | beginner |
| cash_secured_put | bullish | short_vol | credit | undefined | defined | 2 | beginner |
| long_calendar | neutral | long_vol | debit | defined | undefined | 2 | advanced |

(`covered_call`/`cash_secured_put` carry `risk: undefined` because the underlying/assignment exposure is large though not literally infinite; this is the honest retail-facing read. `long_calendar` keeps its existing single-expiry simplification — a true multi-expiry calendar is deferred, see Out of scope.)

## New templates (12)

All build with the existing `build(key, underlying, expiry, atm_strike, width)` signature. `k` = atm_strike, `w` = width, `e` = expiry, `u` = underlying. Ratios are fixed per template (no new params). Leg helpers reuse the existing `_opt`, `EquityLeg`, `CashLeg`.

| key | legs (structure) | market_view | vol_view | net | risk | reward | complexity |
|---|---|---|---|---|---|---|---|
| bull_put_spread | sell put @k, buy put @k−w | bullish | short_vol | credit | defined | defined | beginner |
| bear_call_spread | sell call @k, buy call @k+w | bearish | short_vol | credit | defined | defined | beginner |
| short_straddle | sell call @k, sell put @k | neutral | short_vol | credit | undefined | defined | advanced |
| short_strangle | sell call @k+w, sell put @k−w | neutral | short_vol | credit | undefined | defined | advanced |
| protective_put | buy 100 shares, buy put @k−w | bullish | long_vol | debit | defined | undefined | beginner |
| collar | buy 100 shares, buy put @k−w, sell call @k+w | bullish | neutral | mixed | defined | defined | intermediate |
| call_ratio_spread | buy 1 call @k, sell 2 calls @k+w | bullish | short_vol | credit | undefined | defined | advanced |
| put_ratio_spread | buy 1 put @k, sell 2 puts @k−w | bearish | short_vol | credit | undefined | defined | advanced |
| jade_lizard | sell put @k−w, sell call @k+w, buy call @k+2w | neutral | short_vol | credit | undefined | defined | advanced |
| call_butterfly | buy call @k−w, sell 2 calls @k, buy call @k+w | neutral | long_vol | debit | defined | defined | intermediate |
| put_butterfly | buy put @k+w, sell 2 puts @k, buy put @k−w | neutral | long_vol | debit | defined | defined | intermediate |
| broken_wing_butterfly | buy call @k−w, sell 2 calls @k, buy call @k+2w | neutral | short_vol | credit | defined | defined | advanced |

This brings the library to **21 templates**, covering every (market_view × vol_view) cell the recommender needs.

### Undefined-risk handling
`short_straddle`, `short_strangle`, `call_ratio_spread`, `put_ratio_spread`, `jade_lizard` (and the existing covered/cash-secured) are `risk: undefined`. They are included because Slice B needs short-premium structures for high-vol regimes, but the UI must render the `undefined` risk tag prominently so retail users see the exposure.

## Frontend changes

### `lib/strategies.ts`
Extend `TemplateDescriptor`:
```ts
export interface TemplateDescriptor {
  key: string
  name: string
  description: string
  market_view: 'bullish' | 'bearish' | 'neutral' | 'volatile'
  vol_view: 'long_vol' | 'short_vol' | 'neutral'
  net: 'debit' | 'credit' | 'mixed'
  risk: 'defined' | 'undefined'
  reward: 'defined' | 'undefined'
  legs: number
  complexity: 'beginner' | 'intermediate' | 'advanced'
}
```
(`category` removed.)

### `TemplatePicker.tsx`
- Replace the fixed `['bullish','bearish','neutral']` grouping with **filter chips**: a market-view filter (All / Bullish / Bearish / Neutral / Volatile) and a vol-view filter (All / Long vol / Short vol). Client-side filtering of the templates list.
- Each template renders as a card/row with: name, description (title/tooltip), and **badges** — `net` (debit/credit), `risk` (with `undefined` visually emphasized via the warn token), `legs` count, and a `complexity` indicator. Theme tokens only.
- "Apply" behavior unchanged (`useBuildTemplate` → `onApply(cfg)`).

## Testing

**Core (`packages/core/tests/test_strategy_templates.py`):**
- Per new builder: assert the produced `StrategyConfig` legs match the spec table (option type, side, strike relative to `k`/`w`, qty; equity/cash legs where applicable). E.g. `bull_put_spread` → 2 option legs, sell put @k + buy put @k−w.
- **Schema-completeness test:** every entry in `list_templates()` has all metadata fields present and within the allowed value sets (so Slice B can trust the schema). This guards against a new template missing a tag.
- `build(key, ...)` round-trips for all 21 keys without raising; unknown key raises `KeyError`.
- Re-tagging does not change build math — existing payoff/pop tests stay green.

**Web (`TemplatePicker.test.tsx`):**
- Filter logic: selecting "Bullish" shows only `market_view==='bullish'` templates; "Short vol" filters by `vol_view`.
- Badge rendering: an `undefined`-risk template shows the risk badge; `net` badge reflects debit/credit.

## Error handling
No new failure modes. `build()` still raises `KeyError` on unknown key (existing 4xx mapping in the router is unchanged). The metadata is static data, not computed, so there is no runtime validation path beyond the completeness test at build/test time.

## Out of scope (deferred)
- **Slice B:** regime engine, `/v1/market/regime`, `/app/ideas`, recommendation scoring. This spec only produces the library + metadata they will consume.
- **Multi-expiry templates** (true calendar, diagonal spreads): require extending the `build()` signature with a second expiry; deferred to a follow-up. The existing single-expiry `long_calendar` is retained unchanged.
- **Ratio/quantity parameterization** in the build API (custom ratios beyond the fixed 1×2): not needed now.

## Build sequence (for the plan)
1. Core: add 12 builders + enrich `_REGISTRY` (all 21) + update `list_templates()`; tests (per-builder legs + schema completeness + round-trip).
2. Frontend: extend `TemplateDescriptor`; rebuild `TemplatePicker` (filters + badges) + tests.
3. Gate: core pytest green; web typecheck/lint/test/build green; existing strategy tests unaffected.
