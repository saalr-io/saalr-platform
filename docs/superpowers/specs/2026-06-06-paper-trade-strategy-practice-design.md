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
- Orders are tagged with a shared **`strategy_id`** (the `OrderCreate` field already exists) so the deferred grouped-P&L view is a clean follow-up.

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
       one shared strategy_id → for each option/equity leg → service.place_order (risk + fill)
       skip cash legs → collect per-leg {status, reject_code}
                              │
   result: { strategy_id, results[], placed, rejected } → "placed 2/2 → view in Portfolio →"
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
async def place_strategy(session, principal, body: StrategyOrderCreate, request_id, factory) -> dict
```
- Generate one `strategy_id = str(new_id())`.
- For each leg, in order:
  - `cash` → skip (collateral, not an order); record `{kind:"cash", status:"skipped"}`.
  - `option` → `OrderCreate(broker_account_id, symbol=underlying, side, qty, order_type="market", option_type, strike, expiry, strategy_id, time_in_force="day")`.
  - `equity` → `OrderCreate(broker_account_id, symbol=underlying, side, qty, order_type="market", strategy_id)`.
  - Call the existing `service.place_order(session, principal, order, idempotency_key=f"{strategy_id}:{i}", request_id, factory)`; capture `{leg_index:i, kind, status, order_id?, reject_code?}` from its result.
- Return `{ "strategy_id": strategy_id, "broker_account_id": ..., "results": [...], "placed": <# legs whose status is not "rejected" and not "skipped">, "rejected": <# legs with status "rejected"> }`.
- Per-leg idempotency keys make a whole-strategy retry safe.
- It composes `place_order` per leg, so **all existing risk checks and paper fills apply unchanged**; a rejected leg (e.g. `RISK_NO_MARKET_DATA`) is reported, not hidden.

### Router (`router.py`)
```python
@router.post("/v1/orders/strategy")
async def place_strategy(body: StrategyOrderCreate, request: Request,
                         ctx=Depends(get_principal)) -> dict:
    session, principal = ctx
    factory = getattr(request.app.state, "alpaca_adapter_factory", None)
    return await service.place_strategy(session, principal, body, _request_id(request), factory)
```
Ungated like the rest of the OMS (auth-only). No DB migration (reuses `orders`/`positions`; `strategy_id` column already exists on orders).

## Frontend

### Client (`apps/web/src/lib/oms.ts`)
- Types: `StrategyLeg` (kind/side/qty/option_type/strike/expiry/amount), `StrategyOrderResult { strategy_id; results: { leg_index:number; kind:string; status:string; order_id?:string; reject_code?:string }[]; placed:number; rejected:number }`.
- `placeStrategy(body: { broker_account_id, underlying, legs }): Promise<StrategyOrderResult>` → `POST /v1/orders/strategy`.

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
- `place_strategy` places one order per option/equity leg, **skips cash legs**, and all placed orders share one `strategy_id`.
- The result reports `placed`/`rejected` counts and per-leg status; a leg that the risk layer rejects appears as `rejected` with its code (others still placed).
- Idempotency: re-posting the same strategy doesn't duplicate orders (per-leg keys).

**Web:**
- `lib/oms` `placeStrategy` POSTs the right body.
- `usePaperTradeStrategy`: with no paper account it calls `createBrokerAccount('Practice')` then `placeStrategy`; with one it reuses it.
- `RecoCard`: "Paper trade" → confirm → "Place" fires the handler; pending/done/partial states render; the done state links to Portfolio.
- `Strategies`: the Paper-trade button places the current config (mocked hook) and shows the result.

## Out of scope (deferred)
- **Strategy-grouped positions + live P&L** in the Portfolio (slice 3) — the shared `strategy_id` tag makes it a clean follow-up.
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
