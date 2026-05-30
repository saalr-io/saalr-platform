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

# INGEST_DRY_RUN=1 validates the crontab and exits (used by the image smoke test).
# -no-reap: as PID 1, supercronic's process reaper does a fork/exec that fails under
# some container runtimes; the reaper is irrelevant for a non-running validation pass.
if [ "${INGEST_DRY_RUN:-0}" = "1" ]; then
  exec supercronic -no-reap -test /tmp/ingest.crontab
fi

exec supercronic /tmp/ingest.crontab
