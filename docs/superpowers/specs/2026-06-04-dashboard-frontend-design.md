# Dashboard frontend (AN-4) — design

**Status:** approved design, 2026-06-04. Slice **AN-4** of the analytics-frontends band —
the **last** one (AN-1 Markets, AN-2 Models, AN-3 Portfolio shipped).

## Goal

Replace the `/app` index `PlaceholderPage` with an aggregating landing surface: an ungated
**portfolio overview**, a **watchlist** auto-derived from your held position symbols showing
vol-forecast + sentiment (`ml_forecast`-gated), and a **market snapshot** for your primary
symbol (`vol_surface`-gated). Gated widgets degrade to compact inline upgrade nudges — the
dashboard itself never hard-gates. No new API client: it reuses the AN-1/AN-2/AN-3 clients and
hooks (DRY).

## Backends consumed (all already shipped; bearer-authed)

- **OMS (ungated)** via `lib/oms.ts` + `features/portfolio/hooks.ts`: `listBrokerAccounts()` →
  `{ broker_accounts: BrokerAccount[] }`, `listPositions(accountId)` → `{ positions: Position[] }`
  (`Position.symbol`, `qty`, `avg_entry_price` string, `option_type|strike|expiry` nullable),
  `listOrders(cursor?)` → `{ orders: Order[], next_cursor }` (`Order.status`, `reject_reason_code`,
  `created_at`).
- **Models (`ml_forecast` → 402)** via `lib/models.ts`: `getVolForecast(ticker, horizon)` →
  `{ primary_model, primary_forecast: number[], … }`, `getSentiment(ticker)` →
  `{ score, label, confident, n_headlines, has_data, … }`.
- **Markets (`vol_surface` → 402)** via `lib/market.ts` + `features/markets/hooks.ts`:
  `getIvSurface(ticker)` → `IvSurface` (`spot`, `expiries: [{ expiry, strikes: [{ strike, calls, puts }] }]`).

Entitlements live on `me.entitlements` (`vol_surface`, `ml_forecast` — both Pro+; booleans).
`me = { user: { email }, tenant, tier, entitlements }`.

## Decisions (locked)

- **Layout = portfolio + position-derived watchlist.** The portfolio overview (ungated) is the
  spine; the watchlist is derived from the symbols you actually hold, each row enriched with
  vol-forecast % + a sentiment chip. This ties AN-1/AN-2/AN-3 together with no new backend.
- **Gating = inline per-card nudge.** A free user keeps the full portfolio overview; the
  watchlist and market-snapshot cards each render a compact `UpgradeHint` (→ `/billing?plan=pro`)
  in place of their data. Entitlements are **pre-checked** so a free user fetches nothing gated
  (no wasted 402).
- **Dynamic watchlist fan-out uses `useQueries`.** The symbol list is dynamic, so the page can't
  call `useQuery` in a loop (Rules of Hooks). `useQueries` fetches the per-symbol forecasts and
  sentiments at page level; the row component stays pure.
- **Watchlist is capped at 5 symbols** and shows vol-forecast + sentiment only (no live spot per
  row — that would add the `vol_surface` gate and the full-chain latency to every row). The live
  spot lives in the single MarketSnapshot card.
- **Empty positions** → the watchlist shows a prompt and a manual ticker-add input (client-side
  `extraSymbols` state), so a fresh paper account still has a usable dashboard.

## Components / files

- **`src/features/dashboard/UpgradeHint.tsx`** *(pure)* — props `{ feature: string; plan?: 'pro' | 'premium' }`.
  A compact bordered card: a `// Pro` kicker, a one-line `feature` message, and a
  `<Link to="/billing?plan={plan}">Upgrade</Link>`. `data-testid="upgrade-hint"`.
- **`src/features/dashboard/StatStrip.tsx`** *(pure)* — props `{ email: string; tier: string;
  accounts: number; positions: number; workingOrders: number }`. A greeting line ("Welcome back,
  {email}") + three stat tiles (`data-testid` `stat-accounts`, `stat-positions`, `stat-orders`).
- **`src/features/dashboard/PortfolioOverview.tsx`** *(pure)* — props `{ orders: Order[] }`
  (already sliced to ≤5 by the page). A small table: symbol, side, qty, status (color: filled→pos,
  rejected/cancelled→neg, else warn), time. A "View portfolio →" `<Link to="/portfolio">`. Empty
  → `data-testid="overview-empty"` "No orders yet."
- **`src/features/dashboard/WatchlistTable.tsx`** *(pure)* — props `{ rows: WatchRow[]; entitled:
  boolean; onAddSymbol: (s: string) => void }` where `WatchRow = { symbol: string; forecastPct:
  number | null; sentimentLabel: 'bearish' | 'neutral' | 'bullish' | null; loading: boolean }`.
  - `entitled === false` → render `<UpgradeHint feature="Forecasts & sentiment for your holdings" />`.
  - `rows.length === 0` (entitled) → `data-testid="watchlist-empty"` prompt + a ticker input
    (`data-testid="watchlist-add-input"`) + Add button (`watchlist-add-btn`) calling `onAddSymbol`.
  - otherwise a table: symbol, vol % (or "—" / "…" while loading), a sentiment chip
    (bearish→neg / neutral→warn / bullish→pos, or "—"). Row testid `watch-{symbol}`. The add
    input is also shown beneath a non-empty table so symbols can be appended.
- **`src/features/dashboard/MarketSnapshot.tsx`** *(pure)* — props `{ symbol: string; surface:
  IvSurface | null; entitled: boolean; loading: boolean }`.
  - `entitled === false` → `<UpgradeHint feature="Live IV snapshot for {symbol}" />`.
  - no `symbol` → `data-testid="snapshot-empty"` "Hold a position to see its IV snapshot."
  - `surface` present → spot, nearest expiry, and ATM IV (the strike nearest `spot`, averaging
    call+put IV ×100). `data-testid="snapshot"`. `loading` with no surface → a skeleton.
- **`src/pages/Dashboard.tsx`** — owns all hooks. A `// Dashboard` kicker + `h2`.
  - `me` → `volEntitled = me?.entitlements?.vol_surface === true`,
    `mlEntitled = me?.entitlements?.ml_forecast === true`.
  - `useBrokerAccounts()`; `firstAccount = accounts[0]`; `usePositions(firstAccount?.broker_account_id ?? '')`;
    `useOrders()` (first page only — `data?.pages[0]?.orders ?? []`).
  - `extraSymbols` state; `symbols = unique([...positions.map(p => p.symbol), ...extraSymbols]).slice(0, 5)`.
  - `forecasts = useQueries({ queries: symbols.map(s => ({ queryKey: ['vol-forecast', s, 10],
    queryFn: () => getVolForecast(s, 10), enabled: mlEntitled && !!s, retry: false })) })`;
    `sentiments = useQueries({ queries: symbols.map(s => ({ queryKey: ['sentiment', s],
    queryFn: () => getSentiment(s), enabled: mlEntitled && !!s, retry: false })) })`.
  - Build `WatchRow[]` from the two result arrays (`forecastPct = mean(primary_forecast)` rounded;
    `sentimentLabel = has_data ? label : null`; `loading = forecast.isLoading || sentiment.isLoading`).
  - `surfaceQ = useIvSurface(volEntitled ? (symbols[0] ?? '') : '')`.
  - Layout: `<StatStrip>` → a 2-col grid (`<PortfolioOverview>` | `<MarketSnapshot>`) →
    `<WatchlistTable>` full width.
- **`src/app/Router.tsx`** — replace `<Route index element={<PlaceholderPage title="Dashboard" />} />`
  with `<Route index element={<Dashboard />} />` + import. **Remove the now-unused `PlaceholderPage`
  import** (the index route is its last consumer). If `grep` shows nothing else references
  `PlaceholderPage` (including tests), delete `src/components/PlaceholderPage.tsx`; otherwise leave
  the file and only drop the Router import.

## Data flow

Accounts load → first account → positions → distinct held symbols (∪ manual adds, cap 5). The
watchlist `useQueries` (enabled only when `ml_forecast`) fetch per-symbol forecast + sentiment;
the page reduces each pair to a `WatchRow`. The MarketSnapshot fetches the IV surface for the
first symbol (enabled only when `vol_surface`). The portfolio overview reads the first page of
orders. Adding a symbol pushes to `extraSymbols`, growing the watchlist (and re-pointing the
snapshot if it was empty).

## Error handling

- Not entitled (pre-check) → the per-card `UpgradeHint`; nothing gated is fetched.
- A watchlist forecast/sentiment query error → that cell shows "—" (the row still renders from
  whatever resolved); no card-wide error.
- `sentiment.has_data === false` → the chip shows "—" (no coverage), not an error.
- IV-surface error (entitled) → MarketSnapshot shows its empty/"unavailable" state, not a crash.
- Portfolio/OMS errors → counts fall back to 0 and the overview shows its empty state.

## Testing (vitest + @testing-library/react; mock the lib modules; `MemoryRouter` for `<Link>`)

- `UpgradeHint.test.tsx` — renders the feature text and a `/billing?plan=…` link.
- `StatStrip.test.tsx` — shows the three counts and the email.
- `PortfolioOverview.test.tsx` — renders recent orders with status; empty state with no orders.
- `WatchlistTable.test.tsx` — entitled rows render symbol + vol % + sentiment chip; `entitled:false`
  → `upgrade-hint`; empty rows → add prompt, and `onAddSymbol` fires from the input+button.
- `MarketSnapshot.test.tsx` — surface → spot + ATM IV; `entitled:false` → `upgrade-hint`; no symbol
  → `snapshot-empty`.
- `Dashboard.test.tsx` — (auth mocked via the `let mockMe` + `vi.mock('../auth/AuthContext', …)`
  pattern) free user (`ml_forecast:false, vol_surface:false`) → portfolio overview renders and the
  watchlist + snapshot show `upgrade-hint`, with `getVolForecast`/`getIvSurface` **not** called;
  entitled user with one position (mock `listBrokerAccounts`/`listPositions`/`listOrders` +
  `getVolForecast`/`getSentiment`) → a `watch-{symbol}` row renders with the mocked vol % and label.
- Gate: `npm run typecheck && npm run lint && npm run test:run` (all green); `npm run build` still
  prerenders 17 docs (the `/app` index is client-only).

## Out of scope (later)

Persisted/server-side watchlist (manual adds are client-only, lost on reload); live unrealized
P&L (positions carry only avg entry — no live mark); a batch quote/forecast endpoint to replace
the per-symbol `useQueries` fan-out; charts on the dashboard (deep-link to the full surfaces
instead); multi-account aggregation (uses the first broker account only).
