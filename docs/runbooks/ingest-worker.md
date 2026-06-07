# Runbook — market-data ingest worker

The ingest worker (`apps/ingest-worker`) pulls daily OHLCV bars from Massive into the `bars`
hypertable. It ships as a container that runs on a schedule via **supercronic** (container-native
cron). The same image is what a future ECS Scheduled Task would launch.

## Build the image

```bash
docker build -f apps/ingest-worker/Dockerfile -t saalr-ingest .
```

The entrypoint has two modes:
- **one-shot** — any CLI args are passed through (`docker run … saalr-ingest python -m ingest_worker backfill …`).
- **scheduled** — no args → runs supercronic on `$INGEST_CRON`, executing `ingest_worker run`.

> supercronic runs with `-no-reap` (its PID-1 process reaper fork/execs and fails under some
> container runtimes; the cron jobs are short-lived and supercronic waits on the children it
> spawns). The compose service sets `init: true` so tini reaps any orphans.

## One-shot commands (no scheduler)

Point the container at the dev DB on host **55432** — native PostgreSQL shadows 5432/5433 on this
Windows box, so the Docker DB is published on 55432 via `infra/docker/docker-compose.localport.yml`.
From the host, reach it with `host.docker.internal`:

```bash
# seed the universe
docker run --rm \
  -e APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@host.docker.internal:55432/saalr \
  saalr-ingest python -m ingest_worker add-instrument AAPL --name Apple

# backfill a range (needs a Massive stocks-aggregates key)
docker run --rm \
  -e APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@host.docker.internal:55432/saalr \
  -e MASSIVE_API_KEY="$MASSIVE_API_KEY" \
  saalr-ingest python -m ingest_worker backfill --start 2025-01-01 --end 2025-06-30 --symbol AAPL
```

## Run the scheduler (local, against the compose DB)

The `scheduler` service in `docker-compose.ingest.yml` joins the DB network and talks to the
`postgres` service on 5432. Bring it up alongside the DB stack:

```bash
docker compose \
  -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.localport.yml \
  -f infra/docker/docker-compose.ingest.yml \
  up -d --build
```

Seed an instrument inside the network, then watch it run on a fast (per-minute) cadence:

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.ingest.yml \
  run --rm scheduler python -m ingest_worker add-instrument AAPL --name Apple

INGEST_CRON="* * * * *" docker compose \
  -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.localport.yml \
  -f infra/docker/docker-compose.ingest.yml \
  up -d --build scheduler

docker compose -f infra/docker/docker-compose.ingest.yml logs -f scheduler
```

You should see supercronic read the crontab and, on each tick, fire `ingest_worker run` logging
per-symbol counts. With a valid `MASSIVE_API_KEY` (stocks aggregates), rows appear in `bars`.

## Change the cadence

Set `INGEST_CRON` (standard 5-field cron, **UTC**). Default `30 21 * * *` (daily 21:30 UTC,
~16:30 ET, after the US close). No rebuild needed — the entrypoint regenerates the crontab from
the env var on start.

## Verify the image (smoke)

```bash
docker run --rm saalr-ingest python -m ingest_worker --help     # lists the 4 subcommands
docker run --rm -e INGEST_DRY_RUN=1 saalr-ingest                # validates the crontab, exits 0
```

## Go-live on AWS ECS (follow-up — not built)

The same image is what a production **ECS Scheduled Task** would launch:
- Push the image to **ECR**.
- Define an **ECS task definition** using the image, run in *one-shot* mode: override the command
  to `python -m ingest_worker run` so the task runs once and exits (no supercronic loop in prod).
- Trigger it with an **EventBridge Scheduler** cron rule (e.g. `cron(30 21 * * ? *)`).
- Supply `APP_DATABASE_URL` + `MASSIVE_API_KEY` from **Secrets Manager** (task-definition secrets).
- Depends on the AWS-foundation slice (LLD §13 step 1): VPC/subnets, the ECS cluster, the IAM task
  role, and Secrets Manager — none of which exist yet.
