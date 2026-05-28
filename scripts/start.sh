#!/usr/bin/env bash
# Start the Saalr local dev stack: Docker Postgres+Redis, the FastAPI API, and the web dev server.
#
# Brings up the database (and waits for it), applies migrations, starts the API in the
# background, then runs the Vite web dev server in the foreground. Press Ctrl+C to stop —
# the API is shut down automatically via the trap.
#
# Flags:
#   --skip-db         Don't start/wait for the Docker database (assume it's already up).
#   --skip-migrate    Don't run `alembic upgrade head`.
#   --no-web          Start the DB + API only (no web dev server); blocks until Ctrl+C.
#   --api-port=PORT   Port for the API (default 8000).
#
# Usage: bash scripts/start.sh [flags]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f infra/docker/docker-compose.yml)

SKIP_DB=0
SKIP_MIGRATE=0
NO_WEB=0
API_PORT=8000
for arg in "$@"; do
  case "$arg" in
    --skip-db) SKIP_DB=1 ;;
    --skip-migrate) SKIP_MIGRATE=1 ;;
    --no-web) NO_WEB=1 ;;
    --api-port=*) API_PORT="${arg#*=}" ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

export ADMIN_DATABASE_URL="${ADMIN_DATABASE_URL:-postgresql+asyncpg://postgres:postgres@localhost:5432/saalr}"
export APP_DATABASE_URL="${APP_DATABASE_URL:-postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 not found on PATH" >&2; exit 1; }; }
need uv
[ "$NO_WEB" -eq 0 ] && need pnpm
mkdir -p logs

if [ "$SKIP_DB" -eq 0 ]; then
  need docker
  echo "Starting Docker Postgres + Redis..."
  "${COMPOSE[@]}" up -d
  printf "Waiting for Postgres"
  for _ in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T postgres pg_isready -U postgres -d saalr >/dev/null 2>&1; then
      echo " ready"; break
    fi
    printf "."; sleep 2
  done
fi

if [ "$SKIP_MIGRATE" -eq 0 ]; then
  echo "Applying migrations (alembic upgrade head)..."
  uv run alembic upgrade head
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
API_LOG="logs/api-$STAMP.log"
echo "Starting API on http://localhost:$API_PORT  (log: $API_LOG)"
uv run uvicorn saalr_api.main:create_app --factory --host 127.0.0.1 --port "$API_PORT" >"$API_LOG" 2>&1 &
API_PID=$!

cleanup() {
  echo
  echo "Stopping API (PID $API_PID)..."
  kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 20); do
  curl -sf "http://localhost:$API_PORT/healthz" >/dev/null 2>&1 && break || sleep 1
done
echo "API ready: http://localhost:$API_PORT/healthz  (Swagger: /docs)"

if [ "$NO_WEB" -eq 1 ]; then
  echo "API running (PID $API_PID). Press Ctrl+C to stop."
  wait "$API_PID"
else
  echo "Starting web dev server (Vite) - it will print its URL (5173 or next free)."
  echo "Press Ctrl+C to stop the web server and the API."
  pnpm -C apps/web dev
fi
