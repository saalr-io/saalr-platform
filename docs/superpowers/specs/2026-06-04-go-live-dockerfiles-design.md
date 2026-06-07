# Go-live Dockerfiles — design

**Status:** approved design, 2026-06-04.

## Goal

Author production Dockerfiles for the five apps the dev Terraform already references but which lack
one — `api`, `backtest-worker`, `oms-worker`, `ml-worker`, `research-agent` — so the existing AWS IaC
(`infra/terraform/environments/dev`) can build and deploy real images. Mirror the proven
`apps/ingest-worker/Dockerfile` (uv workspace, non-root, single ENTRYPOINT). The Terraform itself is
already authored and is **not** modified here.

## Current state

- Only `apps/ingest-worker/Dockerfile` exists. The dev stack (`infra/terraform/environments/dev/main.tf`)
  references images for `api`, `ingest-worker`, `oms-worker`, `ml-worker`, `backtest-worker`,
  `research-agent` via `module.compute.ecr_repository_urls[...]` and passes each its ECS `command`.
- Every Python app exposes a CLI: `apps/<app>/<pkg>/__main__.py` does `from .cli import main; main()`,
  so `python -m <pkg> <subcommand>` dispatches (e.g. `consume`, `reconcile --once`, `sentiment`, `run`).
- The API is a factory: `apps/api/saalr_api/main.py` defines `create_app() -> FastAPI` (no module-level
  `app`), with a `/healthz` route. Deps include `fastapi` + `uvicorn[standard]` + `saalr-core`/`-ml`/
  `-content`. `research-agent` depends on `saalr-core[openai,anthropic]` (non-optional → installed by a
  plain `uv sync`). `ml-worker` pulls torch + transformers (heavy).
- Root `.dockerignore` already excludes `apps/web`, `docs`, `tools`, `.venv`, caches, `node_modules`,
  `dist` — so the Python build contexts are lean.

## The shared pattern (mirror `apps/ingest-worker/Dockerfile`)

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
COPY . /app
RUN uv sync --frozen --package saalr-<app>
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser
ENTRYPOINT [...]   # per-app, see table
```

`uv sync --frozen --package saalr-<app>` installs only that workspace package plus its dependency
closure. Non-root `appuser` (uid 10001). **No supercronic** — ECS schedules these via EventBridge
RunTask (one-shot) or runs them as Fargate services, so the ENTRYPOINT is the app itself and ECS
passes the subcommand as the container `command`.

## Per-app ENTRYPOINT (must match the Terraform `command`)

| App | `uv sync` package | ENTRYPOINT | ECS `command` (dev/main.tf) |
|---|---|---|---|
| `api` | `saalr-api` | `["uv","run","--no-sync","uvicorn","saalr_api.main:create_app","--factory","--host","0.0.0.0","--port","8000"]` | — (ALB service) |
| `backtest-worker` | `saalr-backtest-worker` | `["uv","run","--no-sync","python","-m","backtest_worker"]` | `["consume"]` |
| `oms-worker` | `saalr-oms-worker` | `["uv","run","--no-sync","python","-m","oms_worker"]` | `["reconcile","--once"]` |
| `ml-worker` | `saalr-ml-worker` | `["uv","run","--no-sync","python","-m","ml_worker"]` | `["sentiment"]` |
| `research-agent` | `saalr-research-agent` | `["uv","run","--no-sync","python","-m","research_agent"]` | `["consume"]` |

### API specifics

- `EXPOSE 8000` — **must equal the Terraform `api_service` container port** (record the contract in the
  runbook; do not change Terraform here).
- uvicorn uses `--factory saalr_api.main:create_app` (the app is a factory, not a module-level `app`).
- `HEALTHCHECK` hitting `/healthz` via python's stdlib (no curl in the slim image):
  ```dockerfile
  HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python","-c","import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"]
  ```
  (The ALB target group is the real production health check; this aids local/compose runs.)

### Worker specifics

`ml-worker` and `research-agent` produce large images (torch/transformers; openai+anthropic). They
build correctly but slowly — flagged for manual build (see Verification). All four workers take the
ECS `command` as the CLI subcommand, so no entrypoint wrapper script is needed.

## Files

- `apps/api/Dockerfile`, `apps/backtest-worker/Dockerfile`, `apps/oms-worker/Dockerfile`,
  `apps/ml-worker/Dockerfile`, `apps/research-agent/Dockerfile` — five new, per the table.
- `infra/docker/docker-compose.build.yml` — one `build` service per image
  (`context: ../..`, `dockerfile: apps/<app>/Dockerfile`, `image: saalr/<app>:local`), including the
  existing `ingest-worker`, so `docker compose -f infra/docker/docker-compose.build.yml build` builds
  the whole set locally and can run alongside the existing db/redis compose for a local full-stack.
- `docs/runbooks/go-live-images.md` — the operational sequence: `docker compose … build` → `aws ecr
  get-login-password | docker login` → `docker tag saalr/<app>:local <acct>.dkr.ecr.<region>.amazonaws.com/saalr-dev-<app>:latest`
  → `docker push` → `terraform -chdir=infra/terraform/environments/dev apply`; the `container_port=8000`
  contract; the `terraform.tfvars` / Secrets Manager values to set before apply; and the note that
  `ml-worker`/`research-agent` are heavy builds.

## Verification (lint all + build the light images)

- **Lint** all five new Dockerfiles with dockerized hadolint:
  `docker run --rm -i hadolint/hadolint < apps/<app>/Dockerfile` → no errors (warnings acceptable if
  matching the ingest-worker baseline).
- **Build** the lightweight shared-core images via the build compose: `api`, `oms-worker`,
  `backtest-worker`. Then an **import/CLI smoke** (no DB needed):
  - workers: `docker run --rm saalr/oms-worker:local --help` (the ENTRYPOINT + `python -m oms_worker`
    resolve and print CLI help); same for `backtest-worker`.
  - api: `docker run --rm --entrypoint python saalr/api:local -c "import saalr_api.main; saalr_api.main.create_app"`
    (the package imports and the factory is callable; full serving needs a DB, out of smoke scope).
- **Document** the `ml-worker` + `research-agent` builds as a manual runbook step (heavy/slow here).
- The existing pytest/web suites are untouched and remain green (this slice adds no Python/TS code).

## Constraints honored

- Never stage `.terraform/` or `*.tfstate*`; the existing Terraform is not modified.
- The root `.dockerignore` already excludes web/docs/tooling, keeping the build contexts lean.
- Non-root containers (uid 10001), `--frozen` installs (reproducible, no lockfile drift), pinned base.

## Out of scope (explicit follow-ups)

`content-worker` Dockerfile + its Terraform wiring; the web app's static S3/CloudFront deploy (it is
fully static — `npm run build` → `dist`, no container); a GitHub Actions ECR build-push workflow; and
the actual `terraform apply` / ECR push (need AWS credentials).
