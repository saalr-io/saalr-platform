# OMS order core (OMS-1) — broker interface + paper adapter + FSM + risk gates — design

**Date:** 2026-06-01
**Slice:** LLD §6 / §13 step 11 — OMS core. Sub-slice **OMS-1** (pure: interface + paper adapter +
order FSM + risk gates). First slice of the OMS/brokers/paper+live band (OMS-1 core → OMS-2
service+API → OMS-3 Alpaca → OMS-4 live-promotion).
**Status:** Approved design, pre-plan.
**Builds on:** the §6 `BrokerAdapter` contract, the existing `orders`/`executions`/`positions`/
`broker_accounts` schema (slice 1), and the §7 strategy FSM pattern.

## Purpose

Stand up the **account-mode-agnostic** order core: a broker-adapter interface, a first-class
`PaperBrokerAdapter` (deterministic mark-price fills), the order-status FSM, and the pure pre-trade
risk gates. Paper and live share this exact code path; "paper" is a real adapter, not a special case.
No DB/API yet (OMS-2).

## Decisions (locked during brainstorming)

1. **Deterministic mark-price fills** in the paper adapter (market→mark; limit→limit iff marketable;
   stop→mark on cross; non-marketable ioc/fok→cancelled, day/gtc→open). No randomness.
2. **Core risk-gate set:** structural validation + executable-state + buying-power (via
   `get_account_balance`) + a configurable per-account order-rate cap.
3. **Two homes:** a new standalone `saalr-brokers` package (interface + paper adapter); the pure FSM +
   gates in `saalr_core/oms/`. Clean dependency direction (the future OMS service depends on both).
4. **Honest limitation:** a resting (non-marketable) paper limit does not auto-fill later (no
   market-data tick loop in OMS-1).

## Architecture

```
packages/brokers/                    # NEW workspace package "saalr-brokers" (pure in OMS-1; no SDK)
  pyproject.toml
  saalr_brokers/
    __init__.py
    types.py     # BrokerOrder, BrokerOrderResult, BrokerPosition, BrokerFill
    base.py      # BrokerAdapter ABC
    paper.py     # PaperBrokerAdapter
  tests/
saalr_core/oms/                       # NEW pure domain (no broker dependency)
  __init__.py
  types.py     # OrderStatus, OrderRequest, RiskContext, RiskDecision, reason-code constants
  fsm.py       # order-status FSM
  risk.py      # pure pre-trade gates + estimate_cost
packages/core/tests/                  # FSM + risk tests
```

`saalr-brokers` is added as a **root dependency** so its tests run under plain `uv run pytest` (it is
pure now). OMS-3 will add `alpaca-py` as an **optional extra** (`[project.optional-dependencies]`),
lazy-imported by the Alpaca adapter, so the default install stays light.

### `saalr_brokers/types.py` (LLD §6 dataclasses)
- `BrokerOrder{symbol, side("buy"/"sell"), qty:int, order_type("market"/"limit"/"stop"/"stop_limit"),
  limit_price: Decimal|None, stop_price: Decimal|None, time_in_force("day"/"gtc"/"ioc"/"fok"),
  option_type: str|None, strike: Decimal|None, expiry: date|None}` (frozen).
- `BrokerOrderResult{broker_order_id, status("submitted"/"rejected"), rejected_reason: str|None}`.
- `BrokerFill{broker_order_id, broker_execution_id, qty:int, price: Decimal, commission: Decimal}`.
- `BrokerPosition{symbol, qty:int, avg_price: Decimal, market_value: Decimal, unrealized_pnl: Decimal}`.

### `saalr_brokers/base.py` (the contract)
`BrokerAdapter(ABC)` with the §6 methods: `submit_order(order, idempotency_key) -> BrokerOrderResult`,
`cancel_order(broker_order_id) -> bool`, `get_orders(since) -> list[dict]`,
`get_positions() -> list[BrokerPosition]`, `get_account_balance() -> Decimal`,
`stream_executions()` (async-iterates fills). The OMS only needs submit/cancel/get_orders/
get_positions/get_account_balance in OMS-1/2; `stream_executions` is for live reconciliation (OMS-3).

### `saalr_brokers/paper.py` (`PaperBrokerAdapter`)
`PaperBrokerAdapter(starting_cash: Decimal, mark_provider: Callable[[BrokerOrder], Decimal])`. Holds
paper cash, a per-`broker_order_id` order book, fills, and net positions. Deterministic, synchronous:
- `submit_order(order, idempotency_key)`:
  - **Idempotency:** if `idempotency_key` was already seen, return the prior `BrokerOrderResult`
    (no second fill).
  - Generate `broker_order_id`; `mark = mark_provider(order)`.
  - **Fill decision:** market → fill `qty` at `mark`. limit-buy → fill at `limit_price` iff
    `mark ≤ limit_price`; limit-sell → fill at `limit_price` iff `mark ≥ limit_price`; else not
    marketable. stop-buy → triggered iff `mark ≥ stop_price` (then market-fill at mark); stop-sell →
    `mark ≤ stop_price`; stop_limit → on trigger behaves as a limit at `limit_price`.
  - **Not marketable:** `ioc`/`fok` → record the order `cancelled`; `day`/`gtc` → record `open`
    (no auto-fill later). Either way `BrokerOrderResult(status="submitted")` (the order was accepted).
  - **On fill:** create a `BrokerFill` (price=fill price, qty, commission=0), update cash
    (`buy: cash -= price*qty*mult`, `sell: cash += price*qty*mult`; `mult=100` if `option_type` else 1),
    update the net position (`avg_price` recomputed on adds; sign by side). Mark the order `filled`.
  - Returns `BrokerOrderResult(broker_order_id, "submitted")`. (Reject only on a malformed order the
    OMS gates should have caught — the adapter trusts the OMS; it does not re-run risk.)
- `cancel_order(broker_order_id)` → cancel an `open` order (True); already-filled/unknown → False.
- `get_orders(since)` → the order book rows (id, status, fills) for reconciliation.
- `get_positions()` → net `BrokerPosition`s. `get_account_balance()` → current paper cash.
- `stream_executions()` → async-yields the recorded `BrokerFill`s (drains a queue; simple for paper).

> Determinism: no RNG, no wall-clock in fill decisions. The `mark_provider` is injected (OMS-2 wires a
> real mark source; tests pass a fixture). `mult = 100` for option legs mirrors `OPTION_MULTIPLIER`.

### `saalr_core/oms/fsm.py`
`class OrderStatus(str, Enum)`: `PENDING, SUBMITTED, PARTIAL, FILLED, CANCELLED, REJECTED`.
`VALID_TRANSITIONS`: `pending→{submitted,rejected,cancelled}`, `submitted→{partial,filled,cancelled,
rejected}`, `partial→{filled,cancelled}`, `filled/cancelled/rejected→∅`. `transition(current, target)`
returns `target` or raises `IllegalOrderTransition` (same shape as the strategy FSM).

### `saalr_core/oms/types.py` + `risk.py`
- `OrderRequest{side, qty, order_type, limit_price, stop_price, time_in_force, symbol, option_type,
  strike, expiry}` (frozen value type; `Decimal` prices).
- `RiskContext{account_active: bool, strategy_state: str|None, available_balance: Decimal,
  estimated_cost: Decimal, recent_order_count: int, rate_limit: int|None}`.
- `RiskDecision{ok: bool, code: str|None, message: str|None}`.
- Reason-code constants (str): `RISK_INVALID_QUANTITY`, `RISK_INVALID_ORDER_TYPE`, `RISK_INVALID_SIDE`,
  `RISK_INVALID_TIF`, `RISK_MISSING_LIMIT_PRICE`, `RISK_MISSING_STOP_PRICE`, `RISK_ACCOUNT_INACTIVE`,
  `RISK_STRATEGY_NOT_EXECUTABLE`, `RISK_INSUFFICIENT_BUYING_POWER`, `RISK_RATE_LIMIT_EXCEEDED`.
- Gates (each pure `(order, ctx) -> str|None`): `_structural`, `_executable_state`, `_buying_power`,
  `_rate_cap`. Run in that fixed order by `run_gates(order, ctx) -> RiskDecision` (first failure wins;
  all pass → `RiskDecision(ok=True)`).
- `estimate_cost(order, mark: Decimal) -> Decimal` = `mark * qty * (100 if option_type else 1)`
  (the caller computes this and puts it in `ctx.estimated_cost`).

Gate semantics:
- `_structural`: `qty>0`; `order_type∈{market,limit,stop,stop_limit}`; `side∈{buy,sell}`;
  `time_in_force∈{day,gtc,ioc,fok}`; `limit/stop_limit` require `limit_price` and `limit_price>0`;
  `stop/stop_limit` require `stop_price` and `stop_price>0`.
- `_executable_state`: `account_active` is True; if `strategy_state` is not None it must be in
  `{"paper","live"}` (a `draft`/`backtested`/`paused`/`archived` strategy cannot place orders).
- `_buying_power`: for `side=="buy"`, `estimated_cost ≤ available_balance` (sells don't consume cash
  in v1).
- `_rate_cap`: `rate_limit is not None and recent_order_count ≥ rate_limit` → reject.

## Error handling
- The risk gates never raise — they return a `RiskDecision` (the OMS service maps a failure to a
  `rejected` order + `reject_reason_code` in OMS-2).
- The FSM raises `IllegalOrderTransition` on an illegal transition (programmer error; the OMS service
  only drives legal transitions).
- The paper adapter trusts the OMS (gates run upstream); it models acceptance + deterministic fills,
  not validation.

## Testing (all DB-free, fast, deterministic)
- **FSM** (`packages/core/tests/test_oms_fsm.py`): every legal transition returns the target; a sample
  of illegal ones raise (`filled→submitted`, `pending→filled`, `cancelled→submitted`,
  `rejected→filled`).
- **Risk gates** (`packages/core/tests/test_oms_risk.py`): each gate's pass + fail → the exact reason
  code (qty 0 → `RISK_INVALID_QUANTITY`; limit w/o price → `RISK_MISSING_LIMIT_PRICE`; inactive
  account → `RISK_ACCOUNT_INACTIVE`; strategy `draft` → `RISK_STRATEGY_NOT_EXECUTABLE`; cost>balance →
  `RISK_INSUFFICIENT_BUYING_POWER`; rate over → `RISK_RATE_LIMIT_EXCEEDED`); `run_gates` with multiple
  violations returns the **first** (structural before buying-power); a clean order → `ok`;
  `estimate_cost` for an option (×100) vs equity.
- **Paper adapter** (`packages/brokers/tests/test_paper_adapter.py`): market buy fills at the mark
  (cash decreases by `mark*qty*mult`, position appears); marketable limit fills at the limit;
  non-marketable limit (`day`) rests `open` (no fill); same limit with `ioc` → `cancelled`; stop-buy
  triggers when `mark ≥ stop`; `cancel_order` on an open order → True, on a filled order → False;
  `get_account_balance` reflects fills; **idempotency** (same key twice → one fill, same result);
  `get_positions` nets a buy then a partial sell.
- **Gate:** `uv run pytest packages/core/tests packages/brokers/tests` + `uvx ruff check`.

## Out of scope (→ OMS-2+)
- The DB-backed OMS service + `POST /v1/orders` / cancel / list + positions API; audit-log writes; the
  paper `broker_account` row + real mark sourcing (chain/bars); idempotency at the API/DB layer;
  execution reconciliation. The real **Alpaca** adapter + SDK extra (OMS-3). The **live-promotion**
  MFA + 14-day gate (OMS-4). Partial-fill simulation, resting-limit auto-fill (tick loop), short-sale
  margin, and the India SEBI rate cap wiring (the gate exists; configuration comes with India).
