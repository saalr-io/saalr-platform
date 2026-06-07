# Sensibull-style Option Chain UX — Design Spec

**Date:** 2026-06-05
**Slice:** Option chain table redesign (`/app/markets` → Chain tab)
**Status:** Approved design, ready for implementation plan

## Context

The Markets page (`apps/web/src/pages/Markets.tsx`) already has the ticker input, an expiry selector populated from `iv-surface.expiries`, a Vol/Chain tab toggle, and a `ChainTable` component. The backend chain fetch was just fixed to return a bounded, multi-expiry chain (ATM ±15%, near expiries). What's missing is a **trader-grade chain table**: today's `ChainTable` dumps all five greeks per side (23 columns, horizontal scroll) — the opposite of Sensibull's compact, OI/LTP-first layout.

This slice rewrites **one component** (`ChainTable.tsx`) into a Sensibull-style chain. The page shell, expiry selector, hooks, client, and `Contract` type are all unchanged.

### Decisions locked during brainstorming
- **Columns:** compact default set + a **Greeks toggle** (preserves our greeks depth one click away).
- **Visual cues (all four):** ITM shading, OI bars, ATM center + spot line, strike-count limiter.

## Goal

Render the option chain as a calls | strike | puts grid with a moneyness staircase, an ATM-centered focused window, and a one-click Greeks view — matching the Sensibull chain experience while keeping our model-priced greeks/IV available.

## Component

All changes live in `apps/web/src/features/markets/ChainTable.tsx` (props unchanged: `{ contracts: Contract[]; spot: number }`). It manages its own view state; `Markets.tsx` is not touched.

### Layout
Calls on the left, strike in the center, puts on the right, **mirrored** so bid/ask sit next to the strike. Strikes ascending top→bottom.

```
        CALLS                                 PUTS
 OI    Vol   IV     LTP   Bid  Ask │STRIKE│ Bid  Ask  LTP    IV     Vol   OI
 745   ...   ...    ...   ...  ... │ 745  │ ...                              ← call ITM (strike < spot)
 750   ...                         │ 750  │ ...
──────────────────────  spot 754.24  ────────────────────────────────────────
 755   ...                         │ 755  │ ...                              ← put ITM (strike > spot)
 760   ...                         │ 760  │ ...
```

### View state (component-local `useState`)
- `mode: 'default' | 'greeks'` — column set.
- `window: 10 | 20 | 'all'` — strikes shown each side of ATM (default `10`).

### Column sets
- **default:** `OI · Vol · IV · LTP · Bid · Ask` (per side).
- **greeks:** `Δ · Γ · Θ · Vega` (per side), from `c.ours`.
The puts side mirrors the calls side (reversed column order) so both read outward from the strike. A `Greeks` / `Prices` toggle button switches `mode`.

### Visual cues
1. **ITM shading.** For each row: the **call** side is tinted (`bg-pos/8`) when `strike < spot`; the **put** side is tinted (`bg-neg/8`) when `strike > spot`. (A call is ITM below spot; a put is ITM above spot.)
2. **OI bars.** Each OI cell has an inline horizontal bar (absolutely positioned within the cell, `position: relative` cell) whose width is `open_interest / maxOI`, where `maxOI` is the max OI across all rows of the current expiry. Calls bar tinted `bg-pos/20`, puts `bg-neg/20`.
3. **ATM center + spot line.** A full-width divider row (`<tr>` with one `colSpan` cell) reading `spot {spot}` is inserted between the last strike `< spot` and the first strike `>= spot`. On mount / when rows change, the ATM row (`nearestStrike` to spot) is scrolled to center via a `ref` + `scrollIntoView({ block: 'center' })` inside a `max-h-[70vh] overflow-y-auto` body container. **jsdom note:** `scrollIntoView` is not implemented in jsdom, so the call MUST be optional-chained (`ref.current?.scrollIntoView?.({ block: 'center' })`) or the tests throw.
4. **Strike-count limiter.** A `10 / 20 / All` segmented control. Default (`10`) shows the 10 strikes above and below the ATM strike (≤ 21 rows). `All` shows every strike returned (the ±15% band). The window is computed by ATM index ± N over the sorted rows.

### Reused helpers (already in the file)
`pivot(contracts)` → rows by strike; `nearestStrike(rows, spot)` → ATM strike. Formatters `pct`, `g3`, `px`. New small helpers: `oiBarPct`, the spot-divider insertion, and the per-mode column renderers.

## Data flow
Unchanged. `Markets.tsx` → `useChain(ticker, expiry)` → `getChain` → `ChainTable contracts spot`. The component derives everything (pivot, ATM, window, bars) from those two props. No new API, hook, or type.

## Error / empty states
- Empty contracts → existing `chain-empty` message (kept).
- A strike with only a call or only a put → that side renders em-dashes (existing `sideCells` empty behavior, adapted to the new column sets).
- `maxOI === 0` (no OI data) → bars render at 0 width (no divide-by-zero; guard `maxOI || 1`).

## Testing (`ChainTable.test.tsx`, updated)
Keep the existing testids (`chain-table`, `chain-row-{strike}`, `chain-empty`, `data-atm`). Add:
- **Split + pivot:** a call+put at one strike share a row; IV of both shown (existing test, retained).
- **ATM:** the nearest-to-spot strike row has `data-atm="true"` (existing, retained).
- **ITM shading:** a row with `strike < spot` has the call-side ITM class; a row with `strike > spot` has the put-side ITM class (assert via a `data-itm` attribute on the side cells, e.g. `data-testid="call-cell-{strike}"` carrying `data-itm`).
- **Greeks toggle:** clicking the toggle (`data-testid="chain-greeks-toggle"`) swaps columns — `Δ` header appears and the `OI` header is gone (and back on toggle off).
- **Strike-count limiter:** with > 21 strikes, the default render shows ≤ 21 rows; clicking `All` (`data-testid="chain-window-all"`) shows all.
- **Spot line:** a `data-testid="chain-spot-line"` row renders containing the spot value.
- **OI bar:** an OI bar element (`data-testid="oi-bar-{strike}"`) is present.

## Out of scope (deferred)
- OI-change / LTP-change columns — our snapshot is a single point-in-time, no intraday delta.
- Max-pain, PCR, OI-buildup overlays — a separate analytics feature.
- Trading/order entry from the chain.
- A configurable strike band on the backend (currently hardcoded ATM ±15%) — the client limiter covers the UX need.

## Build sequence (for the plan)
1. Rewrite `ChainTable.tsx`: view state, column sets + toggle, mirrored layout, ITM shading, OI bars, spot line + ATM auto-center, strike-count limiter.
2. Update `ChainTable.test.tsx` for the new structure + the added assertions.
3. Gate: web typecheck / lint / `test:run` / build green; `Markets.tsx` untouched and its tests still pass.
