# Alpaca broker adapter (OMS-3a) — design

**Date:** 2026-06-01
**Slice:** LLD §6 / §13 step 12 — Alpaca adapter. Sub-slice **OMS-3a** (the adapter only). **OMS-3b**
(wire into the OMS service + reconciliation) is the next slice.
**Status:** Approved design, pre-plan.
**Builds on:** the OMS-1 `BrokerAdapter` ABC + `BrokerOrder/BrokerOrderResult/BrokerPosition/BrokerFill`
dataclasses in `saalr-brokers`; the env-gated live-smoke pattern (`RUN_LIVE_SMOKE` + key skip).

## Purpose

A real `AlpacaAdapter` (alpaca-py) that satisfies the same `BrokerAdapter` contract the
`PaperBrokerAdapter` does, so OMS-3b can route `broker='alpaca'` with no service changes. Isolated,
testable in isolation, no DB/OMS-service/reconciliation work here.

## Decisions (locked during brainstorming)

1. **env keys + stub-tested adapter:** the adapter takes `(api_key, api_secret, is_paper)` + an
   **injectable** client; unit tests inject a stub `TradingClient` (no network); an env-gated live
   smoke hits real Alpaca paper when keys are present. credential-resolution (`credential_ref`→keys)
   is OMS-3b.
2. **alpaca-py is an optional extra** of `saalr-brokers`, lazy-imported — the default install stays
   alpaca-free.
3. **`stream_executions` deferred** (raises `NotImplementedError`); OMS-3b reconciles by polling
   `get_orders`.
4. **Option legs** map to **OCC symbols**; multi-leg combos are out of scope (each leg is its own order).

## Architecture

```
packages/brokers/pyproject.toml           # + [project.optional-dependencies] alpaca = ["alpaca-py>=0.20"]
packages/brokers/saalr_brokers/alpaca.py  # AlpacaAdapter, occ_symbol(), _ALPACA_STATUS map, BrokerError
packages/brokers/tests/test_alpaca.py     # pure (OCC + status) + extra-gated stub units + key-gated live smoke
```

`saalr-brokers` stays a light root dependency; alpaca-py installs only with the `alpaca` extra. All
`alpaca.*` imports are **inside methods** (lazy), so `import saalr_brokers.alpaca` works without the SDK.

### `occ_symbol(root, expiry, option_type, strike) -> str` (pure)
OCC option symbol: `root` + `expiry` as `%y%m%d` + `"C"|"P"` + `int(round(strike*1000))` zero-padded
to 8 digits. E.g. `occ_symbol("AAPL", date(2025,6,20), "CALL", 100.0) == "AAPL250620C00100000"`.
(`option_type` accepts `CALL/CE`→C, `PUT/PE`→P.) Pure string math — no alpaca dependency.

### `_ALPACA_STATUS: dict[str, str]` + `map_status(alpaca_status) -> str` (pure)
Alpaca order status → our `OrderStatus` value: `new/accepted/pending_new/accepted_for_bidding →
"submitted"`, `partially_filled → "partial"`, `filled → "filled"`, `canceled/expired/done_for_day/
pending_cancel → "cancelled"`, `rejected/suspended/stopped → "rejected"`. Unknown → `"submitted"`
(conservative; reconciliation re-reads later).

### `AlpacaAdapter(api_key, api_secret, is_paper=True, *, client=None)`
Implements `BrokerAdapter`.
- **`_client()`** (lazy): returns the injected `client` if given; else
  `from alpaca.trading.client import TradingClient; TradingClient(api_key, api_secret, paper=is_paper)`,
  cached on the instance. `is_paper` selects Alpaca's paper vs live endpoint (separate accounts, §6).
- **`submit_order(order, idempotency_key) -> BrokerOrderResult`:**
  - Build the alpaca request (lazy import `from alpaca.trading.requests import MarketOrderRequest,
    LimitOrderRequest, StopOrderRequest, StopLimitOrderRequest` and `from alpaca.trading.enums import
    OrderSide, TimeInForce`). `symbol` = `occ_symbol(...)` if `order.option_type` else `order.symbol`.
    Map `side` (buy/sell→OrderSide), `time_in_force` (day/gtc/ioc/fok→TimeInForce), `qty`,
    `limit_price`/`stop_price` (as float), and **`client_order_id=idempotency_key`** (Alpaca-native
    idempotency).
  - `o = client.submit_order(req)`. On an SDK exception → raise `BrokerError`. Map `o.status`
    (string/enum) via `map_status`: `"rejected"` → `BrokerOrderResult(str(o.id), "rejected",
    rejected_reason=getattr(o, "rejected_reason", None) or str(o.status))`; else →
    `BrokerOrderResult(str(o.id), "submitted")`.
- **`cancel_order(broker_order_id) -> bool`:** `client.cancel_order_by_id(broker_order_id)` → True;
  on a not-cancellable/unknown SDK error → False.
- **`get_orders(since=None) -> list[dict]`:** `client.get_orders(...)` → normalized dicts
  `{broker_order_id: str(o.id), status: map_status(o.status), symbol, qty: int(o.qty), side,
  filled_qty: int(o.filled_qty or 0), filled_avg_price: Decimal(o.filled_avg_price) if set else None,
  client_order_id}`.
- **`get_positions() -> list[BrokerPosition]`:** `client.get_all_positions()` → `BrokerPosition(symbol,
  qty=int(p.qty), avg_price=Decimal(p.avg_entry_price), market_value=Decimal(p.market_value),
  unrealized_pnl=Decimal(p.unrealized_pl))`.
- **`get_account_balance() -> Decimal`:** `Decimal(str(client.get_account().buying_power))`.
- **`stream_executions(self)`:** raises `NotImplementedError("reconcile via get_orders polling (OMS-3b)")`.
- **`BrokerError(Exception)`** wraps SDK/transport errors so callers don't see raw alpaca exceptions.

> Decimal at the boundary: alpaca returns numbers as strings/floats; the adapter converts to `Decimal`
> via `Decimal(str(x))`. `qty` is an int.
>
> **Sync SDK in async methods:** alpaca-py's `TradingClient` is **synchronous** (REST). The adapter's
> `async def` methods therefore call it via `await asyncio.to_thread(client.method, ...)` so a network
> call never blocks the event loop. The injected stub client is a plain **synchronous** class (so
> `to_thread` works for both real and stub). `stream_executions` is written as an async generator that
> raises before yielding (`raise NotImplementedError(...)` followed by an unreachable `yield`) so it
> satisfies the ABC's async-iterator contract yet raises on first iteration.

## Error handling
- Any alpaca SDK/API error in `submit_order`/`get_*` → wrapped in `BrokerError`. `cancel_order`
  swallows a not-found/not-cancellable error and returns `False`. An unknown alpaca status maps to
  `"submitted"` (reconciliation corrects it). Missing `client` + missing keys → `BrokerError` on first
  `_client()` use.

## Testing
- **Pure** (`packages/brokers/tests/test_alpaca.py`, always runs — no alpaca, no network):
  - `occ_symbol`: call/put, the `strike×1000` zero-pad (100→`00100000`, 5.5→`00005500`), a 6-char root.
  - `map_status`: each documented alpaca status → the right our-status; an unknown → `"submitted"`.
- **Stub-client unit** (`pytest.importorskip("alpaca")` — runs only with the alpaca extra installed;
  no network, no keys; a stub `TradingClient` is injected that records the submitted request and
  returns canned objects):
  - `submit_order` for a **market equity** order → a `MarketOrderRequest` with the right
    `symbol/qty/side/time_in_force` + `client_order_id == idempotency_key`; result `submitted` with
    `broker_order_id` from the stub's order.
  - **limit / stop / stop_limit** → the matching request type + prices.
  - an **option** order → the request `symbol` is the OCC symbol.
  - an alpaca **rejected** status → `BrokerOrderResult(rejected, reason)`.
  - `get_orders` → normalized dicts with mapped status + `filled_avg_price` as `Decimal`.
  - `get_positions` → `BrokerPosition`s with `Decimal` fields; `get_account_balance` →
    `Decimal(buying_power)`; `cancel_order` → True; `stream_executions` raises `NotImplementedError`.
- **Live smoke** (`importorskip("alpaca")` + `skipif` not `ALPACA_PAPER_KEY`/`ALPACA_PAPER_SECRET`):
  build `AlpacaAdapter(key, secret, is_paper=True)`, assert `await get_account_balance()` is a
  non-negative `Decimal`. Opt-in only.
- **Gate:** default `uv run pytest packages/brokers/tests` runs the pure tests and **skips** the
  alpaca/live ones → green without the SDK. The stub units run after installing the extra
  (`uv pip install alpaca-py` or `uv sync --extra alpaca` for the package). `uvx ruff check`.

## Out of scope (→ OMS-3b / later)
- Wiring `broker='alpaca'` into `place_order` (the service still 400s non-paper, unchanged here);
  `credential_ref`→keys resolution; the async-submit flow (order stays `submitted`) + **reconciliation**
  (poll `get_orders` → persist executions/positions + `last_reconciled_at`); the real
  `stream_executions` trade-update websocket; multi-leg combo orders + Alpaca options entitlement;
  IBKR/Zerodha/AngelOne adapters.
