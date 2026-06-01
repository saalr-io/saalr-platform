# Alpaca OMS wiring + reconciliation (OMS-3b) — design

**Date:** 2026-06-01
**Slice:** LLD §13 step 12 / §6 — Alpaca live/paper trading. Sub-slice **OMS-3b** (wire the OMS-3a
adapter into the order path + a reconciliation worker). OMS-4 (live-promotion MFA + 14-day gate) is next.
**Status:** Approved design, pre-plan.
**Builds on:** OMS-3a `AlpacaAdapter` (`saalr_brokers.alpaca`, alpaca-py optional extra, lazy-imported);
the OMS-2 `place_order`/`cancel_order` service + `saalr_api/oms/repo.py`; the `BrokerAccount`/`Order`/
`Execution`/`Position` models; the worker pattern from ingest/backtest/ml workers (per-row transaction,
`--once` CLI, shared row-CRUD living in `saalr_core` so the worker never depends on `saalr-api`).

## Purpose

Make `broker='alpaca'` work end-to-end: a `POST /v1/orders` against an alpaca `broker_account` resolves
credentials, submits to Alpaca, and **rests `submitted`** (Alpaca fills are asynchronous); a separate
reconciliation worker polls Alpaca, persists executions + positions, advances order status, and stamps
`last_reconciled_at`. One OMS path serves paper + live; only the adapter differs.

## No schema change

`'alpaca'` is already in `broker_accounts_broker_check` (migration `0005`); `broker_accounts` already has
`credential_ref` (Text, not null) and `last_reconciled_at` (TIMESTAMPTZ, nullable). OMS-3b adds **no
migration**.

## Decisions (locked during brainstorming)

1. **Env-prefix credential resolver.** A `CredentialResolver` protocol; `EnvCredentialResolver` reads a
   `credential_ref` like `"env:ALPACA_PAPER"` and resolves `ALPACA_PAPER_KEY` / `ALPACA_PAPER_SECRET` from
   an env mapping. `is_paper` comes from the account row. No secrets in the DB; a `SecretsManagerResolver`
   can replace the env impl later with no call-site change. Supports more than one named credential.
2. **Dedicated worker app.** `apps/oms-worker` (sibling of ingest/backtest/ml workers) holds the loop
   driver + CLI and carries the `saalr-brokers[alpaca]` dependency. The reconcile **logic** lives in
   `saalr_core/oms/reconcile.py` (alpaca-free, called with a real DB session + an injected adapter).
3. **Positions derived from observed fills.** Reconcile computes the fill delta from each order's
   `filled_qty`/`filled_avg_price`, inserts a synthetic execution for the delta (idempotent
   `broker_execution_id`), and recomputes the position via `net_position` — identical to the paper path.
   `account_balance` keeps working off executions. Alpaca's `get_positions` snapshot is NOT the source of
   truth (avoids two divergent position models).
4. **Buying-power from the broker.** On the alpaca path the BP gate uses `adapter.get_account_balance()`
   (real buying power), not the paper executions formula.
5. **`stream_executions` stays deferred** (still `NotImplementedError`); reconciliation is poll-only.

## Two cross-cutting structural choices (from spec self-review)

- **Shared OMS row-CRUD moves into `saalr_core/oms/repo.py`.** The functions reconcile needs (and that
  `place_order` already uses) — `get_position`, `upsert_position`, `insert_execution`, `update_order`,
  `write_audit`, plus new `sum_executed_qty`, `list_open_orders_for_account`, `list_active_alpaca_accounts`
  — live in `saalr_core/oms/repo.py`. `saalr_api/oms/repo.py` **re-exports** them (behaviour-neutral; the
  API keeps its broker-account/order-listing/`account_balance` helpers). The worker then depends only on
  `saalr-core` + `saalr-brokers[alpaca]`, never on `saalr-api` (mirrors the backtest-worker refactor).
- **Adapter construction is an injectable factory, so the default test gate stays alpaca-free.** The API
  resolves the alpaca adapter via `request.app.state.alpaca_adapter_factory` (default = the real
  `build_alpaca_adapter`); tests override it with a stub-adapter factory (same pattern as
  `app.state.market_provider`). `alpaca-py` therefore reaches `saalr-api` ONLY as an optional extra at
  deploy time — it is NOT a root dependency, so `uv run pytest` never installs it and the OMS-3a
  `importorskip` tests keep skipping.

## Architecture

```
packages/brokers/saalr_brokers/credentials.py    # CredentialResolver, EnvCredentialResolver, CredentialError,
                                                  #   build_alpaca_adapter(credential_ref, is_paper, resolver)
packages/core/saalr_core/oms/repo.py             # shared OMS row-CRUD (moved here) + reconcile queries
packages/core/saalr_core/oms/reconcile.py        # reconcile_account(session, adapter, account, *, now) — alpaca-free
apps/api/saalr_api/oms/repo.py                   # MODIFY: re-export core repo fns; keep api-only helpers
apps/api/saalr_api/oms/service.py                # MODIFY place_order + cancel_order: route broker=='alpaca'
apps/api/saalr_api/main.py                        # MODIFY: app.state.alpaca_adapter_factory = build (default)
apps/oms-worker/oms_worker/{reconcile.py,cli.py,__main__.py}  # loop driver + CLI
apps/oms-worker/{pyproject.toml,tests/}          # saalr-core + saalr-brokers[alpaca]; CLI --once smoke
docs/runbooks/oms-reconcile.md                   # runbook
```

### `credentials.py` (in saalr-brokers, alpaca-free at import)
- `class CredentialError(Exception)` — malformed ref or missing env keys (never carries the values).
- `class CredentialResolver(Protocol): def resolve(self, credential_ref: str, is_paper: bool) -> tuple[str, str]`.
- `class EnvCredentialResolver`: constructed with an env mapping (e.g. `os.environ` or a settings-derived
  dict). `resolve("env:ALPACA_PAPER", is_paper)`: requires the `"env:"` prefix (else `CredentialError`);
  the suffix is the env-var prefix → reads `{PREFIX}_KEY` and `{PREFIX}_SECRET` (missing → `CredentialError`).
  The `paper`-vs-`live` distinction is encoded by convention in the ref (`ALPACA_PAPER` vs `ALPACA_LIVE`);
  `is_paper` is passed through to the adapter, not used to alter the lookup.
- `def build_alpaca_adapter(credential_ref, is_paper, resolver) -> AlpacaAdapter`: `key, secret =
  resolver.resolve(credential_ref, is_paper)`; `return AlpacaAdapter(key, secret, is_paper=is_paper)`.
  `AlpacaAdapter.__init__` does not import alpaca (lazy in `_trading()`), so building the adapter is
  SDK-free; the SDK is needed only when a method actually calls Alpaca.

### `apps/api/saalr_api/main.py`
- At app construction set `app.state.alpaca_adapter_factory = lambda account: build_alpaca_adapter(
  account.credential_ref, account.is_paper, EnvCredentialResolver(_alpaca_env(settings)))`, where
  `_alpaca_env` returns the alpaca-prefixed keys from settings/`os.environ`. Tests overwrite
  `app.state.alpaca_adapter_factory` with a factory returning a stub adapter.

### `place_order` changes (`service.py`)
Branch on `account.broker`:
- **`'paper'`** — unchanged (synchronous deterministic fill).
- **`'alpaca'`** (branch taken BEFORE the existing dead `400 BROKER_NOT_SUPPORTED`, so an alpaca order
  never leaves an orphaned `pending` row):
  1. `adapter = request.app.state.alpaca_adapter_factory(account)`; on `CredentialError` →
     `502 BROKER_CREDENTIALS_UNAVAILABLE` (no key values echoed). (`request`/the factory is threaded into
     `place_order`; today it takes `request_id` — it will also receive the factory or the `app` state.)
  2. **Buying-power:** `balance = await adapter.get_account_balance()`. `estimate_cost(req, mark)` still
     uses `model_mark`; if `model_mark` raised `NoMarketData`, set `est_cost = Decimal(0)` (Alpaca enforces
     BP server-side — a missing model mark must not block a live broker). Run the existing gates with this
     `balance`/`est_cost`. (`model_mark` is wrapped so `NoMarketData` on the alpaca path does NOT
     short-circuit to a rejected order the way it does for paper.)
  3. Insert `pending` (existing idempotency-race handling unchanged).
  4. `result = await adapter.submit_order(broker_order, idempotency_key or str(order.order_id))`. On
     `BrokerError` → `502 BROKER_UNAVAILABLE` (order left `pending`, retriable).
  5. `result.status == 'rejected'` → FSM `pending→rejected`, `update_order(status='rejected',
     reject_reason_code='BROKER_REJECTED')`, audit `order.rejected`, raise `422 BROKER_REJECTED` with the
     broker's reason. Else → FSM `pending→submitted`, `update_order(status='submitted',
     broker_order_id=result.broker_order_id, submitted_at=now)`, audit `order.submitted`. **No execution
     insert** — the order rests `submitted`; reconciliation fills it later. Return `submitted`.
- **other brokers** — unchanged `400 BROKER_NOT_SUPPORTED`.

### `cancel_order` changes (`service.py`)
After the local cancellable check, load the account via `order.broker_account_id`; if
`account.broker == 'alpaca'` and `order.broker_order_id`, call
`request.app.state.alpaca_adapter_factory(account).cancel_order(order.broker_order_id)` (best-effort,
returns bool — a `False`/error is logged, not fatal). Then mark local `cancelled` + audit (reconciliation
confirms the terminal state on the next pass). Paper stays local-only.

### `reconcile.py` (in `saalr_core/oms`, alpaca-free)
`async def reconcile_account(session, adapter, account, *, lookback_buffer_seconds=300, now) -> dict`
returns a summary `{matched, filled, partial, cancelled, rejected}` (for logging/tests):
1. `open_orders = await repo.list_open_orders_for_account(session, account.broker_account_id)`
   (`status in ('submitted','partial')`). If empty → stamp `account.last_reconciled_at = now`, return zeros.
2. `since = min(o.submitted_at for o in open_orders) - timedelta(seconds=lookback_buffer_seconds)`;
   `rows = await adapter.get_orders(since)`; `by_id = {r['broker_order_id']: r for r in rows}`. (Driving
   off local-open orders + a covering lookback avoids Alpaca's `after`-filters-by-submit-time gap.)
3. For each open order with a matching `row` (by `order.broker_order_id`):
   - **Fill delta:** `observed = row['filled_qty']`; `recorded = await repo.sum_executed_qty(session,
     order.order_id)`; `delta = observed - recorded`. If `delta > 0` and `row['filled_avg_price'] is not
     None`: `repo.insert_execution(..., qty=delta, price=row['filled_avg_price'], commission=0,
     broker_execution_id=f"recon:{order.order_id}:{observed}")` (idempotent at each cumulative fill level);
     then `net_position(...)` over `repo.get_position`/`repo.upsert_position`, signed by `order.side`.
   - **Status:** `new = row['status']` (already mapped by the adapter). If `new != order.status` and the
     FSM permits, `transition(...)`, `repo.update_order(status=new, filled_at=now if new=='filled')`, and
     `repo.write_audit('order.'+new, ...)`.
4. Stamp `account.last_reconciled_at = now`; return the summary.

### Worker `apps/oms-worker`
- `oms_worker/reconcile.py`: `run_reconcile(sessionmaker, adapter_factory, *, market, once, interval)` —
  each pass: `accounts = list_active_alpaca_accounts(...)`; for each, open **one transaction per account**,
  `adapter = adapter_factory(account)`, `await reconcile_account(session, adapter, account, now=...)`,
  commit; per-account `try/except` logs + continues (crash isolation). `once=True` → one pass; else
  `await asyncio.sleep(interval)` between passes. `adapter_factory` defaults to `build_alpaca_adapter` via
  an `EnvCredentialResolver(os.environ)`; tests pass a stub factory.
- `oms_worker/cli.py`: `reconcile [--market US] [--interval 5] [--once]`; lazy-imports the alpaca-touching
  bits inside the command so `build_parser` stays import-light (mirrors ml-worker). `__main__.py` wires it.
- `pyproject.toml`: deps `saalr-core`, `saalr-brokers[alpaca]`, `sqlalchemy`, `asyncpg`; a `dev` group with
  `pytest` (like ml-worker). NOT a root dep — `uv run pytest` never pulls alpaca; worker tests run via
  `uv run --package saalr-oms-worker pytest apps/oms-worker/tests`.

## Error handling

| Condition | Result |
|---|---|
| `credential_ref` malformed / env keys missing | `place_order` → `502 BROKER_CREDENTIALS_UNAVAILABLE` (no key values echoed) |
| Alpaca SDK/transport error at submit | `502 BROKER_UNAVAILABLE`; order left `pending` (retriable) |
| Alpaca returns `rejected` | order `rejected`, `reject_reason_code='BROKER_REJECTED'`; `422 BROKER_REJECTED` w/ broker reason |
| `model_mark` `NoMarketData` on alpaca path | `est_cost=0`, submit proceeds (broker enforces BP) — NOT a rejected order |
| reconcile error for one account | logged, that account skipped; loop continues; other accounts + next pass unaffected |
| re-poll same fill level | synthetic `broker_execution_id` collision → no-op (idempotent) |

## Testing

- **Default gate (no alpaca install)** — `uv run pytest`:
  - `EnvCredentialResolver`: `"env:ALPACA_PAPER"` → keys; missing `"env:"` prefix → `CredentialError`;
    missing key → `CredentialError`. (`build_alpaca_adapter` constructs an `AlpacaAdapter` without importing
    alpaca — assert it returns an adapter whose `_is_paper` matches.)
  - `reconcile_account` (integration: real DB session on 55432 + a **stub adapter** returning canned
    `get_orders` rows): partial fill → one delta execution + position + `partial`; a second pass at the
    same `filled_qty` → no new execution (idempotent); full fill → `filled` + `filled_at`;
    `cancelled`/`rejected` mapping; no-open-orders → only stamps `last_reconciled_at`.
  - `place_order` alpaca path (integration + `app.state.alpaca_adapter_factory` = stub): rests `submitted`
    (no execution), `rejected` → 422, `CredentialError` → 502, `BrokerError` → 502 + order stays `pending`;
    BP uses the stub's `get_account_balance`. A paper order is unaffected (regression).
- **Worker** — `uv run --package saalr-oms-worker pytest apps/oms-worker/tests`: `run_reconcile(once=True)`
  with a stub `adapter_factory` over a real DB drives `reconcile_account` + commits; a torch/alpaca-free
  `build_parser` test.
- **Live smoke (opt-in)** — env-gated `ALPACA_PAPER_KEY`/`SECRET`: submit a tiny paper order, run one
  reconcile pass, assert status advances. Deferred/optional (documented in the runbook).
- `uvx ruff check`.

## Out of scope (→ OMS-4 / later)
- Live-promotion MFA + 14-day paper gate (OMS-4); the real `stream_executions` trade-update websocket
  (still polling); multi-leg combo orders + Alpaca options entitlement; IBKR/Zerodha/AngelOne adapters;
  worker containerization + scheduling (ops slice, like ingest-worker 7); a `SecretsManagerResolver`
  (the interface is here; the AWS impl needs the AWS-foundation slice).
