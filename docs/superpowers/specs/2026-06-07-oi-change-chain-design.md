# Change in OI (ΔOI) on the Option Chain — Design Spec

**Date:** 2026-06-07
**Slice:** Slice 1 of 2 — per-strike ΔOI column on the chain (`/app/markets` → Chain tab)
**Status:** Approved design, ready for implementation plan

## Context

The Markets page (`apps/web/src/pages/Markets.tsx`) renders an option chain via
`ChainTable.tsx`, fed by `useChain(ticker, expiry)` → `getChain` →
`GET /v1/market/chain`. The chain shows **absolute** open interest per strike (with an
inline OI magnitude bar), a Prices/Greeks toggle, and a ±strike window.

The prior chain-UX spec ([2026-06-05-sensibull-chain-ux-design.md](2026-06-05-sensibull-chain-ux-design.md))
explicitly deferred **OI-change / LTP-change columns** ("our snapshot is a single
point-in-time, no intraday delta"). This slice builds the OI-change part, Sensibull-style:
a **Chg OI** column with a **Day / 1h / 3h / 4h** time-window toggle, per expiry (DTE).

### How OI data actually flows (grounding)
- `MarketService._computed_chain` fetches the **current** chain from the provider, caches it
  in Redis (`mdq:chain:v1:...`), and `persist_chain` **upserts the current snapshot** into the
  shared `options_chain_snapshots` table. The table's PK includes `ts`, so it retains history.
- Therefore: **current OI** = the cached/computed chain payload; **baseline OI** = an *earlier*
  row in `options_chain_snapshots`. ΔOI = current − baseline.

### Data reality (drives the baseline rule)
Snapshot cadence is sparse and irregular (observed locally): AAPL ~5 snapshots over ~8 days,
SPY ~4 over ~1 day. Exact hourly deltas are therefore **not** available from real data yet, so:

> **Baseline rule (locked in brainstorming): nearest-snapshot with an honest label.**
> The baseline for window *W* is the snapshot whose `ts` is closest to (`as_of − W`) **and**
> strictly earlier than `as_of`. The UI always shows a number when a baseline exists, but labels
> the **actual** elapsed time (e.g. "Δ vs 10:27 (~3h7m ago)") so it is never misleading. If no
> earlier snapshot exists for a window, ΔOI renders "—" and the note says so. Making ingestion
> hourly (so the deltas are exact) is **Slice 2 / out of scope** here.

## Goal

Show, per strike and side, the change in open interest over a chosen recent window
(Day/1h/3h/4h), for the selected expiry (DTE), reusing the existing chain endpoint and
`ChainTable` — with honest baseline labelling given sparse snapshots.

## Scope decisions (locked in brainstorming)
- **Both** ΔOI column **and** a dedicated OI-analysis view were requested → decomposed into two
  slices. **This spec is Slice 1 (the ΔOI column).** Slice 2 (OI-analysis view: aggregate
  call/put OI bars, PCR, max-pain) gets its own spec.
- **All four windows computed at once** in the backend response (one snapshot scan, cheap) so the
  frontend toggle is instant and ChainTable keeps its toggle local — consistent with the existing
  Prices/Greeks and ±strike toggles. (Rejected: a `?oi_window=` query param that refetches per
  toggle.)
- **Show DTE** next to the expiry (the "with DTE" ask).
- **No new entitlement** — rides the existing Pro gate (`require_vol_surface`).

## Backend

### New module: `apps/api/saalr_api/market/oi_change.py`
Pure, independently testable logic:

- `WINDOWS: dict[str, timedelta | None]` — `{"day": None, "1h": 1h, "3h": 3h, "4h": 4h}`
  (`day` is special-cased: start-of-day(as_of)).
- `pick_baseline_ts(snapshot_ts: list[datetime], as_of: datetime, window: str) -> datetime | None`
  - For `1h/3h/4h`: among `ts < as_of`, the one closest to `as_of − W`; `None` if none earlier.
  - For `day`: the **earliest** `ts` with `start_of_day(as_of) ≤ ts < as_of`; `None` if none.
- `elapsed_label(as_of, baseline_ts) -> str` — compact "~3h7m" / "~57m" style.

### New repo query (in `market` data access, e.g. `oi_repo.py` or extend `snapshots.py`)
- `load_oi_history(session, underlying, market) -> {ts: {(expiry, strike, type): open_interest}}`
  over `options_chain_snapshots`. (Bounded: one underlying; the table is small/shared.)
  Alternatively return distinct `ts` list + a `{(ts, key): oi}` map; implementation detail for the plan.

### `MarketService.chain(...)` enrichment
After building the (cached) chain payload and filtering by expiry:
1. Load OI history for the underlying; `as_of = datetime.fromisoformat(payload["as_of"])`.
2. For each window, `pick_baseline_ts(...)` → baseline ts (or None).
3. Per contract key `(expiry, strike, type)`, `oi_change[window] = current_oi − baseline_oi`
   when both the baseline ts exists **and** that key existed in the baseline snapshot; else `None`.
4. Response additions:
   - **per contract:** `"oi_change": {"day": int|null, "1h": int|null, "3h": int|null, "4h": int|null}`
   - **chain-level:** `"oi_baselines": {"day": {"ts": iso, "elapsed_label": "~5h"}|null, "1h": …, "3h": …, "4h": …}`

ΔOI enrichment is computed from snapshots in Postgres and merged onto the **cached** chain — it does
not recompute greeks, so it stays cheap. (If a per-window baseline cache is wanted later it can key on
`mdq:oichg:v1:{market}:{ticker}` — not required for this slice.)

## Frontend

### Types (`apps/web/src/lib/market.ts`)
- `Contract` gains `oi_change: { day: number | null; '1h': number | null; '3h': number | null; '4h': number | null }`.
- `Chain` gains `oi_baselines: Record<OiWindow, { ts: string; elapsed_label: string } | null>`.
- `export type OiWindow = 'day' | '1h' | '3h' | '4h'`.

### `ChainTable.tsx`
- New local state `oiWin: OiWindow` (default `'day'`), plus a segmented toggle
  `[ Day | 1h | 3h | 4h ]` rendered alongside the existing controls
  (`data-testid="oi-window-{win}"`).
- A **Chg OI** column added to `DEFAULT_COLS` (first column, mirrored like the rest):
  value = `contract.oi_change[oiWin]`; render `+12.4k` (green, `text-pos`) / `-3.1k`
  (red, `text-neg`) / `—` when null. Reuse the `kfmt` formatter with a sign.
  (Greeks mode unchanged — Chg OI is a default-mode column.)
- A baseline **note** line under the controls (`data-testid="oi-baseline-note"`): from
  `chain.oi_baselines[oiWin]` → "Chg OI vs {HH:MM} ({elapsed_label} ago)", or
  "No earlier snapshot in range." when null.
- `Markets.tsx`: show DTE next to the expiry option/label (e.g. `20 Jun · 13d`), computed from
  expiry − today. (The chain data flow / props are otherwise unchanged.)

### Data flow
Unchanged shape: `Markets.tsx` → `useChain(ticker, expiry)` → `getChain` →
`ChainTable contracts spot oiBaselines`. The new `oi_baselines` is passed as a prop (or read
from the chain object already threaded). The window toggle is purely local; no refetch.

## Error / empty states
- No snapshots / only the current one → every `oi_change[*]` is `null`, every `oi_baselines[*]`
  is `null`; the column shows "—" and the note explains. (No crash, no divide-by-zero.)
- A strike present now but absent in the baseline snapshot → that contract's ΔOI is `null` ("—").
- Empty contracts → existing `chain-empty` message (kept).

## Testing

### Backend
- `oi_change` unit tests: `pick_baseline_ts` for exact match, approximate (nearest earlier),
  none-earlier (`None`), and `day` (earliest same-day). `elapsed_label` formatting.
- Integration test (`tests/integration/test_market_oi_change.py`): seed two snapshots (earlier +
  current) for one underlying/expiry; assert per-contract `oi_change` values and the
  `oi_baselines` ts for at least one window; assert a missing-baseline window yields `null`.

### Frontend (`ChainTable.test.tsx`, extended)
- Chg OI column renders the `oi_change.day` value by default; toggling to `1h`
  (`data-testid="oi-window-1h"`) switches the displayed values.
- Positive value carries the up/green class, negative the down/red class.
- `null` ΔOI renders "—"; with all baselines null, the note shows the "no earlier snapshot" copy.
- Existing chain tests (pivot, ATM, ITM shading, Greeks toggle, strike limiter, spot line, OI bar)
  remain green.
- `Markets.tsx` test: the expiry label includes the DTE suffix.

## Out of scope (deferred)
- **Slice 2:** dedicated OI-analysis view — aggregate call/put OI & ΔOI bars across strikes, PCR,
  max-pain, OI build-up classification.
- Increasing snapshot ingestion cadence so 1h/3h/4h deltas are exact (this slice approximates to
  the nearest earlier snapshot and labels it honestly).
- LTP-change / volume-change columns.
- Per-window server-side caching (current enrichment is already cheap).

## Build sequence (for the plan)
1. Backend `oi_change.py` (pure logic) + tests.
2. Repo query over `options_chain_snapshots` + `MarketService.chain` enrichment + integration test.
3. Frontend types, ChainTable Chg OI column + window toggle + baseline note + tests.
4. `Markets.tsx` DTE label + test.
5. Gate: web typecheck / lint / `test:run` / build green; API integration tests green; existing
   Markets/ChainTable tests still pass.
