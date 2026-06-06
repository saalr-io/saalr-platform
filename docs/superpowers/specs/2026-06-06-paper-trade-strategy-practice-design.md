# Paper-Trade a Strategy (Beginner Practice) — Design Spec

**Date:** 2026-06-06
**Slice:** Connect Strategies + Regimes (Ideas) to the Portfolio so beginners can paper-trade a whole strategy in one click
**Status:** Approved design, ready for implementation plan

## Context

The Portfolio (`/app/portfolio`) is a working **paper-trading desk**: paper broker accounts, a positions table, a single-leg order ticket, and close-position. The OMS places **one leg at a time** (`POST /v1/orders`, with full risk + paper-fill in `service.place_order`). The Ideas page (`/app/ideas`) recommends templates from a ticker's regime (each card has "Apply → builder"); the Strategies builder analyzes/saves multi-leg configs.

**The gap:** nothing turns a *multi-leg strategy* into paper trades, so a beginner can't go "regime → recommended strategy → practise it → watch the P&L." This slice closes that loop: a one-click **Paper trade** that places every leg of a strategy into a Practice paper account and points the user at their Portfolio.

### Decisions locked during brainstorming
- **One combined slice:** the place-a-strategy plumbing **and** the guided beginner entry points (deferring only the strategy-grouped P&L view in Portfolio).
- **Practice hub = the Ideas page** (reuses the regime + recommendation context); plus a Paper-trade button on the Strategies builder.
- **Mechanism = a new backend endpoint** `POST /v1/orders/strategy` (reuses the existing per-order risk + paper-fill), not a client loop.
- Legs are placed as **standalone paper orders (no `strategy_id`)** — the risk gate rejects any `strategy_id` whose strategy isn't in an executable (`paper`/`live`) FSM state, and reaching `paper` requires the `draft → backtested → paper` promotion path, which is too heavy for a one-click practice trade. (Grouped-P&L grouping is deferred; see Out of scope.)

## Goal

Let a beginner paper-trade a recommended (or built) strategy in one guided action: ensure a Practice account exists, place all legs, and surface an honest per-leg result with a link to the Portfolio.

## Architecture

```
Ideas reco card ─┐                         Strategies builder ─┐
  [Paper trade]  │  (guided confirm)         [Paper trade]     │
                 ▼                                             ▼
   usePaperTradeStrategy:
     ensure a Practice paper account ──► [Ideas only] buildTemplate(key) ──►
     placeStrategy({ broker_account_id, underlying, legs })
                              │
   POST /v1/orders/strategy ──► service.place_strategy():
       for each option/equity leg → service.place_order (risk + paper-fill), strategy_id=None
       skip cash legs → catch per-leg reject → collect per-leg {status, reject_code}
                              │
   result: { results[], placed, rejected } → "placed 2/2 → view in Portfolio →"
```

## Backend (`apps/api/saalr_api/oms/`)

### Schema (`schemas.py`)
```python
class LegSpec(BaseModel):
    kind: str                      # "option" | "equity" | "cash"
    side: str | None = None        # BUY | SELL (option/equity)
    qty: int | None = None
    option_type: str | None = None # CALL | PUT
    strike: Decimal | None = None
    expiry: date | None = None
    amount: Decimal | None = None  # cash legs (ignored for orders)

class StrategyOrderCreate(BaseModel):
    broker_account_id: str
    underlying: str = Field(min_length=1)
    legs: list[LegSpec] = Field(min_length=1)
```

### Service (`service.py`) — `place_strategy`
```
async def place_strategy(session, principal, body: StrategyOrderCreate, idem, request_id, factory) -> dict
```
- For each leg `i`, in order:
  - `cash` → skip; record `{"leg_index": i, "kind": "cash", "status": "skipped"}`.
  - `option` → `OrderCreate(broker_account_id, symbol=underlying, side, qty, order_type="market", option_type, strike, expiry, time_in_force="day")` (**no `strategy_id`**).
  - `equity` → `OrderCreate(broker_account_id, symbol=underlying, side, qty, order_type="market")`.
  - `place_order` **raises `HTTPException` on a reject** (`RISK_NO_MARKET_DATA`, a risk gate, an inactive account), so wrap each call:
    ```python
    try:
        res = await place_order(session, principal, order, f"{idem}:{i}", request_id, factory)
        results.append({"leg_index": i, "kind": leg.kind, "status": res["status"], "order_id": res["order_id"]})
    except HTTPException as exc:
        code = exc.detail["error"]["code"] if isinstance(exc.detail, dict) else str(exc.detail)
        results.append({"leg_index": i, "kind": leg.kind, "status": "rejected", "reject_code": code})
    ```
- Return `{ "broker_account_id": str(body.broker_account_id), "results": [...], "placed": <# results whose status is not "rejected"/"skipped">, "rejected": <# results with status "rejected"> }`.
- Per-leg idempotency keys (`f"{idem}:{i}"`) make a whole-strategy retry safe; a leg placed before a later reject stays placed (no rollback) — the per-leg result is the honest record.

### Router (`router.py`)
```python
@router.post("/v1/orders/strategy")
async def place_strategy(body: StrategyOrderCreate, request: Request,
                         idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                         ctx=Depends(get_principal)) -> dict:
    session, principal = ctx
    factory = getattr(request.app.state, "alpaca_adapter_factory", None)
    idem = idempotency_key or str(new_id())
    return await service.place_strategy(session, principal, body, idem, _request_id(request), factory)
```
Ungated like the rest of the OMS (auth-only). No DB migration (reuses `orders`/`positions`; `strategy_id` column already exists on orders).

## Frontend

### Client (`apps/web/src/lib/oms.ts`)
- Types: `StrategyLeg` (kind/side/qty/option_type/strike/expiry/amount), `StrategyOrderResult { results: { leg_index:number; kind:string; status:string; order_id?:string; reject_code?:string }[]; placed:number; rejected:number }`.
- `placeStrategy(body: { broker_account_id, underlying, legs }): Promise<StrategyOrderResult>` → `POST /v1/orders/strategy` with an `Idempotency-Key: crypto.randomUUID()` header (one per user click, so a network retry is safe).

### Hook (`apps/web/src/features/portfolio/usePaperTrade.ts`)
- `usePaperTradeStrategy()` → a mutation taking a `StrategyConfig`:
  1. `accounts = await listBrokerAccounts()`; pick the first `is_paper` account, else `createBrokerAccount('Practice')`.
  2. `placeStrategy({ broker_account_id, underlying: config.underlying, legs: config.legs })`.
  - On success invalidates the positions/orders/accounts queries so the Portfolio reflects the new trade.

### Ideas page — the practice hub
- **`RecoCard`** gains a **"Paper trade"** button next to "Apply". Clicking opens an inline **guided confirm** (local state): shows the legs + copy *"This places N risk-free paper orders into your Practice account so you can watch how the trade behaves."* + **[Place paper trade]** / **[Cancel]**.
- The Ideas page owns the `usePaperTradeStrategy` mutation and a `paperKey` (which template is being traded). On confirm it `buildTemplate(reco.template_key, {underlying, expiry: defaultExpiry(), atm_strike: last_close})` → runs the mutation. The card shows, for its key: `idle` → button; `pending` → "Placing…"; `done` → *"Placed P/N legs ✓ — View in Portfolio →"* (a react-router `<Link to="/portfolio">`), with a note if any leg was rejected.

### Strategies builder
- A **"Paper trade"** button in the analyze row (next to Analyze/Save) runs `usePaperTradeStrategy(config)` on the current builder config, with the same confirm + result line (e.g. above the buttons). Reuses the hook; no buildTemplate needed (config already in hand).

### Beginner guidance
- The confirm copy frames paper trading as **risk-free practice**.
- The success line links straight to `/app/portfolio` so the new positions are immediately visible.
- Regime/why context already lives on the Ideas card and the builder's analyze output.

## Error handling
- **No account / creation fails:** the hook surfaces the error; the card/builder shows *"Couldn't open a Practice account — try again."*
- **Per-leg rejects:** `place_strategy` returns each leg's status; the UI shows `placed/total` and *"k leg(s) couldn't fill (need market data)"* when `rejected > 0`. A bull call spread with no option market data therefore shows an honest partial/zero result rather than silently doing nothing.
- **Build failure (Ideas):** if `buildTemplate` fails, show the existing template-build error path; do not place anything.
- **402/entitlement:** the OMS is ungated, so no entitlement branch.

## Testing
**Backend (`tests/integration/test_oms.py` or a new `test_paper_strategy.py`):**
- `place_strategy` places one order per option/equity leg and **skips cash legs** (a covered-call config → 2 orders + 0 for any cash leg).
- The result reports `placed`/`rejected` counts and per-leg status; a leg the risk layer rejects appears as `rejected` with its code while the others stay placed.
- Idempotency: re-posting the same strategy doesn't duplicate orders (per-leg keys).

**Web:**
- `lib/oms` `placeStrategy` POSTs the right body.
- `usePaperTradeStrategy`: with no paper account it calls `createBrokerAccount('Practice')` then `placeStrategy`; with one it reuses it.
- `RecoCard`: "Paper trade" → confirm → "Place" fires the handler; pending/done/partial states render; the done state links to Portfolio.
- `Strategies`: the Paper-trade button places the current config (mocked hook) and shows the result.

## Out of scope (deferred)
- **Strategy-grouped positions + live P&L** in the Portfolio (slice 3). Since legs here are placed un-grouped (no `strategy_id`), grouping will need its own mechanism — either a lightweight paper-trade batch id persisted on the orders, or the full "save → backtest → promote to paper" FSM path for serious strategies. Deferred.
- A separate `/app/practice` wizard (the Ideas page is the hub for now).
- Limit/stop order types for legs (market only), and editing legs before placing (use the builder for that).
- Live (non-paper) strategy placement — Practice/paper only here.

## Build sequence (for the plan)
1. Backend: `LegSpec`/`StrategyOrderCreate` schemas + `service.place_strategy` + router + tests.
2. Web client: `lib/oms.placeStrategy` + types.
3. `usePaperTradeStrategy` hook (ensure-account → placeStrategy) + test.
4. `RecoCard` Paper-trade + confirm + result; Ideas wiring (buildTemplate → mutation, per-card state) + tests.
5. Strategies builder Paper-trade button + test.
6. Gate: python (oms) + web typecheck/lint/test/build; live smoke (paper-trade a SPY bull call spread → see orders/positions).
