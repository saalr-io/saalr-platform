#!/bin/sh
set -e

# One-shot mode: `docker run ... python -m ingest_worker backfill --start ... --end ...`
# --no-sync: use the environment baked at build time; don't re-resolve the workspace at runtime.
if [ "$#" -gt 0 ]; then
  exec uv run --no-sync "$@"
fi

# Scheduled mode: run `ingest_worker run` on $INGEST_CRON via supercronic (foreground, stdout logs).
: "${INGEST_CRON:=30 21 * * *}"
printf '%s cd /app && uv run --no-sync python -m ingest_worker run\n' "$INGEST_CRON" > /tmp/ingest.crontab

# -no-reap: as PID 1, supercronic's process reaper does a fork/exec that fails under some
# container runtimes (and is unnecessary here — supercronic waits on the jobs it spawns; use
# docker `init: true` for orphan reaping if ever needed). Applied to BOTH paths so scheduled
# mode actually starts, not just the dry-run validation.
if [ "${INGEST_DRY_RUN:-0}" = "1" ]; then
  exec supercronic -no-reap -test /tmp/ingest.crontab
fi

exec supercronic -no-reap /tmp/ingest.crontab
