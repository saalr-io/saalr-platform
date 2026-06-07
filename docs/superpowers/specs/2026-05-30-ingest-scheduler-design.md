# Ingest worker — Dockerization + local scheduler — design

**Date:** 2026-05-30
**Slice:** Operationalize the market-data ingestion worker (§13.5) — containerize it and run it on a schedule locally. The AWS ECS Scheduled Task path is a documented follow-up (it depends on the deferred AWS-foundation slice, §13 step 1).
**Status:** Approved design, pre-plan.
**Builds on:** the `ingest-worker` CLI (`python -m ingest_worker run`) and the Docker Postgres dev stack.

## Purpose

The ingest worker is a CLI that must run on a schedule to keep daily bars fresh. There is no
AWS deployed (Terraform/ECS are placeholders) and no Dockerfile yet. This slice delivers a
**production-style Docker image for the worker** and a **local container scheduler** (supercronic
cron) that runs `ingest_worker run` daily against the local Postgres — runnable and observable
today, and the same image is what a future ECS Scheduled Task would launch.

## Decisions (locked during brainstorming)

1. **Dockerfile + local Docker cron** (runnable now). AWS ECS/EventBridge is out of scope (a
   documented follow-up; it needs the unbuilt VPC/cluster/IAM/Secrets foundation).
2. **supercronic** as the in-container cron runner (container-native: single static binary,
   foreground, logs to stdout — unlike system `cron`/`crond`).
3. **A dedicated `infra/docker/docker-compose.ingest.yml`** scheduler service (kept separate from
   the lean PG/Redis `docker-compose.yml`).
4. **Default schedule: daily 21:30 UTC** (after the US close, so the settled daily bar exists);
   overridable via the `INGEST_CRON` env.

## Architecture

```
apps/ingest-worker/
  Dockerfile              # build the worker image (uv sync + supercronic)
  .dockerignore
  crontab                 # `${INGEST_CRON} python -m ingest_worker run` (env-substituted at start)
  docker-entrypoint.sh    # render crontab from $INGEST_CRON, exec supercronic (or passthrough a CLI cmd)
infra/docker/
  docker-compose.ingest.yml   # `scheduler` service: build the image, join the DB network, env
docs/runbooks/
  ingest-worker.md        # build / seed instruments / run scheduler / change cadence / go-live note
```

### Image (`apps/ingest-worker/Dockerfile`)
- Base `python:3.12-slim`. Install `uv` (copy the static binary from `ghcr.io/astral-sh/uv:latest`
  image stage, the documented pattern).
- Copy the minimal workspace: root `pyproject.toml`, `uv.lock`, `.python-version`,
  `packages/core/`, `apps/ingest-worker/`. Run `uv sync --frozen --package saalr-ingest-worker`
  (creates `.venv` with saalr-core + worker deps: sqlalchemy[asyncio], asyncpg, pydantic-settings,
  uuid-utils, httpx).
- Install **supercronic** (download the pinned release binary, verify it's executable).
- Copy `crontab` + `docker-entrypoint.sh`. `ENTRYPOINT ["/app/docker-entrypoint.sh"]`. With no
  args, the entrypoint renders the crontab and execs supercronic; with args
  (`docker run … python -m ingest_worker backfill …`) it execs them directly via `uv run`.
- Runs as a non-root user.

### Entrypoint (`docker-entrypoint.sh`)
```sh
#!/bin/sh
set -e
if [ "$#" -gt 0 ]; then exec uv run "$@"; fi          # one-shot: backfill/add-instrument/etc.
: "${INGEST_CRON:=30 21 * * *}"
echo "$INGEST_CRON cd /app && uv run python -m ingest_worker run" > /tmp/crontab
exec supercronic /tmp/crontab                          # scheduled: run on cron, log to stdout
```
(The committed `apps/ingest-worker/crontab` documents the default line; the entrypoint regenerates
it from `INGEST_CRON` so the cadence is configurable without rebuilding.)

### Scheduler service (`infra/docker/docker-compose.ingest.yml`)
```yaml
services:
  scheduler:
    build: { context: ../.., dockerfile: apps/ingest-worker/Dockerfile }
    environment:
      APP_DATABASE_URL: postgresql+asyncpg://saalr_app:saalr_app@postgres:5432/saalr
      MASSIVE_API_KEY: ${MASSIVE_API_KEY:-}
      INGEST_CRON: ${INGEST_CRON:-30 21 * * *}
    depends_on: [postgres]
    networks: [default]
```
Run alongside the main stack:
`docker compose -f docker-compose.yml -f docker-compose.localport.yml -f docker-compose.ingest.yml up -d`.
Inside the compose network the DB host is `postgres:5432` (container DNS) — **not** the host-
published 55432. `MASSIVE_API_KEY` comes from the host env / `.env`.

## Data flow
1. Operator seeds the universe once (one-shot container): `docker compose … run --rm scheduler python -m ingest_worker add-instrument AAPL --name Apple`.
2. The `scheduler` service runs supercronic; at the cron time it execs `ingest_worker run`, which
   appends new daily bars for all active instruments into `bars` (per-symbol transactions).
3. Logs (the run summary, per-symbol counts/failures) stream to the container's stdout.

## Error handling
- `MASSIVE_API_KEY` missing/empty → the worker's `run` surfaces `ProviderError` per symbol and
  logs it; supercronic keeps scheduling (a bad run doesn't kill the scheduler).
- DB unreachable → the run errors and logs; the next cron tick retries. supercronic runs each job
  in its own process; a non-zero exit is logged, not fatal to the scheduler.
- A long-running `run` overlapping the next tick: daily cadence + minutes-long runs make overlap
  unlikely; supercronic logs if a job is still running. (No locking this slice — single-instance.)

## Testing / verification (infra — build + observe, not pure TDD)
- **Image builds:** `docker build -f apps/ingest-worker/Dockerfile -t saalr-ingest .` succeeds.
- **Image smoke:** `docker run --rm saalr-ingest python -m ingest_worker --help` prints the four
  subcommands (proves the venv + entrypoint passthrough work).
- **Compose validates:** `docker compose -f docker-compose.yml -f docker-compose.ingest.yml config`
  parses (no YAML/interpolation errors).
- **Entrypoint logic:** a tiny shell test (or manual) — with args it passes through; with none it
  writes the crontab from `INGEST_CRON` and would exec supercronic. (Assert the rendered crontab
  line contains the cron expr + `ingest_worker run`.)
- **End-to-end (manual, documented in the runbook):** bring up the stack + scheduler with
  `INGEST_CRON="* * * * *"`, seed an instrument, watch the logs fire `run` within a minute, and
  (with a Massive stocks key) confirm rows appear in `bars`.
- The existing Python/web suites are unaffected (no app code changes).

## Out of scope
- AWS ECS Scheduled Task + EventBridge + ECR push + Terraform (documented follow-up; needs the
  AWS-foundation slice). The runbook includes a "go-live on ECS" note describing the mapping
  (same image → ECS task def; cron → EventBridge schedule; env → Secrets Manager).
- CI building/publishing the image; multi-arch; image size optimization beyond `slim` + a focused
  copy.
- Distributed locking / multiple scheduler replicas; alerting on failed runs (freshness alerts are
  a later slice).
- Scheduling the option-chain snapshot job (only daily bars exist to ingest today).
