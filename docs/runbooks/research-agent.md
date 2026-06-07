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

## Multi-agent graph (RA-3b)

Each research run executes a hand-rolled 6-role graph (sequential): the analysts
**Fundamentals → Sentiment → Technical → Risk**, then the **Trader** (thesis),
then the **Portfolio Manager** (synthesis). The PM's markdown becomes the note's
`summary`; the analyst/trader memos are transient (transcript persistence is
RA-3c). Fundamentals has no financials wired into the platform, so its prompt
explicitly states the gap and forbids inventing figures.

Every run makes **6 metered gateway calls** — one `llm_usage` row each, with
`purpose="research_agent:<role>"`, all linked to the run's `note_id`. The note's
`prompt_tokens`/`completion_tokens`/`cost_usd` are the sums across the six calls;
`model` is the PM call's model.

The budget is checked **before every call** (not just at run start), so a run can
fail `RESEARCH_BUDGET_EXCEEDED` partway through with the already-completed calls'
cost recorded. (At-least-once redelivery of a crashed run re-runs the graph and
may double-count `llm_usage` rows — an accepted over-count, dedup deferred.)

## Transcripts (RA-3c)

Each succeeded run's six agent memos are persisted to `research_transcripts`
(one JSONB row keyed by `note_id`, `transcript_json` = `[{role, memo}, …]` in
graph order). The write is **best-effort** in worker phase 3: a failure logs but
does NOT fail the (already generated + paid-for) note, so a succeeded note can
lack a transcript. The `note_id UNIQUE` constraint + the best-effort catch absorb
at-least-once redelivery (a re-run can't create a second transcript row).

Read it at `GET /research/notes/{id}/transcript` (Premium) — it loads the memos
from the store and merges each agent's `provider`/`model`/tokens/`cost_usd` from
`llm_usage` (joined by `note_id` + `purpose="research_agent:<role>"`), so cost is
not duplicated in the transcript. The poll/list endpoints are unchanged.

The store is **pluggable** (`TranscriptStore` Protocol, injected on
`app.state.transcript_store` and threaded into the worker): `DbTranscriptStore`
today; an `S3TranscriptStore` drops in when the AWS-foundation slice lands, with
no caller change.

## AWS backends (AWS-1)

Set `TRANSCRIPT_S3_BUCKET` (+ `AWS_REGION`) to route transcripts to **S3**
(`S3TranscriptStore`, key `transcripts/{tenant_id}/{note_id}.json`); unset, they
go to Postgres (`DbTranscriptStore`). `boto3` is an optional extra
(`saalr-core[aws]`) — install it where the API/worker run against real S3.

For local dev/tests, run LocalStack and point boto3 at it:

    docker compose -f infra/docker/docker-compose.localstack.yml up -d
    export AWS_ENDPOINT_URL=http://localhost:4566 AWS_DEFAULT_REGION=us-east-1 \
           AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
    aws --endpoint-url=$AWS_ENDPOINT_URL s3 mb s3://saalr-transcripts

The gated tests (`packages/core/tests/test_s3_transcript_store.py`) run only when
`AWS_ENDPOINT_URL` is set + `boto3` is installed; a real-AWS smoke uses real
creds with `AWS_ENDPOINT_URL` unset.
