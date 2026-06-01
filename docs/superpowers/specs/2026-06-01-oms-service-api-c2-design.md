# OMS service + API (OMS-2) — paper trading end-to-end — design

**Date:** 2026-06-01
**Slice:** LLD §5.1 / §6 / §13 step 11 — OMS service + API. Sub-slice **OMS-2** (wires the OMS-1 core
to the DB + API; makes paper trading work end-to-end). Band: OMS-1 (done) → OMS-2 (here) → OMS-3
(Alpaca) → OMS-4 (live promotion).
**Status:** Approved design, pre-plan.
**Builds on:** OMS-1 (`saalr_brokers.PaperBrokerAdapter`, `saalr_core.oms` FSM + risk gates +
`estimate_cost`); the existing `orders`/`executions`/`positions`/`broker_accounts`/`audit_log` tables
+ models; the BSM `pricing` engine + `bars`; `get_principal` RLS sessions.

## Purpose

Place a paper order through the API and get a deterministic, model-priced fill persisted to the DB —
with pre-trade risk gates, idempotency, position/cash tracking, and an audit trail. The
account-mode-agnostic OMS service routes by `broker_account.broker`, so OMS-3's Alpaca adapter slots
in unchanged.

## Decisions (locked during brainstorming)

1. **Model-priced marks** (self-contained): equity → latest bar close; option → BSM from the
   underlying's latest bar + trailing realized vol. No bar → reject (`RISK_NO_MARKET_DATA`).
2. **Explicit paper accounts** with a new `'paper'` broker value; balance derived from executions
   (no balance column); starting cash a config default.
3. **Synchronous** place→fill→persist (paper resolves instantly); one RLS transaction per request.
4. **Paper placement open to all tiers** (the live entitlement gate is OMS-4).

## Architecture

```
infra/migrations/versions/0005_paper_broker.py    # add 'paper' to broker_accounts.broker CHECK
saalr_core/oms/positions.py                         # NEW pure net_position(...) — shared by OMS-2 + paper adapter
packages/brokers/saalr_brokers/paper.py             # refactor _add_position onto net_position (behaviour-neutral)
apps/api/saalr_api/oms/                              # NEW API feature
  __init__.py  schemas.py  marks.py  repo.py  service.py  router.py
apps/api/saalr_api/main.py                           # register the oms router
packages/core/saalr_core/config.py                  # + paper_starting_cash (default 100000)
```

### Migration `0005` (only schema change)
Replace the `broker_accounts.broker` CHECK to include `'paper'`:
`ALTER TABLE broker_accounts DROP CONSTRAINT broker_accounts_broker_check;
 ALTER TABLE broker_accounts ADD CONSTRAINT broker_accounts_broker_check
   CHECK (broker IN ('paper','alpaca','ibkr','zerodha','angelone'));`
`down_revision = "0004"` (downgrade restores the original 4-value CHECK). `BrokerAccount.broker` is
plain `Text` — no model change; the schema-vs-models test is unaffected.
**Constraint name:** the plan must verify the actual CHECK name before dropping it (Postgres
auto-names an inline single-column CHECK `broker_accounts_broker_check`, but confirm against the live
DB / `0001` baseline; a `DROP CONSTRAINT IF EXISTS` plus the verified name avoids a failed migration).

### `saalr_core/oms/positions.py` (pure, shared)
`net_position(old_qty: int, old_avg: Decimal, signed_qty: int, price: Decimal) -> tuple[int, Decimal]`:
the buy/sell averaging — recompute the weighted average when opening/adding in the same direction;
keep the average on a partial close; reset the basis to `price` when the fill crosses through zero;
return `(new_qty, new_avg)` (`new_avg=0` when flat). This is the OMS-1 `_add_position` math extracted
once. The paper adapter's `_add_position` is refactored to call it (its tests stay green); OMS-2's DB
upsert calls it too.

### `oms/marks.py` (model-priced, self-contained)
`model_mark(session, *, symbol, market, option_type, strike, expiry, today) -> Decimal`:
- **equity** (`option_type is None`): the latest `bars` close for `(symbol, market, '1d')` → `Decimal`.
- **option**: `spot` = latest underlying bar close; `sigma` = trailing realized vol (annualized stdev
  of the last ~20 daily log returns from `bars`, floored); `t = (expiry − today).days / 365`;
  `rate` = a flat default (e.g. `0.04`); `pricing.greeks.price(OptionParams(spot, strike, t, rate,
  sigma, div_yield=0, kind))` → `Decimal`.
- **No underlying bar** (or `t ≤ 0`) → raise `NoMarketData` (the service maps it to `422
  RISK_NO_MARKET_DATA`).

### `oms/repo.py` (RLS session writes/reads)
- `get_broker_account(session, id) -> BrokerAccount | None`; `create_broker_account(...)`;
  `list_broker_accounts(session)`.
- `find_order_by_idempotency(session, tenant_id, key) -> Order | None`.
- `insert_order(...) -> Order` (status `pending`); `update_order_status(order, status, **fields)`.
- `insert_execution(order, broker_account_id, qty, price, commission, broker_execution_id)`.
- `account_balance(session, account, starting_cash) -> Decimal` = `starting_cash − Σ` side-signed
  execution notional (executions ⋈ orders; `×100` for options; minus commissions).
- `get_position(session, account_id, symbol, option_type, strike, expiry) -> Position | None`;
  `upsert_position(...)` (insert / update / **delete when qty→0**).
- `list_orders(...)` (cursor-paginated, RLS), `get_order(session, id)`, `list_positions(session,
  broker_account_id=None)`.
- `write_audit(session, tenant_id, user_id, action, target_type, target_id, before, after,
  request_id)`.

### `oms/service.py` — `place_order(session, principal, body, idempotency_key, request_id)`
1. `account = get_broker_account(body.broker_account_id)`; 404 if missing; reject if `status != "active"`.
2. **Idempotency:** if `idempotency_key` and `find_order_by_idempotency` hits → return that order (200).
3. Build `OrderRequest`; `mark = model_mark(...)` (→ 422 `RISK_NO_MARKET_DATA` on `NoMarketData`);
   `est_cost = estimate_cost(order, mark)`; `balance = account_balance(account, paper_starting_cash)`;
   `strategy_state = strategies.repo.get_strategy(strategy_id).state` if `strategy_id` else None;
   `ctx = RiskContext(account_active=True, strategy_state, available_balance=balance,
   estimated_cost=est_cost, recent_order_count=0, rate_limit=None)`.
4. `decision = run_gates(order, ctx)`. **Reject:** `insert_order(status="rejected",
   reject_reason_code=decision.code, idempotency_key)`; `write_audit("order.rejected", before=None,
   after={order})`; raise **422** `{error:{code:decision.code, message, details}}`.
5. **Pass:** `order = insert_order(status="pending", idempotency_key, ...)`. Route by `account.broker`:
   `"paper"` → `PaperBrokerAdapter(balance, lambda o: mark)`; else **400** `BROKER_NOT_SUPPORTED`
   (OMS-3). `result = await adapter.submit_order(broker_order, idempotency_key)`; read the resulting
   fill from `adapter.get_orders()`.
6. **Reconcile + FSM:**
   - filled → `insert_execution(...)`; `update_order_status(pending→submitted→filled,
     broker_order_id, submitted_at, filled_at)`; `upsert_position(net_position(...))`; audit
     `order.submitted` + `order.filled`.
   - open (resting) → `update_order_status(pending→submitted, broker_order_id, submitted_at)`; audit
     `order.submitted`.
   - cancelled (ioc/fok) → `pending→submitted→cancelled`; audit `order.submitted` + `order.cancelled`.
7. Return **200** `{order_id, broker_order_id, status, submitted_at}`.

`cancel_order(session, principal, order_id, request_id)`: load (RLS, 404); if status in
`{pending, submitted}` → `transition(... cancelled)` + audit `order.cancelled`; terminal → **409**
`ORDER_NOT_CANCELLABLE`.

### API (`oms/router.py`, all `Depends(get_principal)`)
- `POST /v1/broker-accounts` (paper only; 400 otherwise) · `GET /v1/broker-accounts`.
- `POST /v1/orders` (`Idempotency-Key` header) · `GET /v1/orders` · `GET /v1/orders/{id}` ·
  `POST /v1/orders/{id}/cancel`.
- `GET /v1/positions` (optional `broker_account_id`).
- Registered in `main.py`.

## Error handling
- 404: unknown/cross-tenant broker_account, order, position. 400: non-`paper` broker, unsupported
  market (US-only v1). 422: any risk-gate failure (persisted `rejected` + audit) incl.
  `RISK_NO_MARKET_DATA`. 409: cancelling a terminal order. asyncpg binds `Decimal` for NUMERIC, `date`
  for DATE, `datetime` for TIMESTAMPTZ.

## Testing
- **Pure** (`packages/core/tests/test_oms_positions.py`): `net_position` — open/add weighted average,
  partial close keeps avg, flip-through-zero resets basis to the fill, close-to-zero → `(0, 0)`. The
  OMS-1 paper-adapter tests stay green after the refactor.
- **Integration** (`tests/integration/test_oms.py`, 55432): create a paper account → 200; seed
  `bars`; **market buy fills** → 200 `filled` + an `execution` + a `position` row + reduced balance;
  **marketable limit** fills at the limit; **non-marketable limit (day)** → `submitted`, no position;
  **risk rejects** (422 + persisted `rejected` + audit): over-balance → `RISK_INSUFFICIENT_BUYING_POWER`,
  qty 0 → `RISK_INVALID_QUANTITY`, `draft`-strategy order → `RISK_STRATEGY_NOT_EXECUTABLE`, unknown
  underlying → `RISK_NO_MARKET_DATA`; **option order** (seeded underlying bars) → BSM mark → fills with
  option fields; **idempotency** (same key → one `order_id`, one execution); **cancel** a resting
  order → `cancelled`, cancel a filled → 409; **RLS** (second tenant can't see the first's orders /
  positions); an **audit row** exists per action.
- **Gate:** `uv run pytest packages/core/tests packages/brokers/tests` + `uv run pytest
  tests/integration/test_oms.py` (+ the schema/migration tests) + `uvx ruff check`.

## Out of scope (→ OMS-3/4)
- The real **Alpaca** adapter + reconciliation stream; partial fills; the **live-trading** entitlement
  gate + **MFA/14-day** promotion (OMS-4); per-strategy position-size limits + a market-hours gate;
  multi-market / India + the SEBI rate cap wiring; a live-chain mark source; an order-events
  websocket; a persistent in-memory paper-broker (OMS-2 rebuilds balance/positions from the DB per
  request).
