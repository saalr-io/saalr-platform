# RA-2 — Async research runs (design)

**Status:** approved 2026-06-02
**Slice:** RA-2 (second sub-slice of the Research Agent band; LLD §13 step 17 / HLD §9)
**Builds on:** RA-1 (`docs/superpowers/specs/2026-06-02-research-note-core-design.md` — the synchronous `POST /research/run` note core) and the backtest-async pattern (slice 8b: Redis Streams + consumer group + 202/poll).

## Goal

Convert research-note generation from synchronous to **asynchronous**: `POST /research/run` enqueues a job and returns `202`; a dedicated **research-agent worker** generates the note; the client **polls** for the result. Add a **per-tenant daily rate limit** (10 runs / UTC-day). Premium-gated via the existing `research_agent` entitlement. Reuse the proven backtest-async machinery (Redis Streams, consumer group, claim-stale crash recovery, 3-phase load/compute/persist).

This is the lightweight, single-LLM-call ancestor of the deferred HLD §9 multi-agent Research Agent (LangGraph fan-out, multi-provider fallback + budgets, S3 transcripts are RA-3).

## Approved decisions

1. **Async shape — replace, don't duplicate.** `POST /research/run` returns `202` (or `200` on a cache hit) and enqueues; note generation **moves out of `apps/api` into the research-agent worker**. One code path, mirrors backtest 1:1. RA-1's synchronous integration tests are rewritten for the async shape.
2. **Run record — augment `research_notes`.** Add a `status` lifecycle (`queued → running → succeeded/failed`) + `error_message` to the existing table (migration 0009) and `GRANT UPDATE`; one row = one run, mutated through its lifecycle. RA-1's INSERT-only/immutable decision is superseded (async needs lifecycle mutation). Mirrors the `backtests` table.
3. **Rate limit — DB count, 10 / UTC-day.** At enqueue, count the tenant's non-`failed` runs created since UTC-midnight; `≥10 → 429`. No new infra; failed runs do not burn quota.
4. **6h cache — kept as a pre-enqueue fast path.** A `succeeded` note `<6h` old for `(ticker, market)` → return it immediately (`200`, `cached:true`) without enqueuing or burning quota. `refresh=true` bypasses it.

## Request lifecycle

`POST /research/run {ticker, market="US", refresh=False}` → dependency `require_research_agent` (Premium; `402 ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM` for free **and** pro). Then:

1. **Validate** — `ticker.strip().upper()` must be non-empty `isalpha`; `market` must be `"US"`; else `400 VALIDATION_INVALID_PARAMETER`.
2. **6h cache fast-path** (skipped when `refresh=true`) — `recent_succeeded_note(session, ticker, market, since=now-6h)`; hit → **`200`** `_out(note, cached=True)` (the full RA-1 note shape). No queue, no quota.
3. **In-flight dedup** — `in_flight_run(session, ticker, market)` finds a `queued`/`running` row → return **`202`** `_accepted(existing.note_id, "queued")`. Prevents duplicate concurrent runs (replaces backtest's `Idempotency-Key` header — research dedups naturally by ticker). `refresh=true` does **not** bypass this (a fresh run is already in flight).
4. **Rate limit** — `count_runs_today(session, tenant_id) >= 10` → **`429`** `RATE_LIMIT_RESEARCH_DAILY_EXCEEDED` (message names the limit; counts non-`failed` runs since UTC-midnight).
5. **Create + enqueue** — create a `status='queued'` row in its **own committed `tenant_session`** (before enqueue, so the worker cannot read a row that does not yet exist — the backtest ordering invariant) → `enqueue(redis, tenant_id, note_id)`. Enqueue failure → **`503`** `RESEARCH_ENQUEUE_FAILED` (the row stays `queued` and is reclaimable). → **`202`** `_accepted(note_id, "queued")`.

`_accepted(note_id, status)` = `{"note_id": str, "status": status, "poll_url": f"/research/notes/{note_id}"}`.

### Worker

`run_research_job(sessionmaker, tenant_id, note_id, *, chat_provider, embedding_provider, catalog)` — 3 phases, each fault-isolated like `run_backtest`:

1. **Load + mark running** (`tenant_session`): load the row; if missing or not `queued`/`running`, return (idempotent — a re-delivered job that already finished is a no-op). `mark_running(note_id)`.
2. **Compute** (no DB writes): `gather_inputs(session_for_reads, ...)` — load closes (no bars → raise `NoPriceData`), spot, GARCH (≥250 closes, best-effort), sentiment, RAG excerpts (best-effort) — then `build_research_prompt` → `chat_provider.complete` → `estimate_cost`. (Reads use a read `tenant_session`; the compute itself is provider calls.)
3. **Persist** (fresh `tenant_session`): `save_succeeded(note_id, summary, signals, sources, model, prompt_tokens, completion_tokens, cost_usd)`.

On any exception in phases 1–2, persist failure in a **fresh** `tenant_session` so a read error cannot poison the failure write: `save_failed(note_id, code, message)` where `code ∈ {RESEARCH_NO_PRICE_DATA, RESEARCH_LLM_UNAVAILABLE, RESEARCH_GENERATION_FAILED}` (no-bars → `NO_PRICE_DATA`; `ChatError`/`EmbeddingError` → `LLM_UNAVAILABLE`; anything else → `GENERATION_FAILED`). Graceful signal degradation (GARCH/sentiment/RAG missing → `null`/`[]`) carries over from RA-1 unchanged — only no-price-bars and a hard LLM failure fail the run.

### Poll

`GET /research/notes/{note_id}` (status-aware; RLS-scoped, `404 RESOURCE_NOT_FOUND` if not the tenant's):
- `queued` / `running` → `{note_id, status}`.
- `succeeded` → the full RA-1 note body (`note_id, ticker, market, summary, signals, sources, model, usage:{prompt_tokens, completion_tokens}, cost_usd, status:"succeeded", created_at`).
- `failed` → `{note_id, status:"failed", error:{code, message}}`.

`GET /research/notes` (history) — list **succeeded** notes only (`status='succeeded'`), keyset cursor (base64 `created_at|note_id`), `limit: Query(20, ge=1, le=100)`. Each row: `{note_id, ticker, market, model, cost_usd, created_at}`.

## Data model — migration 0009

```sql
ALTER TABLE research_notes ADD COLUMN status TEXT NOT NULL DEFAULT 'succeeded'
  CHECK (status IN ('queued','running','succeeded','failed'));
ALTER TABLE research_notes ADD COLUMN error_message TEXT;
ALTER TABLE research_notes
  ALTER COLUMN summary           DROP NOT NULL,
  ALTER COLUMN signals_json      DROP NOT NULL,
  ALTER COLUMN sources_json      DROP NOT NULL,
  ALTER COLUMN model             DROP NOT NULL,
  ALTER COLUMN prompt_tokens     DROP NOT NULL,
  ALTER COLUMN completion_tokens DROP NOT NULL,
  ALTER COLUMN cost_usd          DROP NOT NULL;
GRANT UPDATE ON research_notes TO saalr_app;
CREATE INDEX idx_research_notes_tenant_created ON research_notes(tenant_id, created_at DESC);
```

- `status` default `'succeeded'` keeps any pre-existing RA-1 rows valid; the async create path sets `'queued'` explicitly.
- `down_revision = "0008"`. Downgrade drops the new index, `status`, `error_message`, and the UPDATE grant; it does **not** re-add the `NOT NULL` constraints (rows with nulls may exist) — documented as a one-way nullability relaxation.
- `ResearchNote` model gains `status: str` and `error_message: str | None`, and the seven columns become `| None`. `test_schema_matches_models` enforces the new column-name set.

## Code layout

Mirrors backtest's core/worker split (slice 8b): shared queue + row-CRUD + the closes loader live in `saalr-core`; the generation orchestration lives in the worker; the API only enqueues + polls.

- **`saalr_core/queue/research_queue.py`** — parallel to `backtest_queue.py`: `STREAM = "saalr:research:jobs:v1"`, `GROUP = "research-workers"`, `Job(msg_id, tenant_id, note_id)`, `ensure_group / enqueue(redis, tenant_id, note_id) / consume_batch / ack / claim_stale`. Accepted small duplication of the queue primitives for slice isolation (a future refactor could generalize both domains over a shared stream helper).
- **`saalr_core/research/repo.py`** (NEW) — RA-1's note CRUD **moves here** + new fns: `create_queued_run(session, *, tenant_id, user_id, ticker, market) -> note_id`, `mark_running`, `save_succeeded(...)`, `save_failed(note_id, code, message)`, `recent_succeeded_note(session, ticker, market, since)`, `in_flight_run(session, ticker, market)`, `count_runs_today(session, tenant_id, since)`, `list_succeeded_notes(session, limit, cursor)`, `get_note(session, note_id)`. The API's `apps/api/saalr_api/research/repo.py` re-exports them (behaviour-neutral move).
- **`saalr_core/marketdata/bars.py`** (NEW) — `load_closes(session, symbol, market, lookback_days=900)` **moves here** (raw-SQL read of the non-RLS `bars`); `apps/api/saalr_api/forecast/repo.py` re-exports it so the worker (which must not depend on `apps/api`) shares one copy. `load_closes` has no `saalr-ml` dependency, so it lives cleanly in core. Forecast + Monte-Carlo behaviour is unchanged.
- **`apps/research-agent/`** (the empty slice-1 stub, now real) — deps `saalr-core[openai] + saalr-ml + saalr-content` (so `openai`/`torch` stay out of the default root env; the worker env is the only place the real OpenAI path runs):
  - `research_agent/service.py` — `run_research_job(...)` (3-phase) + `gather_inputs(...)` (moved out of the API; imports `load_closes` from core, `vol_forecast` from saalr-ml, `latest_sentiment` + `retrieve_context` + `build_research_prompt`/`estimate_cost` from core). Providers + catalog are **injected** (real ones built by the consumer from env; tests pass stubs).
  - `research_agent/consumer.py` — `run_consumer(redis, sessionmaker, consumer, *, chat_provider, embedding_provider, catalog, block_ms, count, once, claim_min_idle_ms)` mirroring backtest: `ensure_group` → `claim_stale` reprocess → loop `consume_batch` → `_process` → `ack` in `finally`. Built once with real providers at startup.
  - `research_agent/cli.py` — `consume [--once] [--interval]` (lazy-imports the run loop + provider construction to keep `build_parser` import-light/torch-free) + `__main__.py`.
  - `research_agent/repo.py` — re-exports the core `load_closes` + research CRUD it uses (so the worker imports only saalr-core/ml/content, never apps/api). Own `pyproject` `[tool.pytest.ini_options] asyncio_mode="auto"` + httpx/pytest dev-deps (self-contained, like oms-worker).
- **`apps/api/saalr_api/research/`** — `service.py` shrinks to the enqueue path (`run = cache → in-flight → rate-limit → create → enqueue`); generation code is deleted (moved to the worker). `router.py` updates the three endpoints. `main.py` calls research-stream `ensure_group` at lifespan startup (the `$`-start group must exist before any `XADD`, exactly like backtest).

## Error handling & edge cases

| Case | Where | Result |
|------|-------|--------|
| free / pro tier | API gate | `402 ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM` |
| bad ticker / market | API validation | `400 VALIDATION_INVALID_PARAMETER` |
| ≥10 runs today | API rate limit | `429 RATE_LIMIT_RESEARCH_DAILY_EXCEEDED` |
| enqueue fails | API | `503 RESEARCH_ENQUEUE_FAILED` (row reclaimable) |
| in-flight run exists | API | `202` with the existing `note_id` (no dup) |
| fresh succeeded note <6h | API | `200 cached:true` (no queue, no quota) |
| no price bars | worker | `save_failed(RESEARCH_NO_PRICE_DATA)` → poll `failed` |
| chat/embeddings down | worker | `save_failed(RESEARCH_LLM_UNAVAILABLE)` → poll `failed` |
| unexpected error | worker | `save_failed(RESEARCH_GENERATION_FAILED)` |
| poll unknown id / other tenant | API | `404 RESOURCE_NOT_FOUND` (RLS-scoped) |

- **Failure ≠ quota burn:** `count_runs_today` excludes `status='failed'`, so a worker failure or a typo'd ticker frees the slot once it fails.
- **Crash safety (from the backtest playbook):** `claim_stale` reclaims pending jobs after `claim_min_idle_ms`; `_process` acks in `finally` (poison guard — a job that always fails is not redelivered forever); `save_succeeded`/`save_failed`/`mark_running` are no-ops if the row vanished; at-least-once delivery is safe because `run_research_job` is idempotent (phase-1 guard: a re-delivered job whose row is already `succeeded`/`failed` returns without regenerating).
- **No bars checked at enqueue:** the API stays thin; a typo'd ticker costs one queue cycle (but not quota, since the resulting `failed` run is excluded from the count).
- **Error shape** is the project standard everywhere: `HTTPException(status, {"error": {"code", "message"}})` → `resp.json()["detail"]["error"]["code"]`. No global exception handler (the OMS-2 lesson).

## Testing

- **Pure / unit:** `research_queue` `_parse`; `count_runs_today` UTC-midnight boundary; status-mapping in the poll serializer.
- **Integration** (DB on 55432 + Redis on 6379; `StubChatProvider` + `HashEmbeddingProvider` → no API key needed; worker driven in-process via `run_research_job` or `run_consumer(once=True)`, like the backtest e2e tests):
  1. **run → poll → success:** POST `202 queued` → run the worker once → poll `succeeded` with `summary`, `signals.spot` present, `model == "stub-chat"`, `usage`/`cost_usd` populated.
  2. **6h cache fast-path:** with a succeeded note <6h old, POST returns `200 cached:true`, no new row, no quota consumed.
  3. **in-flight dedup:** two POSTs before the worker runs → same `note_id`, exactly one `queued` row.
  4. **rate limit:** 10 runs created today → 11th POST `429 RATE_LIMIT_RESEARCH_DAILY_EXCEEDED`; a `failed` run does not count.
  5. **gating:** pro → `402`, free → `402`.
  6. **graceful degradation:** <250 bars + no sentiment row → polled succeeded note has `signals.vol_forecast is None` and `signals.sentiment is None`.
  7. **no bars:** unknown ticker → worker → poll `failed` with `error.code == "RESEARCH_NO_PRICE_DATA"`.
  8. **worker LLM down:** inject a chat provider that raises `ChatError` → poll `failed` with `error.code == "RESEARCH_LLM_UNAVAILABLE"`.
  9. **RLS isolation:** tenant B cannot poll tenant A's run (`404`) nor see it in `/research/notes`.
- **Isolation gate:** `uv sync` then assert `openai ABSENT` in the default env; worker package tests run via `uv run --package saalr-research-agent`. Default `uv run pytest` stays keyless + torch-free.
- **Regression:** RA-1's `test_schema_matches_models`, the forecast + montecarlo suites (the `load_closes` move must not change their behaviour), and `test_research.py` (rewritten for the async shape) all green.

## Out of scope (RA-3 and later)

Multi-agent LangGraph fan-out (Fundamentals/Sentiment/Technical/Risk/Trader/PM); Anthropic/Google provider fallback + per-tenant LLM-cost budgets; S3 research-note transcripts; streaming/SSE progress; dead-letter stream + transient-vs-permanent failure classification; worker containerization/scheduling (ops slice, like ingest-7); research-note UI; per-tenant configurable daily limits; Idempotency-Key header (the in-flight dedup covers the concurrent-submit case for now).

## Runbook

`docs/runbooks/research-agent.md` — how to run the worker (`uv run --package saalr-research-agent python -m research_agent consume`), the env it needs (`REDIS_URL`, `APP_DATABASE_URL`/`ADMIN_DATABASE_URL`, `OPENAI_API_KEY`), the stream/group names, and how `claim_stale` recovers a crashed worker.
