# Portfolio frontend (AN-3) — design

**Status:** approved design, 2026-06-04. Slice **AN-3** of the analytics-frontends band
(AN-1 Markets & Vol shipped; AN-2 Models + AN-4 Dashboard remain).

## Goal

Replace the `Portfolio` placeholder with a paper-trading desk over the OMS endpoints: select/create a
paper broker account, see positions, place market/limit orders (equity + options), one-click close a
position, and view + cancel orders. No entitlement gate (auth only); paper trading works end-to-end.

## Backends consumed (bearer-authed; base `import.meta.env.VITE_API_BASE_URL ?? '/api'`)

- `GET /v1/broker-accounts` → `{ broker_accounts: BrokerAccount[] }`,
  `BrokerAccount = { broker_account_id, broker, account_label, is_paper, status }`.
- `POST /v1/broker-accounts` body `{ broker:'paper', account_label, is_paper:true }` → `BrokerAccount`.
  (400 `BROKER_NOT_SUPPORTED`, 422 `VALIDATION_MISSING_CREDENTIAL_REF` for alpaca — N/A here.)
- `GET /v1/positions?broker_account_id=` → `{ positions: Position[] }`,
  `Position = { broker_account_id, symbol, option_type:'CALL'|'PUT'|null, strike:string|null,
  expiry:string|null, qty:number, avg_entry_price:string }`.
- `POST /v1/orders` body `OrderCreate` (below) + optional `Idempotency-Key` header →
  `{ order_id, broker_order_id, status, submitted_at }`. Risk rejections → **422 `RISK_*`**
  (`RISK_INSUFFICIENT_BUYING_POWER`, `RISK_INVALID_QUANTITY`, `RISK_MISSING_LIMIT_PRICE`,
  `RISK_RATE_LIMIT_EXCEEDED`, `RISK_NO_MARKET_DATA`, …); also 404 `RESOURCE_NOT_FOUND`,
  409 `BROKER_ACCOUNT_INACTIVE`, 409 `ORDER_DUPLICATE_IN_FLIGHT`.
- `GET /v1/orders?limit=&cursor=` → `{ orders: Order[], next_cursor:string|null }`,
  `Order = { order_id, symbol, side, qty, order_type, status, broker_order_id:string|null,
  reject_reason_code:string|null, created_at }`. Status FSM: pending → submitted → filled | cancelled | rejected.
- `POST /v1/orders/{id}/cancel` → `{ order_id, broker_order_id, status, submitted_at }`.
  409 `ORDER_NOT_CANCELLABLE` (status not pending/submitted).

`OrderCreate = { broker_account_id, symbol, side:'BUY'|'SELL', qty:number, order_type:'market'|'limit',
option_type?:'CALL'|'PUT', strike?:number, expiry?:string (YYYY-MM-DD), limit_price?:number,
time_in_force?:'day' }`. (`stop`/`stop-limit`/`strategy_id` are out of scope for v1.)

## Decisions (locked)

- **Order ticket: equity + options, market + limit** (stop/stop-limit deferred). Limit shows a
  limit-price field; an "Options" toggle reveals CALL/PUT + strike + expiry.
- **Accounts: paper-only** (create + select; Alpaca/live deferred to a later promotion slice).
- **Close position (with inline confirm):** a `Close` button per position; the **first** click swaps
  the row's action to an inline `Confirm? Yes / No` (no modal), and **Yes** places an **offsetting
  market order** (side = `qty >= 0 ? 'SELL' : 'BUY'`, `qty = Math.abs(position.qty)`, carrying
  `option_type/strike/expiry` for option positions) via the normal place-order path, then refreshes
  positions + orders. `No` reverts. This avoids accidental one-click closes.
- **Double-click protection:** the submit / Yes-close buttons are **disabled while the mutation is
  pending** (the primary double-click guard); additionally the **component generates a fresh
  `crypto.randomUUID()` per submit-intent** and passes it as the `Idempotency-Key`, so a network
  retry of that one click dedupes server-side instead of creating a second order.
- Single-page layout (no modal): account bar → positions + order ticket → orders list.

## Components / files

- **`src/lib/oms.ts`** — client over the existing `request()` wrapper (401→logout,
  402→`EntitlementError` [unused here], else `Error(code)`):
  - `listBrokerAccounts(): Promise<{ broker_accounts: BrokerAccount[] }>`
  - `createBrokerAccount(label: string): Promise<BrokerAccount>` (sends `broker:'paper', is_paper:true`)
  - `listPositions(brokerAccountId: string): Promise<{ positions: Position[] }>`
  - `listOrders(cursor?: string): Promise<{ orders: Order[]; next_cursor: string | null }>`
  - `placeOrder(body: OrderCreate, idempotencyKey: string): Promise<OrderResult>` — sends the
    caller-supplied key as the `Idempotency-Key` header (the component generates one per submit-intent).
    `OrderResult = { order_id, broker_order_id, status, submitted_at }`.
  - `cancelOrder(orderId: string): Promise<OrderResult>`
  - Exports the `BrokerAccount`/`Position`/`Order`/`OrderResult`/`OrderCreate` types.
- **`src/features/portfolio/hooks.ts`** — `useBrokerAccounts()`, `useCreateAccount()` (invalidate
  `['broker-accounts']`), `usePositions(accountId)` (key `['positions', accountId]`,
  `enabled:!!accountId`), `useOrders()` (key `['orders']`), `usePlaceOrder()` (mutationFn
  `({ body, key }) => placeOrder(body, key)`; invalidate `['orders']` + `['positions']`),
  `useCancelOrder()` (invalidate `['orders']`).
- **`src/features/portfolio/AccountBar.tsx`** — props `{ accounts, selected, onSelect }`. A `<select>`
  of accounts + an inline "New paper account" label input → `useCreateAccount`. If `accounts` is
  empty, render a "Create a paper account to start trading." prompt with the same input.
- **`src/features/portfolio/PositionsTable.tsx`** — props `{ positions, confirmingId, closingId,
  onCloseRequest, onCloseConfirm, onCloseCancel }`. Columns: instrument (equity `symbol`; option
  `${symbol} $${strike} ${option_type} ${expiry}`), qty, avg entry. Each row keys on a stable
  `rowKey(position)` (e.g. `${symbol}|${option_type}|${strike}|${expiry}`). The action cell:
  normally a `Close` button → `onCloseRequest(rowKey)`; when `confirmingId === rowKey` it becomes an
  inline `Confirm? [Yes] [No]` (`Yes` → `onCloseConfirm(position)`, `No` → `onCloseCancel()`); while
  `closingId === rowKey` it shows "Closing…" and `Yes` is disabled. Empty → "No open positions."
- **`src/features/portfolio/OrderTicket.tsx`** — props `{ disabled, onSubmit, pending, error,
  lastResult }`. Fields: symbol (uppercased), side BUY/SELL toggle, qty, order_type market|limit,
  limit_price (shown only for limit), an Options checkbox → option_type CALL/PUT + strike + expiry.
  On submit, build `OrderCreate` (omit option fields unless Options is on; omit `limit_price` unless
  limit), generate `crypto.randomUUID()`, and call `onSubmit(order, idempotencyKey)`. The submit
  button is **disabled when `disabled` (no account) OR `pending`** (double-click guard). Shows `error`
  (the humanized RISK reason) and `lastResult` (e.g. "Order submitted · filled"). `data-testid`s on
  the form + key fields.
- **`src/features/portfolio/OrdersList.tsx`** — props `{ orders, onCancel, cancellingId, onLoadMore,
  hasMore }`. Rows: symbol, side, qty, order_type, status (color: filled→`pos`,
  rejected/cancelled→`neg`, pending/submitted→`warn`), `created_at`, and `reject_reason_code` when
  rejected. A `Cancel` button on `pending|submitted` rows → `onCancel(order)`; "Load more" when
  `hasMore`. Empty → "No orders yet."
- **`src/pages/Portfolio.tsx`** — composes it. Owns: `selectedAccount` state (defaults to the first
  account when they load), the place-order mutation + its error/result, `confirmingId`/`closingId`
  (close flow) and `cancellingId` (cancel) tracking, and the cursor accumulation for orders. Generates
  the `crypto.randomUUID()` for a close in the close-confirm handler and routes the offsetting
  `OrderCreate` through `usePlaceOrder`. A `// Portfolio` kicker + `h2`. Layout: `AccountBar` → a 2-col
  grid (`PositionsTable` | `OrderTicket`) → `OrdersList`.
- **`src/app/Router.tsx`** — replace `<Route path="portfolio" element={<PlaceholderPage title="Portfolio" />} />`
  with `<Route path="portfolio" element={<Portfolio />} />` + import.

## Data flow

Accounts load → page selects the first. Selected account → `usePositions` + the ticket's
`broker_account_id`. Placing an order (ticket or a close) → `usePlaceOrder` → on success invalidate
orders + positions (the new order appears, positions update). Cancel → `useCancelOrder` → invalidate
orders. "Close" builds the offsetting market `OrderCreate` from the position and routes through the
same mutation.

## Error handling

- No accounts → the AccountBar create prompt (positions/ticket hidden or disabled until one exists).
- Order/close `RISK_*` 422 → `Error(code)`; the ticket shows the humanized reason (e.g.
  `RISK_INSUFFICIENT_BUYING_POWER` → "insufficient buying power"); rejected orders also show their
  `reject_reason_code` in the list.
- Cancel 409 `ORDER_NOT_CANCELLABLE` → inline "Order can't be cancelled." (refetch to refresh status).
- 404 / 409 `BROKER_ACCOUNT_INACTIVE` → a generic "Couldn't place the order." message.

## Testing (vitest + @testing-library/react; mock the `oms` module or `fetch`; `MemoryRouter` where a Link/router is used)

- `src/lib/oms.test.ts` — each method's URL/method; `placeOrder(body, key)` sends the
  `Idempotency-Key: <key>` header and the body; a 422 throws `Error('RISK_INSUFFICIENT_BUYING_POWER')`.
- `AccountBar.test.tsx` — lists accounts; the create form calls `createBrokerAccount(label)`; empty
  state shows the prompt.
- `PositionsTable.test.tsx` — formats an option instrument; first `Close` click calls `onCloseRequest`
  (not `onCloseConfirm`); when `confirmingId` matches, `Yes` calls `onCloseConfirm(position)` and `No`
  calls `onCloseCancel`; empty state.
- `OrderTicket.test.tsx` — submitting an equity market order calls `onSubmit(body, key)` with the
  right body and a string key; enabling Options + limit adds the option fields + `limit_price`; the
  submit button is disabled while `pending` (double-click guard); a passed `error` renders.
- `OrdersList.test.tsx` — status colors; `Cancel` on a submitted order calls `onCancel`; a rejected
  order shows its `reject_reason_code`.
- `Portfolio.test.tsx` — with no accounts shows the create prompt; with an account + a position,
  `Close` → `Yes` places an **offsetting market order** (mock `placeOrder`, assert side/qty + that a
  key string was passed) and the order ticket is enabled.
- Gate: `npm run typecheck && npm run lint && npm run test:run` (all green); `npm run build` still
  prerenders 17 docs (client-only `/app` route).

## Out of scope (later)

Alpaca/live accounts + the live-promotion gate; live mark / unrealized P&L on positions (needs market
data — the positions endpoint returns only avg entry); stop / stop-limit order types; multi-leg
strategy orders; order-detail drill-in; partial-close (close is all-or-nothing for v1).
