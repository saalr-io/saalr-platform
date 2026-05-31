# Backtest async API + queue (8b) — design

**Date:** 2026-05-31
**Slice:** LLD §13 step 8 — backtest, sub-slice **8b**: the §5.3 async API + Redis-Streams queue +
the worker consume loop. Wraps transport around the **8a** `run_backtest(sm, tenant_id, backtest_id)`
engine, which already runs a backtest by id and persists results.
**Status:** Approved design, pre-plan.
**Builds on:** 8a (`saalr_core/backtest/*`, `apps/backtest-worker` repo/service/cli), the existing
FastAPI app (`app.state.redis`, `get_principal` RLS sessions), the `Backtest` model, and the
`redis:7-alpine` already in compose.

## Purpose

Deliver the §5.3 contract: `POST /v1/strategies/{id}/backtest` returns **202 queued** immediately,
a worker runs the job off a **Redis Stream**, and `GET /v1/backtests/{id}` polls until the metrics
are ready. Backtesting is open to all authenticated tiers (no entitlement gate). Crash-safety comes
from Streams consumer-group semantics (at-least-once), which is safe because `run_backtest` is
deterministic and overwrites the row idempotently.

## Decisions (locked during brainstorming)

1. **Queue = Redis Streams + consumer group** (not a plain list): un-acked jobs from a crashed
   worker are reclaimed and reprocessed. At-least-once is safe (idempotent re-run).
2. **No tier gate** — any authenticated user can run backtests. Per-tier quotas/rate-limits are a
   separate later concern.
3. **Idempotency-Key** (optional header) dedupes client retries via a Redis `SET NX` key.
4. **Container/daemon for the consumer is out of scope** (a later ops slice, like ingest's 7); 8b
   ships the consume loop + a `consume` CLI command, tested directly via `run_consumer(once=True)`.

## Architecture

```
packages/core/saalr_core/queue/backtest_queue.py   # shared Redis-Streams helpers (API + worker)
packages/core/saalr_core/backtest/repo.py          # MOVED from the worker: Backtest-row CRUD (shared)
apps/api/saalr_api/backtests/                       # NEW API feature
  schemas.py   router.py
apps/api/saalr_api/main.py                          # register the backtests router
apps/backtest-worker/backtest_worker/
  consumer.py                                       # NEW: run_consumer + _process
  cli.py                                            # +consume subcommand
  repo.py                                           # keeps load_underlying_closes; row-CRUD now imported from core
  service.py                                        # import row-CRUD from saalr_core.backtest.repo
packages/core/pyproject.toml                        # +redis>=5
```

### Shared boundary move (targeted improvement)
The 8a row-CRUD (`create_backtest`, `get_backtest`, `mark_running`, `save_result`) moves from
`apps/backtest-worker/backtest_worker/repo.py` into **`saalr_core/backtest/repo.py`** so the API and
the worker share one tested copy. `load_underlying_closes` (a bars/compute concern) stays in the
worker's `repo.py`. The worker's `service.py` imports the row-CRUD from core. No behavior change —
the 8a integration tests must stay green.

### `saalr_core/queue/backtest_queue.py` (shared)
Redis client uses `decode_responses=True` (matches `app.state.redis`). Defaults:
`STREAM = "saalr:bt:jobs:v1"`, `GROUP = "bt-workers"`. All functions accept `stream`/`group`
overrides (tests pass a unique stream per test for isolation).
- `ensure_group(redis, stream=STREAM, group=GROUP)` — `XGROUP CREATE stream group $ MKSTREAM`,
  swallow the `BUSYGROUP` error if it already exists.
- `enqueue(redis, tenant_id, backtest_id, stream=STREAM) -> str` — `XADD stream MAXLEN~ 10000 *
  tenant_id <uuid> backtest_id <uuid>`; returns the message id.
- `consume_batch(redis, consumer, block_ms, count, stream=STREAM, group=GROUP) -> list[Job]` —
  `XREADGROUP GROUP group consumer COUNT count BLOCK block_ms STREAMS stream >`; parse to
  `Job(msg_id, tenant_id, backtest_id)` (a small dataclass). Empty list on timeout.
- `ack(redis, msg_id, stream=STREAM, group=GROUP)` — `XACK stream group msg_id` then `XDEL stream
  msg_id` (trim acked entries).
- `claim_stale(redis, consumer, min_idle_ms, count, stream=STREAM, group=GROUP) -> list[Job]` —
  `XAUTOCLAIM stream group consumer min_idle_ms 0 COUNT count`; returns reclaimed jobs (entries
  pending longer than `min_idle_ms` from a dead consumer).

## API (`apps/api/saalr_api/backtests/`)

Prefix-less router with full paths; registered in `main.py` via `app.include_router(...)`.

### `schemas.py`
`BacktestRequest(BaseModel)`: `start_date: date`, `end_date: date`, `initial_capital: float = 100000.0`,
`include_costs: bool = True`. A model validator rejects `end_date <= start_date` (422). (Pydantic
parses `date` from `YYYY-MM-DD` strings.)

> **Group-creation ordering (important):** a consumer group created with start id `$` only receives
> messages `XADD`ed *after* the group exists. So the group must exist before the first `enqueue`, or
> that first job is silently lost. Therefore the **API lifespan startup** calls `ensure_group(redis)`
> (in `main.py`, right after creating `app.state.redis`), and the worker also calls it on start. Both
> are idempotent (swallow `BUSYGROUP`).

### `POST /v1/strategies/{strategy_id}/backtest`
1. `get_principal` → `(session, principal)` (RLS tenant set).
2. Load the strategy via the existing `saalr_api.strategies.repo.get_strategy(session, strategy_id)`
   → 404 `RESOURCE_NOT_FOUND` if missing/cross-tenant. (Row creation uses
   `saalr_core.backtest.repo.create_backtest`.)
3. Read optional `Idempotency-Key` header. If present and `redis.get("saalr:idem:bt:{tenant}:{key}")`
   returns an id → load that `Backtest` row and return **202** with its *current* status + `poll_url`
   (idempotent replay; no new row, no re-enqueue).
4. Otherwise build `params = {start_date, end_date, initial_capital, include_costs}` and
   `config_snapshot = {config: strat.config_json, params, engine_version: ENGINE_VERSION}`, then
   create the row in a **separate, committed** `tenant_session(app.state.sessionmaker, tenant_id)`
   (NOT the `get_principal` session — that one commits only *after* the handler returns, so enqueuing
   on it would let the worker read the row before it exists). This mirrors 8a's `create_and_run`
   (create-commits-then-run).
5. `enqueue(redis, tenant_id, backtest_id)` — now guaranteed after the row is committed. If
   `Idempotency-Key` was supplied, `redis.set("saalr:idem:bt:{tenant}:{key}", backtest_id, nx=True,
   ex=86400)`.
6. Return **202** `{backtest_id, status:"queued", estimated_duration_seconds, poll_url:
   "/v1/backtests/{backtest_id}"}`. `estimated_duration_seconds = min(120, max(5, (end-start).days //
   7))`.

If `enqueue` raises (Redis down), return **503** `BACKTEST_ENQUEUE_FAILED` — the row stays `queued`
and is reclaimable later (documented; a requeue tool is a follow-up).

### `GET /v1/backtests/{backtest_id}`
`get_principal` → RLS read via `get_backtest`. 404 if missing/cross-tenant. Map:
- `queued` / `running` → `{backtest_id, status}`.
- `succeeded` → `{backtest_id, status, metrics: metrics_json["metrics"], trade_log_url: null}`.
- `failed` → `{backtest_id, status, error: {code: "BACKTEST_FAILED", message: error_message}}`.

## Worker consumer (`apps/backtest-worker/backtest_worker/`)

### `consumer.py`
- `run_consumer(redis, sessionmaker, consumer, block_ms=5000, count=10, once=False,
  claim_min_idle_ms=60000)`:
  1. `ensure_group(redis)`.
  2. Reclaim + process any prior-crash pending: `claim_stale(...)` → `_process` each.
  3. Loop: `jobs = consume_batch(redis, consumer, block_ms, count)`; `_process` each; `ack`.
     `once=True` → after step 2, do exactly one `consume_batch` pass then return (deterministic for
     tests).
- `_process(redis, sessionmaker, job)`:
  ```
  try:
      await run_backtest(sessionmaker, job.tenant_id, job.backtest_id)
  except Exception:           # poison guard: a job whose row is gone, or an unexpected error
      log.exception(...)      # run_backtest already persists 'failed' for in-pipeline errors
  finally:
      await ack(redis, job.msg_id)
  ```
  Crash *before* `ack` (process dies) → the entry stays pending → reclaimed by `claim_stale` on the
  next start/tick. This is the crash-safety guarantee.

### `cli.py` — `consume` subcommand
`consume [--block-ms 5000] [--count 10] [--once] [--consumer <name>]`. Builds a
`redis.asyncio.from_url(settings.redis_url, decode_responses=True)` client + a sessionmaker, then
runs `run_consumer`. Default `--consumer` = a stable name (e.g. `f"bt-{socket.gethostname()}"`).

## Error handling summary
- POST: strategy not found → 404; `end_date <= start_date` → 422; Redis enqueue failure → 503;
  duplicate Idempotency-Key → 202 replay of the existing row.
- GET: missing / cross-tenant → 404 (RLS yields no row).
- Consumer: in-pipeline failures are persisted `failed` by `run_backtest`; unexpected/poison jobs are
  logged and acked (no infinite redelivery); worker crash before ack → reclaimed via `claim_stale`.

## Testing
- **Queue** (`tests/integration/test_backtest_queue.py`, real Redis via `REDIS_URL`, a unique stream
  key per test): `ensure_group` is idempotent (second call no-ops, no BUSYGROUP leak); `enqueue` →
  `consume_batch` returns the `Job` with the right tenant/backtest ids; `ack` empties `XPENDING`;
  `claim_stale` reclaims an un-acked entry once it exceeds `min_idle_ms` (use `min_idle_ms=0` to
  force) and a fresh entry is NOT reclaimed by a second consumer before timeout.
- **API + worker end-to-end** (`tests/integration/test_backtest_api.py`, 55432 + Redis): seed a tenant
  (dev auth) + strategy + `bars` (reuse the 8a seeding helpers); `POST` → 202 with `poll_url`; `GET`
  → `queued`; run `run_consumer(once=True)`; `GET` → `succeeded` with a `metrics` block containing the
  §5.3 keys and `trade_log_url: null`. Plus: **idempotency** (two POSTs with the same
  `Idempotency-Key` → identical `backtest_id`, exactly one row); **RLS** (a second tenant GETting the
  first tenant's `backtest_id` → 404); **validation** (`end_date <= start_date` → 422); **failed
  path** (strategy whose underlying has no bars → consumer runs → `GET` → `failed` + error).
- **Unit:** the `estimated_duration_seconds` heuristic; the `BacktestRequest` date validator.
- **Gate:** the end-to-end test imports both `saalr_api` and `backtest_worker.consumer`, so the suite
  runs under `uv run --package saalr-backtest-worker pytest …` against the 55432 DB + Redis; plus the
  core suite and `uvx ruff check`. The 8a backtest integration + ingest integration tests must stay
  green after the row-CRUD move.

## Out of scope (later)
- Containerizing/daemonizing the consumer (ops slice). The §5.3 `/v1/backtests/{id}/trades`
  trade-log endpoint (8a stores no per-trade log; `trade_log_url` is null). Per-tier quotas /
  rate-limiting. A dead-letter stream beyond `claim_stale`. Websocket/SSE push (polling only, per
  §5.3). A standalone requeue tool for orphaned `queued` rows.
