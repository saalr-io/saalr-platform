# Ingest Worker — Dockerization + Local Scheduler — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A production-style Docker image for the ingest worker plus a local docker-compose scheduler (supercronic cron) that runs `ingest_worker run` on a schedule against the local Postgres.

**Architecture:** A `python:3.12` + `uv` image that `uv sync`s only the `saalr-ingest-worker` workspace package and installs supercronic; an entrypoint that passes through one-shot CLI commands or runs supercronic on `$INGEST_CRON`; a separate `docker-compose.ingest.yml` `scheduler` service joining the existing DB network.

**Tech Stack:** Docker, uv (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`), supercronic, docker-compose, sh.

**Spec:** `docs/superpowers/specs/2026-05-30-ingest-scheduler-design.md`

**This slice is infra — verification is `docker build` + container smokes + `docker compose config`, not pytest.** Docker Desktop must be running. The build context is the **repo root** (the Dockerfile copies the uv workspace). The root is a uv workspace (`members = ["packages/*","apps/*"]`, `apps/web` excluded); `uv sync --frozen --package saalr-ingest-worker` installs only the worker + `saalr-core` (avoids the empty `research-agent`/`ml-worker` placeholders).

## File structure

```
.dockerignore                              # NEW (repo root) — keep the build context lean
apps/ingest-worker/Dockerfile              # NEW — the worker image
apps/ingest-worker/docker-entrypoint.sh    # NEW — passthrough | supercronic
apps/ingest-worker/crontab                 # NEW — documents the default schedule line
infra/docker/docker-compose.ingest.yml     # NEW — scheduler service
docs/runbooks/ingest-worker.md             # NEW — build/seed/run/cadence + ECS go-live note
```

---

## Task 1: Worker image (Dockerfile + entrypoint + crontab + .dockerignore)

**Files:**
- Create: `.dockerignore`
- Create: `apps/ingest-worker/Dockerfile`
- Create: `apps/ingest-worker/docker-entrypoint.sh`
- Create: `apps/ingest-worker/crontab`

- [ ] **Step 1: Create `.dockerignore` (repo root)**

```
.git
.github
.venv
**/.venv
**/__pycache__
**/*.py[cod]
**/.pytest_cache
**/.ruff_cache
**/node_modules
apps/web
docs
mocks
tools
.superpowers
.cache
logs
dist
```

- [ ] **Step 2: Create `apps/ingest-worker/docker-entrypoint.sh`**

```sh
#!/bin/sh
set -e

# One-shot mode: `docker run ... python -m ingest_worker backfill --start ... --end ...`
if [ "$#" -gt 0 ]; then
  exec uv run "$@"
fi

# Scheduled mode: run `ingest_worker run` on $INGEST_CRON via supercronic (foreground, stdout logs).
: "${INGEST_CRON:=30 21 * * *}"
printf '%s cd /app && uv run python -m ingest_worker run\n' "$INGEST_CRON" > /tmp/ingest.crontab

# INGEST_DRY_RUN=1 validates the crontab and exits (used by the image smoke test).
if [ "${INGEST_DRY_RUN:-0}" = "1" ]; then
  exec supercronic -test /tmp/ingest.crontab
fi

exec supercronic /tmp/ingest.crontab
```

- [ ] **Step 3: Create `apps/ingest-worker/crontab`** (documents the default; the entrypoint regenerates it from `$INGEST_CRON`)

```
# Default ingest schedule. The container entrypoint regenerates this from the
# $INGEST_CRON env var, so change the cadence there (no rebuild needed).
# Daily at 21:30 UTC (~16:30 ET, after the US close, when the settled daily bar exists).
30 21 * * * cd /app && uv run python -m ingest_worker run
```

- [ ] **Step 4: Create `apps/ingest-worker/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# supercronic — container-native cron (runs in foreground, logs to stdout, unlike system cron)
ARG SUPERCRONIC_VERSION=v0.2.33
ARG SUPERCRONIC_SHA1SUM=71b0d58cc53f6bd72cf2f293e09e294b79c666d8
ADD https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN echo "${SUPERCRONIC_SHA1SUM}  /usr/local/bin/supercronic" | sha1sum -c - \
 && chmod +x /usr/local/bin/supercronic

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# Copy the uv workspace (apps/web, docs, etc. are excluded via .dockerignore) and install
# only the worker package + its dependency closure (saalr-core).
COPY . /app
RUN uv sync --frozen --package saalr-ingest-worker

RUN chmod +x /app/apps/ingest-worker/docker-entrypoint.sh \
 && useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

ENTRYPOINT ["/app/apps/ingest-worker/docker-entrypoint.sh"]
```

- [ ] **Step 5: Build the image**

Run (from repo root): `docker build -f apps/ingest-worker/Dockerfile -t saalr-ingest .`
Expected: build succeeds (supercronic sha1 verifies; `uv sync` resolves saalr-ingest-worker + saalr-core). If `uv sync` complains about a missing workspace member, confirm `.dockerignore` did NOT exclude `packages/` or any `apps/` member except `apps/web`.

- [ ] **Step 6: Smoke — CLI passthrough**

Run: `docker run --rm saalr-ingest python -m ingest_worker --help`
Expected: usage text listing `add-instrument`, `list-instruments`, `backfill`, `run`; exit 0. (Proves the venv + entrypoint passthrough work.)

- [ ] **Step 7: Smoke — cron render + validate (no DB, non-blocking)**

Run: `docker run --rm -e INGEST_DRY_RUN=1 -e INGEST_CRON="*/2 * * * *" saalr-ingest`
Expected: supercronic prints that it read/validated the crontab and exits 0 (the `-test` path). Proves the scheduled-mode crontab renders from `$INGEST_CRON` and is a valid cron expression.

- [ ] **Step 8: Commit**

```bash
git add .dockerignore apps/ingest-worker/Dockerfile apps/ingest-worker/docker-entrypoint.sh apps/ingest-worker/crontab
git commit -m "feat(ingest): worker Docker image + supercronic entrypoint"
```

---

## Task 2: Scheduler compose service

**Files:**
- Create: `infra/docker/docker-compose.ingest.yml`

- [ ] **Step 1: Create `infra/docker/docker-compose.ingest.yml`**

```yaml
services:
  scheduler:
    build:
      context: ../..
      dockerfile: apps/ingest-worker/Dockerfile
    environment:
      # Inside the compose network the DB host is the `postgres` service on 5432
      # (NOT the host-published 55432).
      APP_DATABASE_URL: postgresql+asyncpg://saalr_app:saalr_app@postgres:5432/saalr
      MASSIVE_API_KEY: ${MASSIVE_API_KEY:-}
      INGEST_CRON: ${INGEST_CRON:-30 21 * * *}
    depends_on:
      - postgres
    restart: unless-stopped
```

- [ ] **Step 2: Validate the merged compose config**

Run: `docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.ingest.yml config`
Expected: prints the merged config with `postgres`, `redis`, and `scheduler` services; no YAML/interpolation errors. (The `scheduler` references the `postgres` service from the base file, so both `-f` files are required together.)

- [ ] **Step 3: Commit**

```bash
git add infra/docker/docker-compose.ingest.yml
git commit -m "feat(ingest): local scheduler compose service"
```

---

## Task 3: Runbook + final verification

**Files:**
- Create: `docs/runbooks/ingest-worker.md`

- [ ] **Step 1: Create `docs/runbooks/ingest-worker.md`**

````markdown
# Runbook — market-data ingest worker

The ingest worker (`apps/ingest-worker`) pulls daily OHLCV bars from Massive into the `bars`
hypertable. It runs as a container on a schedule via supercronic.

## Build the image

```bash
docker build -f apps/ingest-worker/Dockerfile -t saalr-ingest .
```

## One-shot commands (no scheduler)

The image entrypoint passes through any CLI command. Point it at the dev DB on host **55432**
(native PostgreSQL shadows 5432/5433 on this Windows box; the Docker DB is published on 55432 via
`infra/docker/docker-compose.localport.yml`). From the host, use `host.docker.internal`:

```bash
# seed the universe
docker run --rm \
  -e APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@host.docker.internal:55432/saalr \
  saalr-ingest python -m ingest_worker add-instrument AAPL --name Apple

# backfill a range (needs a Massive stocks-aggregates key)
docker run --rm \
  -e APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@host.docker.internal:55432/saalr \
  -e MASSIVE_API_KEY=$MASSIVE_API_KEY \
  saalr-ingest python -m ingest_worker backfill --start 2025-01-01 --end 2025-06-30 --symbol AAPL
```

## Run the scheduler (local, against the compose DB)

The `scheduler` service in `docker-compose.ingest.yml` joins the DB network and talks to the
`postgres` service on 5432. Bring it up alongside the DB:

```bash
docker compose \
  -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.localport.yml \
  -f infra/docker/docker-compose.ingest.yml \
  up -d --build
```

Seed an instrument inside the network, then watch it run:

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.ingest.yml \
  run --rm scheduler python -m ingest_worker add-instrument AAPL --name Apple

# demo cadence: every minute, so you can watch it fire
INGEST_CRON="* * * * *" docker compose \
  -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.localport.yml \
  -f infra/docker/docker-compose.ingest.yml \
  up -d --build scheduler

docker compose -f infra/docker/docker-compose.ingest.yml logs -f scheduler
```

You should see `ingest_worker run` fire on the cron tick, logging per-symbol counts; with a valid
`MASSIVE_API_KEY` (stocks aggregates), rows appear in `bars`.

## Change the cadence

Set `INGEST_CRON` (standard 5-field cron, UTC). Default `30 21 * * *` (daily 21:30 UTC, ~16:30 ET
after the US close). No rebuild needed — the entrypoint regenerates the crontab from the env var.

## Go-live on AWS ECS (follow-up, not built)

The same image is what a production **ECS Scheduled Task** would launch:
- Push the image to **ECR**.
- Define an **ECS task definition** using the image, with the entrypoint run in *one-shot* mode:
  override the command to `python -m ingest_worker run` (so the task runs once and exits, rather
  than supercronic looping).
- Trigger it with an **EventBridge Scheduler** cron rule (e.g. `cron(30 21 * * ? *)`).
- Supply `APP_DATABASE_URL` + `MASSIVE_API_KEY` from **Secrets Manager** (task definition secrets).
- This depends on the AWS-foundation slice (LLD §13 step 1): VPC/subnets, the ECS cluster, the IAM
  task role, and Secrets Manager — none of which exist yet.
````

- [ ] **Step 2: Re-run the image + compose verification (final gate)**

Run: `docker build -f apps/ingest-worker/Dockerfile -t saalr-ingest .`
Expected: succeeds.
Run: `docker run --rm saalr-ingest python -m ingest_worker --help`
Expected: 4 subcommands.
Run: `docker run --rm -e INGEST_DRY_RUN=1 saalr-ingest`
Expected: supercronic validates the default crontab, exit 0.
Run: `docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.ingest.yml config >/dev/null && echo "compose ok"`
Expected: `compose ok`.

- [ ] **Step 3: Confirm existing suites are unaffected**

Run: `cd packages/core && uv run pytest -q && cd ../..`
Expected: green (no app code changed).
Run: `uvx ruff check apps/ingest-worker` (the shell/Docker files aren't Python; this just confirms the existing worker package still lints).
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add docs/runbooks/ingest-worker.md
git commit -m "docs(ingest): scheduler runbook + ECS go-live note"
```

---

## Self-review checklist (completed)

- **Spec coverage:** Dockerfile + uv-sync-worker-package + non-root (T1), supercronic install + verified sha1 (T1), entrypoint passthrough/scheduled/dry-run (T1), crontab default (T1), `.dockerignore` lean context (T1), scheduler compose service on the DB network with env (T2), image smoke + cron-validate + compose config verification (T1/T3), runbook with build/seed/run/cadence + ECS go-live note (T3). All spec sections covered.
- **Placeholder scan:** none — every file is complete; the supercronic sha1 is the real verified value for v0.2.33.
- **Consistency:** the entrypoint path `/app/apps/ingest-worker/docker-entrypoint.sh` matches the COPY layout; `INGEST_CRON`/`INGEST_DRY_RUN` env names are consistent across entrypoint, compose, and runbook; the compose `scheduler` uses `postgres:5432` (network DNS) while the runbook's host-run examples use `host.docker.internal:55432` (correctly distinguished).

## Known risks / notes

- **Build needs network** (pull the uv base image + ADD supercronic + `uv sync` downloads wheels). First build is slow; subsequent builds cache.
- **`host.docker.internal`** resolves on Docker Desktop (Windows/Mac). The runbook's one-shot host examples rely on it; the in-compose `scheduler` uses the `postgres` service name instead (no host gateway needed).
- **Single instance, no locking** — fine for one scheduler. The runbook's `run`-once ECS note avoids supercronic in prod (EventBridge is the scheduler there).
- **supercronic `-test`** exits non-zero on an invalid crontab — the dry-run smoke doubles as crontab validation.
- The image bundles the whole Python workspace source (minus `.dockerignore`d paths). That's acceptable for a worker image; a multi-stage slimming is a later optimization (out of scope).
```
