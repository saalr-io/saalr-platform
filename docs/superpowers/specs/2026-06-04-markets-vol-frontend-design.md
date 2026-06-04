# Markets & Vol frontend (AN-1) — design

**Status:** approved design, 2026-06-04. Slice **AN-1** of the analytics-frontends band.

## Band context

The authed `/app` SPA still has four `PlaceholderPage` routes. They decompose into four
independent slices, each its own spec→plan→build:
- **AN-1 Markets & Vol** (`/app/markets`) — this slice.
- **AN-2 Models** (`/app/models`) — GARCH vol-forecast + sentiment + Monte-Carlo POP (`ml_forecast`).
- **AN-3 Portfolio** (`/app/portfolio`) — OMS: broker accounts, positions, place/cancel orders.
- **AN-4 Dashboard** (`/app`) — aggregates the above; built last (reuses AN-1/AN-3 clients).

## Goal

Replace the `Markets & Vol` placeholder with a ticker-driven options-analytics terminal: a live
options **chain** table and an **IV-surface** visualization, over the already-built
`/v1/market/{iv-surface,chain}` endpoints. `vol_surface`-gated (Pro+); free users get an upgrade
nudge to `/app/billing?plan=pro`.

## Backends consumed (bearer-authed; base `import.meta.env.VITE_API_BASE_URL ?? '/api'`)

- `GET /v1/market/iv-surface?ticker=&market=US` → `{ ticker, market, as_of, spot,
  expiries: [{ expiry, strikes: [{ strike, calls: Greeks, puts: Greeks }] }], data_provider, model,
  risk_free_source, freshness_ms }` where `Greeks = { price, delta, gamma, theta, vega, rho, iv }`.
- `GET /v1/market/chain?ticker=&market=US&expiry=` → `{ ticker, market, as_of, spot, model,
  risk_free_source, contracts: [{ expiry, strike, type:'CALL'|'PUT', bid, ask, last, volume,
  open_interest, ours: Greeks, vendor: { iv, delta, gamma, theta, vega } }] }`. The `expiry` param
  filters to one expiry.
- Both gate on `vol_surface` → **402 `ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO`**. Other errors:
  404 `RESOURCE_NOT_FOUND` (bad ticker), 400 `VALIDATION_INVALID_PARAMETER` (bad market),
  503 `MARKET_DATA_PROVIDER_UNAVAILABLE`.
- Entitlement flag on `me`: `me.entitlements.vol_surface` (boolean).

## Decisions (locked)

- **IV surface = smile + term-structure curves** (two custom SVG line charts), not a heatmap.
- **Chain = pivoted layout** (calls | strike | puts) for one selected expiry.
- **iv-surface is the backbone** — one fetch per ticker feeds the expiry dropdown + both curves; the
  **chain is fetched per selected expiry** (`?expiry=`) to avoid the known full-chain pagination
  latency.
- **Pre-check `me.entitlements.vol_surface`** to show the gate without a wasted 402 (still handle a
  402 defensively).
- **No default ticker** — empty input with a placeholder (`e.g. SPY`); load on submit. No auto-fetch
  on mount, no polling (server caches 6h); a Refresh button refetches.

## Components / files

- **`src/lib/market.ts`** — typed client over the existing `request()` wrapper (401→logout,
  402→`EntitlementError`, else `Error(code)`):
  - `getIvSurface(ticker: string): Promise<IvSurface>`
  - `getChain(ticker: string, expiry: string): Promise<Chain>`
  - Exported types: `Greeks`, `IvSurface` (`{ spot, as_of, data_provider, freshness_ms, expiries:
    IvExpiry[] }`, `IvExpiry = { expiry, strikes: { strike, calls: Greeks, puts: Greeks }[] }`),
    `Chain` (`{ spot, as_of, model, contracts: Contract[] }`,
    `Contract = { expiry, strike, type, bid, ask, last, volume, open_interest, ours: Greeks,
    vendor: { iv, delta, gamma, theta, vega } }`).
- **`src/features/markets/hooks.ts`** — `useIvSurface(ticker)` (query key `['iv-surface', ticker]`,
  `enabled: !!ticker`), `useChain(ticker, expiry)` (key `['chain', ticker, expiry]`,
  `enabled: !!ticker && !!expiry`). `retry: false`.
- **`src/features/markets/ChainTable.tsx`** — props `{ contracts: Contract[], spot: number }`. Pivot
  the contracts by `strike`: each row = a strike with its CALL on the left and PUT on the right.
  Call columns: `delta, iv, bid, ask, last, vol, OI`; center `strike`; put columns mirrored
  (`OI, vol, last, ask, bid, iv, delta`). The strike nearest `spot` (ATM) is highlighted (accent
  row). IV/Greeks formatted (iv as %, prices `.tnum`). Monospace, dense, terminal styling.
- **`src/features/markets/IvCurves.tsx`** — props `{ surface: IvSurface, expiry: string }`. Two
  custom SVG charts (a small local `scale` helper or inline min/max mapping; no chart lib):
  - **Smile** — for `expiry`, plot IV (y) vs strike (x); two series (calls, puts) or a blended mid;
    mark the ATM strike. Use `calls[i].iv` / `puts[i].iv` × 100 for %.
  - **Term structure** — ATM IV (the strike nearest `spot`, calls) per expiry, x = expiry index/date,
    y = ATM IV %. A single line across expiries.
  - Hover/labels optional; axis ticks minimal (min/max IV, strike range). SSR-irrelevant (client-only).
- **`src/features/markets/MarketsGate.tsx`** — the `vol_surface` upgrade panel (mirrors research
  `PremiumGate`): "Live chains & the IV surface are a Pro feature" + a `<Link to="/billing?plan=pro">
  Upgrade to Pro</Link>`.
- **`src/pages/Markets.tsx`** — composes it. If `useAuth().me?.entitlements?.vol_surface !== true` →
  render `<MarketsGate/>` (no fetch). Otherwise: a `// Markets & Vol` kicker + `h2`; a ticker
  `<input>` (uppercased, alpha) + Load + Refresh; once loaded, a header line (spot, as_of,
  `data_provider`, freshness) from the iv-surface; an expiry `<select>` (from the surface's
  `expiries`); and tabs **Chain** | **Vol Surface** rendering `ChainTable` (uses `useChain(ticker,
  expiry)`) / `IvCurves` (uses the already-loaded surface). A 402 from either query (defensive) also
  shows `MarketsGate`.
- **`src/app/Router.tsx`** — replace `<Route path="markets" element={<PlaceholderPage title="Markets & Vol" />} />`
  with `<Route path="markets" element={<Markets />} />` + import.

## Data flow

Enter ticker → `useIvSurface(ticker)` loads (expiries + IV data). Default the expiry `<select>` to
the nearest/first expiry. The **Vol Surface** tab renders `IvCurves` from the loaded surface; the
**Chain** tab triggers `useChain(ticker, selectedExpiry)` and renders `ChainTable`. Changing the
expiry updates both. Refresh invalidates both queries.

## Error handling

- Not entitled (`vol_surface` false) → `MarketsGate` (no fetch). A defensive 402 → also `MarketsGate`.
- 404 `RESOURCE_NOT_FOUND` → inline "No data for that ticker."
- 503 `MARKET_DATA_PROVIDER_UNAVAILABLE` → "Market data is temporarily unavailable — try again."
- Loading → skeleton/pulse; empty `contracts` for an expiry → "No chain for this expiry."

## Testing (vitest + @testing-library/react; mock `fetch` + `useAuth`; wrap in `MemoryRouter`)

- `src/lib/market.test.ts` — `getIvSurface`/`getChain` hit the right URLs (incl. the `expiry` param);
  a 402 throws `EntitlementError`.
- `ChainTable.test.tsx` — pivots a CALL+PUT at the same strike onto one row; highlights the ATM
  strike (nearest spot); renders IV/Greeks.
- `IvCurves.test.tsx` — renders the smile + term-structure SVGs (assert both chart testids + a
  plausible path/point count) from a small fixture surface.
- `Markets.test.tsx` — a free user (`vol_surface:false`) sees `MarketsGate` with the billing link and
  no fetch; an entitled user, after entering a ticker + Load, sees the header (spot) and the tabs.
- Gate: `npm run typecheck && npm run lint && npm run test:run` (all green); `npm run build` still
  prerenders 17 docs (this is a client-only `/app` route — no SSG impact).

## Out of scope (later)

Heatmap surface; vendor-vs-ours IV comparison toggle; per-contract trade actions (Portfolio, AN-3);
streaming/real-time; saving a watchlist; greeks beyond delta/theta/vega in the chain.
