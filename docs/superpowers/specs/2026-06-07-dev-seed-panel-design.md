# Dev Seed Panel — automate market-data injection through the UI — Design Spec

**Date:** 2026-06-07
**Slice:** Dev-only in-app panel + backend endpoints to inject real Massive market data on demand
**Status:** Approved design, ready for implementation plan

## Context

Local/demo environments keep hitting thin market data: price forecasts need 250+ daily
`bars`, backtests need bars, and the upcoming ΔOI column
([2026-06-07-oi-change-chain-design.md](2026-06-07-oi-change-chain-design.md)) needs multiple
timestamped `options_chain_snapshots`. Today data lands only when:
- the chain endpoint misses its **6h Redis cache** (`MarketService._computed_chain` →
  `persist_chain`), so repeatedly loading a ticker in the UI does **not** create new snapshots; and
- the once-a-day ingest cron (`apps/ingest-worker`, `INGEST_CRON=30 21 * * *`) runs.

We want an **elegant, dev-only way to inject data through the UI**: a panel that triggers real
**Massive** fetches on demand and accumulates intraday chain snapshots.

### Decisions locked in brainstorming
- **Mechanism:** a dev-only in-app **Seed panel** that calls backend seed endpoints (not headless
  UI automation, not a CLI-only seeder).
- **Data source:** **real Massive provider** (not synthetic, not hybrid). Requires
  `MASSIVE_API_KEY`; the panel surfaces a clear error when it's absent.
- **What to seed:** **both** historical bars backfill **and** a cache-bypassing chain snapshot.
- **Trigger:** one-shot buttons **plus** an optional browser-driven repeat loop
  ("every N min × K times").

### Honest limitation (real data)
Real captures minutes apart reflect only the OI moves the live market actually made, so rapid
repeats yield near-zero ΔOI; intraday ΔOI accumulates as real time passes. This is acceptable and
matches the ΔOI spec's "nearest-snapshot, honestly labelled" baseline rule.

## Existing building blocks (grounding)
- `saalr_core.marketdata.massive.MassiveProvider.get_option_chain` — current option chain.
- `saalr_core.marketdata.aggregates.MassiveAggregatesProvider.get_daily_bars(symbol, start, end, market)`
  — historical daily bars.
- `apps/api/.../market/snapshots.py:persist_chain` — upserts an `options_chain_snapshots` row.
- `apps/api/.../market/service.py:MarketService._computed_chain` — fetch → compute greeks →
  `persist_chain` → cache 6h (early-returns on cache hit).
- `apps/ingest-worker` `service.backfill_symbol` + `repo` (bars upsert) — backfill logic that today
  lives only in that app (the API package can't import it).

## Architecture & safety (dev-only, defense in depth)
- **Backend:** `/v1/dev/seed/*` endpoints are mounted/served only when
  `settings.auth_provider == 'dev'`; otherwise they return `404`. They still require a logged-in
  principal (`get_principal`).
- **Frontend:** the `/app/dev` route and its sidebar link render only when `import.meta.env.DEV`
  (true under `vite dev`, false in a production build).

These are independent: even if a dev build were served, the backend gate still blocks seeding
against a non-dev (`clerk`) deployment.

## Backend

### Shared backfill helper — `packages/core/saalr_core/marketdata/backfill.py` (new)
Extract the small, currently-ingest-worker-only logic into `saalr-core` so both the API dev
endpoint and (later) the ingest-worker share one copy:
- `async def upsert_bars(session, rows: list[BarRow]) -> int` — INSERT … ON CONFLICT upsert into
  `bars`, returns count.
- `async def backfill_symbol(session, provider, symbol, market, start, end) -> int` —
  `provider.get_daily_bars(...)` → `upsert_bars(...)`.
(Refactoring `apps/ingest-worker` to import this is a **follow-up**, not part of this slice.)

### Cache-bypassing capture — `MarketService`
Refactor `_computed_chain` to split the compute+persist body from the cache wrapper, then add:
- `async def capture_snapshot(self, session, ticker, market) -> dict` — runs the compute body
  **without** the Redis early-return: fetch via `MassiveProvider`, `_compute`, `persist_chain`
  (new timestamped row), and `redis.set` to refresh the cache. Returns the chain payload.
The normal cached `chain()` / `iv_surface()` paths are unchanged.

### Provider wiring — `apps/api/saalr_api/main.py`
Construct `MassiveAggregatesProvider(settings.massive_api_key)` into
`app.state.aggregates_provider` (chains already use `app.state.market_provider`).

### Endpoints — `apps/api/saalr_api/dev/router.py` (new)
Mounted only in dev. Both accept JSON bodies and require a principal.
- `POST /v1/dev/seed/bars` body `{ "ticker": str, "days": int = 400 }`
  → `backfill_symbol(session, app.state.aggregates_provider, TICKER, "US", today-days, today)`
  → `{ "symbol", "rows_upserted", "first", "last" }`.
- `POST /v1/dev/seed/chain` body `{ "ticker": str }`
  → `MarketService.capture_snapshot(session, TICKER, "US")`
  → `{ "ticker", "as_of", "contracts", "total_snapshots" }` (`total_snapshots` = count of distinct
  `ts` for that underlying, so the UI can show history growing).
Validation mirrors `market/router.py:_validate` (alpha ticker, market `US`). `ProviderError` → `503`
with `{error:{code:"MARKET_DATA_PROVIDER_UNAVAILABLE", message}}`.

## Frontend
- `apps/web/src/lib/dev.ts` — `seedBars(ticker, days)` and `seedChain(ticker)` POST helpers (reuse
  `BASE` + `authHeaders`, same error mapping as `lib/market.ts`).
- `apps/web/src/pages/DevSeed.tsx` — the panel:
  - Inputs: **ticker**, **days** (default 400).
  - Buttons: **[Backfill bars]**, **[Capture snapshot]** — each shows its JSON result and appends a
    line to a scrolling **log** (`data-testid="seed-log"`).
  - **Repeat loop:** inputs `every [N] min`, `× [K] times`, **[Start]/[Stop]**. Uses a browser
    `setInterval`; each tick calls `seedChain(ticker)`, appends the result (or error) to the log,
    increments a counter, and auto-stops after K or on Stop. Cleared on unmount.
- Routing/nav: add `/app/dev` to `Router.tsx` and a "Dev" entry in `nav.ts`/Sidebar **guarded by
  `import.meta.env.DEV`** (no breadcrumb/label changes needed beyond the new route's label).

## Error / edge handling
- Missing `MASSIVE_API_KEY` → provider raises `ProviderError` → `503`; the panel shows
  "no Massive API key configured" so the cause is obvious.
- Unknown ticker → `404` surfaced in the log.
- Repeat loop: a failing iteration is logged and the loop **continues**; **Stop** always halts it;
  navigating away clears the interval.
- Non-dev backend → `404` for all `/v1/dev/seed/*` (asserted by test).

## Testing
### Backend
- Unit: `upsert_bars` / `backfill_symbol` with a fake aggregates provider (asserts rows upserted,
  idempotent on conflict). `capture_snapshot` with fake redis+provider — asserts it does **not**
  early-return on a primed cache, calls `persist_chain`, and refreshes the cache.
- Integration (`tests/integration/test_dev_seed.py`): with `auth_provider != 'dev'` the endpoints
  return `404`; in dev, a stubbed provider yields the expected counts and a snapshot row appears.
### Frontend (`DevSeed.test.tsx`)
- Clicking **Backfill bars** / **Capture snapshot** calls the mocked client and logs the result.
- Repeat loop with fake timers fires K times then auto-stops; **Stop** halts early.
- Panel/route absent when `import.meta.env.DEV` is false (guard test).

## Out of scope (deferred)
- Production use (dev-gated by design).
- Synthetic data generation (this slice is real-Massive only).
- Changing the ingest cron / a server-side scheduler (the browser repeat loop covers the need).
- Refactoring `apps/ingest-worker` onto the shared `backfill` helper (follow-up).
- Seeding user-scoped data (strategies, backtests, paper trades).

## Build sequence (for the plan)
1. `saalr_core.marketdata.backfill` (helper) + unit tests.
2. `MarketService.capture_snapshot` (cache-bypass refactor) + unit test; wire
   `aggregates_provider` in `main.py`.
3. `apps/api/saalr_api/dev/router.py` + dev-gated mounting + integration tests.
4. Frontend `lib/dev.ts`, `DevSeed.tsx`, route + DEV-guarded nav + tests.
5. Gate: web typecheck / lint / `test:run` / build green; API tests green; non-dev returns 404.
