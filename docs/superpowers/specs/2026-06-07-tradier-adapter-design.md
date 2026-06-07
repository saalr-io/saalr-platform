# Tradier Broker Adapter (sandbox) — Design Spec

**Date:** 2026-06-07
**Slice:** Slice 1 — Tradier sandbox adapter + multi-broker OMS routing (no OAuth, no live money, no account-linking UI)
**Status:** Approved design, ready for implementation plan

## Context

The platform already has a broker-adapter abstraction in `packages/brokers/saalr_brokers/`:
- `base.py` — `BrokerAdapter` ABC: `submit_order`, `cancel_order`, `get_orders`, `get_positions`,
  `get_account_balance`, `stream_executions`.
- `types.py` — `BrokerOrder` (carries single-leg option fields), `BrokerOrderResult`, `BrokerFill`,
  `BrokerPosition`.
- `alpaca.py` — reference adapter (pure mappers `occ_symbol`/`map_status` + lazy SDK client;
  `stream_executions` is a no-op because reconciliation polls `get_orders`).
- `credentials.py` — prefix-routed resolver (`env:` / `secretsmanager:`) returning `(key, secret)`;
  `build_alpaca_adapter(credential_ref, is_paper, resolver)`.

The OMS consumes adapters but **hardcodes broker support**:
- `apps/api/saalr_api/oms/service.py` rejects `broker not in ("paper","alpaca")`, branches on
  `is_alpaca`, and uses an injected `adapter_factory`.
- `apps/api/saalr_api/oms/router.py` validates `broker in ("paper","alpaca")` and reads a single
  `app.state.alpaca_adapter_factory`.
- `apps/api/saalr_api/main.py` wires `app.state.alpaca_adapter_factory`.

This slice adds **Tradier** — a good fit because the product is options-centric and Tradier has
first-class options + a token-auth REST API that maps cleanly onto the existing contract. It also
generalizes the OMS broker selection so further brokers are drop-in.

### Decisions locked in brainstorming
- **Broker:** Tradier (over SnapTrade) — options-native, token auth fits the resolver, 1:1 with the
  `BrokerAdapter` contract.
- **Scope:** sandbox/paper first via an env-token credential_ref. Live OAuth is a later slice.
- **No account-linking UI** in this slice (belongs with the live-OAuth slice); Tradier sandbox
  accounts are created via the existing broker-account API.

## Goal

A `TradierAdapter` implementing `BrokerAdapter` against the Tradier **sandbox** REST API, plus an
OMS broker→factory registry so `place_order` / `place_strategy` / `cancel_order` route to Tradier the
same way they route to Alpaca — verifiable end-to-end with stubbed HTTP and no real money.

## Components

### Shared OCC helper — `packages/brokers/saalr_brokers/occ.py` (new)
Move `occ_symbol(root, expiry, option_type, strike)` out of `alpaca.py` into `occ.py`. `alpaca.py`
re-exports it (`from .occ import occ_symbol`) so `test_alpaca_pure` and any
`from saalr_brokers.alpaca import occ_symbol` keep working.

### Tradier adapter — `packages/brokers/saalr_brokers/tradier.py` (new)
Raw `httpx.AsyncClient` (no SDK); retry/error handling mirrors `saalr_core.marketdata.massive`.
A `TradierError(Exception)` wraps transport/HTTP errors (never leaks the token).

- `TradierAdapter(access_token, account_id, is_paper=True, *, client=None)`.
  `BASE = "https://sandbox.tradier.com/v1" if is_paper else "https://api.tradier.com/v1"`.
  Headers: `Authorization: Bearer <token>`, `Accept: application/json`.
- **Pure helpers (no network — the test core):**
  - `build_order_form(order: BrokerOrder, tag: str) -> dict[str, str]`:
    - equity: `{class: "equity", symbol, side, quantity, type, duration[, price][, stop]}`.
    - option: `{class: "option", symbol: <underlying>, option_symbol: occ_symbol(...),
      side, quantity, type, duration[, price][, stop]}`.
    - `side` map: equity `buy→buy`, `sell→sell`; **option `buy→buy_to_open`, `sell→sell_to_open`**
      (open-only — see limitations).
    - `type` passthrough (`market`/`limit`/`stop`/`stop_limit`); `price`=limit_price, `stop`=stop_price.
    - `duration` map: `day→day`, `gtc→gtc`, else `day`.
    - `tag`=idempotency_key (Tradier order tag; alnum/hyphen, truncated to Tradier's limit).
  - `map_status(tradier_status: str) -> str`: `ok|pending|open|partially_filled→...`,
    `filled→filled`, `partially_filled→partial`, `canceled|expired|rejected→cancelled/rejected`
    (full map in code), unknown→`submitted`.
  - `parse_orders(json) -> list[dict]`: normalize Tradier order(s) to the **same dict shape Alpaca
    returns** — `{broker_order_id, status, symbol, qty, side, filled_qty, filled_avg_price,
    client_order_id}` (`client_order_id` from `tag`).
  - `parse_positions(json) -> list[BrokerPosition]`: `qty=quantity`, `avg_price=cost_basis/quantity`,
    `market_value=cost_basis`, `unrealized_pnl=0` (marks enriched elsewhere).
  - `parse_balance(json) -> Decimal`: option/stock buying power, else `total_cash`.
- **Methods:**
  - `submit_order` → `POST /accounts/{account_id}/orders` (form-encoded `build_order_form`); on
    Tradier error payload or rejected status → `BrokerOrderResult(id, "rejected", reason)`, else
    `BrokerOrderResult(id, "submitted")`.
  - `cancel_order` → `DELETE /accounts/{account_id}/orders/{id}` → `True`/`False`.
  - `get_orders(since)` → `GET /accounts/{account_id}/orders` → `parse_orders`; if `since`, filter
    client-side by transaction date.
  - `get_positions` → `GET /accounts/{account_id}/positions` → `parse_positions`.
  - `get_account_balance` → `GET /accounts/{account_id}/balances` → `parse_balance`.
  - `stream_executions` → `raise NotImplementedError(...)` then `yield` (async-generator no-op, like
    Alpaca; reconcile polls `get_orders`).
  - Tradier sometimes returns `"null"`/single-object instead of arrays for empty/one-element results;
    parsers normalize both.

### Builder — in `packages/brokers/saalr_brokers/credentials.py`
`build_tradier_adapter(credential_ref, is_paper, resolver) -> TradierAdapter`:
resolves `(access_token, account_id) = resolver.resolve(credential_ref, is_paper)` and constructs
the adapter. The resolver's `(key, secret)` slots carry `(access_token, account_id)`:
- env: `TRADIER_SANDBOX_KEY=<sandbox token>`, `TRADIER_SANDBOX_SECRET=<sandbox account id>`,
  credential_ref `env:TRADIER_SANDBOX`.
- secretsmanager: secret JSON `{"key": <token>, "secret": <account_id>}`.

### OMS broker→factory registry
- `main.py`: build `app.state.adapter_factories = {`
  `"alpaca": lambda a: build_alpaca_adapter(a.credential_ref, a.is_paper, resolver),`
  `"tradier": lambda a: build_tradier_adapter(a.credential_ref, a.is_paper, resolver)}`.
  Keep `app.state.alpaca_adapter_factory` only if still referenced; otherwise remove.
- `service.py`: replace the hardcoded checks. `place_order` accepts `adapter_factories: dict | None`;
  `supported = {"paper"} | set(adapter_factories or {})`; reject unknown with `BROKER_NOT_SUPPORTED`;
  `is_live = account.broker != "paper"`; when live, `adapter = adapter_factories[account.broker](account)`.
  `place_strategy` threads `adapter_factories` through to `place_order`. `cancel_order` uses
  `adapter_factories.get(account.broker)` when the account is live and has a `broker_order_id`.
- `router.py`: accept `tradier` in create/validate; on create with `broker=="tradier"` set
  `credential_ref="env:TRADIER_SANDBOX"`, `is_paper=True`; pass
  `request.app.state.adapter_factories` everywhere `alpaca_adapter_factory` was passed.

## Data flow
`POST /v1/broker-accounts {broker:"tradier"}` → row with `credential_ref="env:TRADIER_SANDBOX"`.
`POST /v1/orders` (or strategy place) → `service.place_order` → `adapter_factories["tradier"](account)`
→ `TradierAdapter.submit_order` → Tradier sandbox → `BrokerOrderResult` persisted. Reconcile worker
polls `get_orders` (unchanged; broker-agnostic dict shape).

## Error handling
- Transport/HTTP/Tradier error payloads → `TradierError`; `submit_order` surfaces a rejected result
  or the OMS maps to its standard error envelope (as it does for Alpaca's `BrokerError`).
- Missing/blank credentials → `CredentialError` from the resolver (never carries secrets).
- Unknown broker at the OMS → `BROKER_NOT_SUPPORTED` (400).
- `cancel_order` returns `False` on any failure (matches Alpaca).

## Known limitations (documented; follow-ups)
- Option side is **open-only** (`buy_to_open`/`sell_to_open`) — `BrokerOrder` lacks open/close intent;
  exits/rolls need a future `position_effect` field.
- Positions: `market_value=cost_basis`, `unrealized_pnl=0` (Tradier gives cost basis only; OMS
  `marks.py` enriches marks).
- `time_in_force` `ioc`/`fok` → `day`.
- No multi-leg single-ticket order (OMS already places legs as N single orders).

## Testing
- `packages/brokers/tests/test_tradier_pure.py`: `occ_symbol`; `build_order_form` for an equity and an
  option leg (class, `option_symbol`, side mapping, price/duration); `map_status`; `parse_orders`,
  `parse_positions`, `parse_balance` (including the single-object/`"null"` normalization).
- `packages/brokers/tests/test_tradier_adapter.py`: `submit_order` (success + rejected), `cancel_order`,
  `get_orders` driven through an injected `httpx.MockTransport` returning canned Tradier JSON — asserts
  the request path/method/body and the normalized result. No network.
- `tests/integration/test_oms_tradier.py`: creating a `tradier` broker account is accepted (not
  `BROKER_NOT_SUPPORTED`); `place_order` with a stub tradier factory submits and records the
  broker order id; an unknown broker still returns `BROKER_NOT_SUPPORTED`.
- Regression: existing `test_alpaca_pure`, `test_alpaca_adapter`, OMS tests stay green (Alpaca path and
  the `occ_symbol` import unchanged).

## Out of scope (later slices)
Live OAuth + per-user token storage/refresh; broker account-linking UI; multi-leg single-ticket
orders; options exit/roll (`position_effect`); real-time account streaming; compliance/ODD gating;
SnapTrade or other brokers.

## Build sequence (for the plan)
1. Extract `occ.py`; re-export from `alpaca.py`; keep alpaca tests green.
2. `tradier.py` pure helpers (`build_order_form`, `map_status`, parsers) + `test_tradier_pure.py`.
3. `TradierAdapter` methods over httpx + `test_tradier_adapter.py` (MockTransport).
4. `build_tradier_adapter` in `credentials.py` + a builder unit test.
5. OMS registry: `main.py` `adapter_factories`; `service.py` + `router.py` generalization +
   `test_oms_tradier.py`.
6. Gate: brokers + OMS + market tests green; ruff clean.
