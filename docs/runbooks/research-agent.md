# Research-agent worker (RA-2)

Generates async research notes from queued `research_notes` rows. The API
(`POST /research/run`) enqueues to the Redis stream `saalr:research:jobs:v1`
(consumer group `research-workers`); this worker consumes, generates, and
persists the note (status `queued → running → succeeded/failed`).

## Run

    uv run --package saalr-research-agent python -m research_agent consume

Flags: `--once` (drain then exit), `--block-ms`, `--count`, `--consumer <name>`.

## Environment

- `APP_DATABASE_URL` — Postgres (RLS app role).
- `REDIS_URL` — default `redis://localhost:6379/0`.
- `OPENAI_API_KEY` — when set (and the `openai` extra installed, which this
  worker's `saalr-core[openai]` dep provides), the worker uses real OpenAI
  embeddings + chat; otherwise `make_*_provider` returns `None` and a run fails
  with `RESEARCH_LLM_UNAVAILABLE`.

## Crash recovery

On startup the worker calls `claim_stale` (XAUTOCLAIM) to reclaim jobs left
pending by a crashed worker after `claim_min_idle_ms` (default 60s) and
reprocesses them. Delivery is at-least-once; `run_research_job` is idempotent
(a re-delivered job whose row is already `succeeded`/`failed` is a no-op).
Each job is acked in a `finally` (poison guard) — a job that always throws is
not redelivered forever; its row is persisted as `failed`.

## Rate limit

10 runs / UTC-day per tenant, enforced at the API (`count_runs_today`
excludes `failed` runs). Cache hits (`<6h` succeeded note) and in-flight
dedup short-circuit before enqueue and do not consume quota.

Known soft-limit behavior (acceptable at this stage): the count read and the
row insert are not in one transaction, so a burst of concurrent requests can
each pass the check and slightly exceed 10. A `queued`/`running` run counts
toward the limit immediately; if it later transitions to `failed` (e.g.
`RESEARCH_NO_PRICE_DATA`), the quota self-heals since `failed` rows are
excluded. A hard, race-free limit (unique-window constraint or atomic counter)
is deferred to RA-3 alongside per-tenant budgets.

## Providers & budget (RA-3a)

The worker generates via a **ChatGateway** with ordered fallback: OpenAI →
Anthropic. `make_chat_gateway(settings)` includes a provider only if its key is
set, so with just `OPENAI_API_KEY` the gateway is OpenAI-only; add
`ANTHROPIC_API_KEY` (+ `ANTHROPIC_MODEL`, default `claude-3-5-haiku-latest`) to
enable fallback. If no provider is configured the run fails
`RESEARCH_LLM_UNAVAILABLE`.

Every successful call is recorded to the per-tenant `llm_usage` ledger
(provider, model, tokens, `cost_usd`, `purpose`, `note_id`). The note's
`cost_usd` is the roll-up for its run; `llm_usage` is the per-call ledger that
budgets + the cost dashboard sum.

**Monthly budget cap** (`LLM_MONTHLY_BUDGET_USD`, default $10/tenant): before a
run, month-to-date `llm_usage` for the tenant is summed (UTC calendar month). At
or over the cap, the run is rejected — fail-fast `402 RESEARCH_BUDGET_EXCEEDED`
at the API, and authoritatively in the worker (phase-1 check →
`RESEARCH_BUDGET_EXCEEDED`). The cap is uniform across tenants for now
(per-tenant overrides + operator alerts deferred).
