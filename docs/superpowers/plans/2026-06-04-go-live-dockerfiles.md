# Go-live Dockerfiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Production Dockerfiles for `api`, `backtest-worker`, `oms-worker`, `ml-worker`, `research-agent` (the images the dev Terraform references but lack one), mirroring `apps/ingest-worker/Dockerfile`; a build-all compose; and a go-live runbook. Terraform is NOT modified.

**Architecture:** Each image is a uv-workspace build (`uv sync --frozen --package saalr-<app>`), non-root, single ENTRYPOINT = the app (ECS supplies the CLI subcommand as `command`). The API runs uvicorn against the `create_app` factory on port 8000.

**Tech Stack:** Docker, uv (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`), hadolint (dockerized).

**Conventions (apply to every task):**
- Commit footer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- NEVER modify root `.gitignore`, `tools/equity-screener/equity_screener/cli.py`, or any existing Terraform; never stage `.terraform/` or `*.tfstate*`. Stage ONLY each task's files.
- Lint: `docker run --rm -i hadolint/hadolint < apps/<app>/Dockerfile` → no errors (warnings acceptable if the existing `ingest-worker` Dockerfile produces the same).
- Builds run from the repo root: `docker compose -f infra/docker/docker-compose.build.yml build <svc>`.

---

### Task 1: worker Dockerfiles — `backtest-worker`, `oms-worker`

**Files:** Create `apps/backtest-worker/Dockerfile`, `apps/oms-worker/Dockerfile`.

- [ ] **Step 1: create** `apps/backtest-worker/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# Copy the uv workspace (apps/web, docs, etc. excluded via the root .dockerignore) and install
# only this worker package + its dependency closure (saalr-core).
COPY . /app
RUN uv sync --frozen --package saalr-backtest-worker

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

# ECS supplies the CLI subcommand as the container command (e.g. ["consume"]).
ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "backtest_worker"]
```

- [ ] **Step 2: create** `apps/oms-worker/Dockerfile` (identical but `saalr-oms-worker` / `oms_worker`):

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

COPY . /app
RUN uv sync --frozen --package saalr-oms-worker

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

# ECS supplies the CLI subcommand as the container command (e.g. ["reconcile","--once"]).
ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "oms_worker"]
```

- [ ] **Step 3: lint** both: `docker run --rm -i hadolint/hadolint < apps/backtest-worker/Dockerfile` and the oms one → no errors.

- [ ] **Step 4: commit**

```bash
git add apps/backtest-worker/Dockerfile apps/oms-worker/Dockerfile
git commit -m "build(infra): Dockerfiles for backtest-worker + oms-worker (uv, non-root, CLI entrypoint)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: heavy worker Dockerfiles — `ml-worker`, `research-agent`

**Files:** Create `apps/ml-worker/Dockerfile`, `apps/research-agent/Dockerfile`. (Lint-only here — builds are large/slow; documented as manual in the runbook.)

- [ ] **Step 1: create** `apps/ml-worker/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# saalr-ml-worker pulls torch + transformers (large image, slow build). The FinBERT model is
# downloaded at first run into the HF cache unless pre-baked (out of scope).
COPY . /app
RUN uv sync --frozen --package saalr-ml-worker

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

# ECS supplies the CLI subcommand as the container command (e.g. ["sentiment"]).
ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "ml_worker"]
```

- [ ] **Step 2: create** `apps/research-agent/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# saalr-research-agent depends on saalr-core[openai,anthropic] (non-optional → installed here).
COPY . /app
RUN uv sync --frozen --package saalr-research-agent

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

# ECS supplies the CLI subcommand as the container command (e.g. ["consume"]).
ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "research_agent"]
```

- [ ] **Step 3: lint** both with hadolint → no errors.

- [ ] **Step 4: commit**

```bash
git add apps/ml-worker/Dockerfile apps/research-agent/Dockerfile
git commit -m "build(infra): Dockerfiles for ml-worker + research-agent (uv, non-root, CLI entrypoint)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: API Dockerfile

**Files:** Create `apps/api/Dockerfile`.

- [ ] **Step 1: create** `apps/api/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

COPY . /app
RUN uv sync --frozen --package saalr-api

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

EXPOSE 8000

# Local/compose health check; the ALB target group is the production health check.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD ["uv", "run", "--no-sync", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"]

# Factory app: saalr_api.main:create_app() -> FastAPI. Port 8000 MUST match the Terraform
# api_service container_port.
ENTRYPOINT ["uv", "run", "--no-sync", "uvicorn", "saalr_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: lint** `docker run --rm -i hadolint/hadolint < apps/api/Dockerfile` → no errors.

- [ ] **Step 3: commit**

```bash
git add apps/api/Dockerfile
git commit -m "build(infra): API Dockerfile (uvicorn factory on :8000, /healthz, non-root)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: build-all compose + go-live runbook

**Files:** Create `infra/docker/docker-compose.build.yml`, `docs/runbooks/go-live-images.md`.

- [ ] **Step 1: create** `infra/docker/docker-compose.build.yml`:

```yaml
# Build every Saalr service/worker image locally:
#   docker compose -f infra/docker/docker-compose.build.yml build
# Produces saalr/<app>:local images (run alongside docker-compose.yml + localport for a local stack).
services:
  api:
    build:
      context: ../..
      dockerfile: apps/api/Dockerfile
    image: saalr/api:local
  ingest-worker:
    build:
      context: ../..
      dockerfile: apps/ingest-worker/Dockerfile
    image: saalr/ingest-worker:local
  backtest-worker:
    build:
      context: ../..
      dockerfile: apps/backtest-worker/Dockerfile
    image: saalr/backtest-worker:local
  oms-worker:
    build:
      context: ../..
      dockerfile: apps/oms-worker/Dockerfile
    image: saalr/oms-worker:local
  ml-worker:
    build:
      context: ../..
      dockerfile: apps/ml-worker/Dockerfile
    image: saalr/ml-worker:local
  research-agent:
    build:
      context: ../..
      dockerfile: apps/research-agent/Dockerfile
    image: saalr/research-agent:local
```

- [ ] **Step 2: create** `docs/runbooks/go-live-images.md`:

```markdown
# Go-live: build & push the service images

Builds the Saalr container images and pushes them to the ECR repositories the dev Terraform
provisions, then applies the stack. Images: `api`, `ingest-worker`, `oms-worker`, `ml-worker`,
`backtest-worker`, `research-agent`.

## Contracts (must stay in sync)

- The **API listens on container port 8000** (`apps/api/Dockerfile` `EXPOSE 8000` + uvicorn `--port 8000`).
  This must equal the Terraform `api_service` container port.
- Each worker's **ENTRYPOINT is its CLI** (`python -m <pkg>`); the ECS task's `command` is the
  subcommand (`["consume"]`, `["reconcile","--once"]`, `["sentiment"]`, `["run"]`). Keep
  `infra/terraform/environments/dev/main.tf` `command`s aligned with the CLIs.
- ECR repo names are `saalr-dev-<app>` (from `module.compute` `ecr_repo_names`).

## 1. Build locally

```bash
docker compose -f infra/docker/docker-compose.build.yml build
# Heavy images (torch / openai+anthropic) — build on their own if needed:
docker compose -f infra/docker/docker-compose.build.yml build ml-worker research-agent
```

## 2. Log in to ECR + push

```bash
ACCOUNT=<aws-account-id>; REGION=us-east-1
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

for app in api ingest-worker oms-worker ml-worker backtest-worker research-agent; do
  docker tag "saalr/$app:local" "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/saalr-dev-$app:latest"
  docker push "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/saalr-dev-$app:latest"
done
```

## 3. Set secrets + vars, then apply

- Populate Secrets Manager (`saalr/app/openai`, `/anthropic`, `/massive`, `/fred`) and the
  RDS-managed DB secret.
- Set a globally-unique `bucket_prefix` and the bootstrap state bucket/lock table in
  `infra/terraform/environments/dev`.

```bash
terraform -chdir=infra/terraform/environments/dev init
terraform -chdir=infra/terraform/environments/dev apply
```

## Notes

- `ml-worker` bundles torch + transformers and downloads the ~440MB FinBERT model into the HF cache
  on first run (pre-baking the model layer is a future optimization).
- The web app is **not** containerized — it is static (`apps/web` `npm run build` → `dist/client`),
  deploy to S3/CloudFront (separate slice).
```

- [ ] **Step 3: commit**

```bash
git add infra/docker/docker-compose.build.yml docs/runbooks/go-live-images.md
git commit -m "build(infra): build-all compose + go-live images runbook

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: verification (lint all + build the light images + smoke)

No new commit unless a Dockerfile needs a fix.

- [ ] **Step 1: lint all five** new Dockerfiles with hadolint → no errors (warnings OK if the
  `ingest-worker` Dockerfile produces the same class).

- [ ] **Step 2: build the lightweight images** (shared saalr-core; api also saalr-ml/-content):

```bash
docker compose -f infra/docker/docker-compose.build.yml build oms-worker backtest-worker api
```
Expected: all three build successfully.

- [ ] **Step 3: import / CLI smoke** (no DB needed):

```bash
docker run --rm saalr/oms-worker:local --help
docker run --rm saalr/backtest-worker:local --help
docker run --rm --entrypoint uv saalr/api:local run --no-sync python -c "import saalr_api.main; assert callable(saalr_api.main.create_app)"
```
Expected: the worker `--help` prints CLI usage and exits 0; the api import line exits 0.
If a worker CLI lacks `--help`, substitute the same import smoke (`--entrypoint uv … python -c "import <pkg>"`).

- [ ] **Step 4: record results.** Report which images built + smoked, and note `ml-worker` /
  `research-agent` as lint-passed + documented-manual (heavy builds). If any build fails, fix the
  Dockerfile and amend the relevant task's commit.

---

## Self-Review notes (for the executor)

- **Don't touch Terraform** — this slice only adds Dockerfiles, a build compose, and a runbook. The
  `command`/port contracts are documented in the runbook, not changed in `.tf`.
- **Entrypoint ↔ ECS command:** the ENTRYPOINT is `python -m <pkg>` (no subcommand baked in) so the
  Terraform `command=[...]` appends the right subcommand. The API has no ECS command (ALB service).
- **uvicorn `--factory`** is required — `saalr_api.main` exposes `create_app()`, not a module-level `app`.
- **hadolint** runs dockerized (no host install needed). The existing `ingest-worker` Dockerfile is the
  warning baseline.
- **Heavy builds:** `ml-worker` (torch) and `research-agent` (openai+anthropic) are lint-only in-gate
  and documented as manual; building them here can take many minutes.
```
