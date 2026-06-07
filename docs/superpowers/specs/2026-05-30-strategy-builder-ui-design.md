# Strategy builder UI (7b) — design

**Date:** 2026-05-30
**Slice:** LLD §13 step 7 — multi-leg builder UI. The front-end half (7b) of the strategy builder; consumes the 7a backend.
**Status:** Approved design, pre-plan.
**Builds on:** 7a backend (`/v1/strategies` CRUD, `/templates`, `/analyze`), the React web shell, and the Greeks/vol-surface slice.

## Purpose

A Sensibull-inspired, chart-first strategy builder at `/strategies`: pick a ready-made
strategy or build your own multi-leg position, see the payoff diagram (expiration +
target-date), the key stats (max P/L, breakevens, POP, net premium, net Greeks), and
save/load strategies. Free tier sees the expiration payoff from entered prices; Pro unlocks
live Greeks, POP, and the target-date curve.

## Decisions (locked during brainstorming)

1. **Layout B — chart-first:** full-width SVG payoff chart on top, a stats strip beneath, the
   leg/template controls + Analyze in a panel below. Three tabs: Ready-made · Build your own · Saved.
2. **Custom SVG payoff chart** — no charting library (web app stays on react/router/query only).
3. **Full builder in one slice:** Build-your-own (leg editor) + Ready-made templates + live
   Analyze + payoff chart + stats + Save/list/load.
4. **Code structure (Approach A):** feature folder `src/features/strategies/`; route in
   `pages/Strategies.tsx`; HTTP client in `lib/strategies.ts`.
5. **Tier UX:** CRUD + pure expiration payoff for all tiers; live analysis (net Greeks, POP,
   target-date curve, auto-filled prices) requires `vol_surface` (Pro) — a 402 surfaces as an
   upgrade nudge, not an error.

## Architecture

```
apps/web/src/
  lib/strategies.ts                  # typed HTTP client + TS types + EntitlementError
  pages/Strategies.tsx               # route: tabs, shared state, orchestration (layout B)
  features/strategies/
    hooks.ts                         # React Query hooks (queries + mutations)
    types.ts                         # shared view types (re-exports from lib where useful)
    scale.ts                         # PURE curve -> SVG-pixel math (unit-tested)
    PayoffChart.tsx                  # presentational SVG chart (curves + markers)
    StatsPanel.tsx                   # stat cards; hides live-only stats when absent
    LegEditor.tsx                    # add/edit/remove leg rows
    TemplatePicker.tsx               # category-grouped ready-made chips
    SavedList.tsx                    # saved strategies: load / archive / state badge
  app/routes / Sidebar               # /strategies route already present in Sidebar
```

### Data flow
1. `Strategies.tsx` owns the working `StrategyConfig` (underlying, expiry, legs), the selected
   tab, the live toggle + target date, and the latest `AnalyzeResult`.
2. Editing legs (debounced) or clicking **Analyze** calls `useAnalyze(config, {live, target_date})`.
3. `AnalyzeResult` flows into `PayoffChart` (curves + markers) and `StatsPanel` (numbers).
4. Save → `useCreateStrategy` (draft); **Saved** tab lists via `useStrategies`, loads a config
   back into the builder, archives via `useArchive`.

## Components

### `lib/strategies.ts`
- **Types**: `Leg` = discriminated union (`OptionLeg`/`EquityLeg`/`CashLeg` on `kind`),
  `StrategyConfig` (`underlying`, `legs`), `Strategy` (saved: `strategy_id`, `name`, `state`,
  `market`, `config`, `created_at`, `updated_at`), `TemplateDescriptor`
  (`key`, `name`, `category`, `description`), `AnalyzeResult`:
  - pure: `expiration_curve: {spot:number; pnl:number}[]`, `breakevens:number[]`,
    `max_profit:number|null`, `max_loss:number|null`, `unbounded_profit:boolean`,
    `unbounded_loss:boolean`, `net_premium:number`, `risk_reward:number|null`
  - live-only (optional): `net_greeks`, `probability_of_profit`, `target_date_curve`,
    `spot`, `data_provider`, `risk_free_source`
- **Functions**: `listStrategies(cursor?)`, `getStrategy(id)`, `createStrategy(body)`,
  `updateStrategy(id, body)`, `transitionStrategy(id, target)`, `archiveStrategy(id)`,
  `listTemplates()`, `buildTemplate(key, params)`, `analyzeStrategy(config, opts)`.
- **Errors**: reuse `BASE` + `authHeaders()` from `api.ts`. 401 → clear token (existing
  pattern). **402 → throw `EntitlementError`** (carries the code) so the builder shows an
  upgrade nudge. Other non-OK → `Error` with the server `error.code`.

### `features/strategies/hooks.ts` (React Query)
- Queries: `useStrategies()`, `useStrategy(id)`, `useTemplates()` (static → long `staleTime`).
- Mutations: `useCreateStrategy`, `useUpdateStrategy`, `useTransition`, `useArchive` (each
  invalidates `['strategies']`), `useAnalyze` (on-demand; returns `AnalyzeResult`; the caller
  catches `EntitlementError`).

### `features/strategies/scale.ts` (pure, unit-tested)
- `bounds(curves) -> {minS, maxS, minP, maxP}` over one or more curves.
- `toPixels(curve, bounds, {width, height, pad}) -> {x:number; y:number}[]` mapping
  (spot, pnl) → SVG coords (y inverted).
- `zeroY(bounds, dims)`, `xFor(spot, ...)`, `yFor(pnl, ...)` helpers for axis/markers.
- Handles empty curves and a flat (single-value) P&L range without divide-by-zero.

### `PayoffChart.tsx` (presentational)
Props: `expirationCurve`, `targetDateCurve?`, `spot?`, `breakevens`, `width/height`. Renders:
the green/red P&L zones (polygons vs the zero line), the zero line, the **solid expiration**
polyline, the **dashed target-date** path (when present), the spot crosshair, breakeven dots,
and a hover readout (nearest sample → `@ spot`, `P&L`). No data fetching, no business logic.

### `StatsPanel.tsx`
Cards: max profit / max loss (show "Unbounded" when the flag is set, not a number), breakeven(s),
**POP** (with an `*approximate` footnote), net premium (debit/credit), and net Greeks
(Δ/Γ/Θ/V) when live. Live-only cards render only when the field is present; otherwise a compact
"Upgrade to Pro for live Greeks, POP & target-date" hint.

### `LegEditor.tsx`
Underlying + expiry inputs; a row per leg (kind, option_type, side, strike, qty, optional
`entry_price`); add/remove. Emits an updated `StrategyConfig` upward (controlled).

### `TemplatePicker.tsx`
`useTemplates()` grouped by category (bullish/bearish/neutral) as chips; clicking a chip prompts
for underlying/expiry/ATM strike (defaults from the current config) and calls `buildTemplate` →
loads the returned legs into the builder (switches to Build-your-own to show them).

### `SavedList.tsx`
`useStrategies()` list: name, state badge, updated time; load (config → builder) and archive.

### `pages/Strategies.tsx`
Owns shared state; renders layout B (chart + stats on top, tabbed controls below); wires the
live toggle + target-date picker (Pro); maps `EntitlementError` to the upgrade nudge.
Replaces the current placeholder at the `/strategies` route.

## Error handling
- 402 `EntitlementError` → inline upgrade nudge; the pure payoff still renders if entry prices
  were supplied.
- 401 → token cleared (existing behavior), redirect to login via the existing `RequireAuth`.
- Analyze with missing entry prices + free tier → the pure curve can't compute; show a hint to
  enter prices or upgrade. Validation errors (400/422) → inline message near the offending field.
- Provider/market 503 from the live path → "live data unavailable, showing entered-price payoff".

## Testing (vitest + @testing-library/react, existing setup)
- **`scale.ts`** (pure): curve → expected pixel coords; y-inversion; empty curve; flat P&L
  range (no divide-by-zero); multi-curve bounds.
- **`PayoffChart`**: given a result, renders the expiration polyline, the target-date path only
  when provided, breakeven dots, and the spot marker; hover updates the readout.
- **`StatsPanel`**: "Unbounded" rendering when flags set; live-only cards hidden without live
  fields; POP footnote present.
- **`LegEditor`**: add/remove/edit a leg emits the right `StrategyConfig`.
- **`TemplatePicker`**: selecting a template calls `buildTemplate` and populates legs.
- **Analyze flow** (mocked fetch): pure result renders chart+stats; **402 → upgrade nudge** (no
  crash); live result adds the target-date line + Greeks/POP.
- **`SavedList`**: loads a saved config into the builder; archive calls the mutation.
- **Gate**: `pnpm -C apps/web test:run` + `pnpm -C apps/web typecheck` (`tsc --noEmit`) +
  `pnpm -C apps/web lint`.

## Out of scope
- Backtest / execution / order placement (later slices).
- Editing a saved strategy's config in place beyond load-into-builder + re-save (PATCH exists in
  7a; the UI uses create/load/archive this slice).
- Real-time streaming updates to the chart; the chart is request/response per Analyze.
- Mobile-specific layout polish (desktop-first, matching the current shell).
- India market UI; `market` is carried as `"US"`.
