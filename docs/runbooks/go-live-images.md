# Go-live: build & push the service images

Builds the Saalr container images and pushes them to the ECR repositories the dev Terraform
provisions, then applies the stack. Images: `api`, `ingest-worker`, `oms-worker`, `ml-worker`,
`backtest-worker`, `research-agent`, `content-worker`.

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

for app in api ingest-worker oms-worker ml-worker backtest-worker research-agent content-worker; do
  docker tag "saalr/$app:local" "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/saalr-dev-$app:latest"
  docker push "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/saalr-dev-$app:latest"
done
```

## 3. Set secrets + vars, then apply

- Populate Secrets Manager (`saalr/app/openai`, `/anthropic`, `/massive`, `/fred`) and the
  RDS-managed DB secret.
- Set a globally-unique `bucket_prefix` and the bootstrap state bucket / lock table in
  `infra/terraform/environments/dev`.

```bash
terraform -chdir=infra/terraform/environments/dev init
terraform -chdir=infra/terraform/environments/dev apply
```

## content-worker — one-off reindex

`content-worker` rebuilds the OptionsAcademy embeddings index; it is content-change-driven, not a
scheduled or long-running worker (so it is intentionally NOT in the Terraform `workers` module). Its
ECR repo (`saalr-dev-content-worker`) is already declared in `module.compute` `ecr_repo_names`. Run it
on demand, either locally against the DB:

```bash
docker run --rm \
  -e APP_DATABASE_URL=postgresql+asyncpg://... -e OPENAI_API_KEY=... \
  saalr/content-worker:local reindex
```

or as a one-off `aws ecs run-task` (register a task def for the image with `command=["reindex"]`,
reusing the shared execution/task roles + the `saalr/app/openai` secret).

## Notes

- **Live Stripe billing:** the API package keeps `stripe` an optional extra (billing degrades to a
  503 when it is absent). To ship working billing, build the API image with the extra —
  change the `uv sync` line in `apps/api/Dockerfile` to `uv sync --frozen --package saalr-api --extra stripe`.
- `ml-worker` bundles torch + transformers and downloads the ~440MB FinBERT model into the HF cache
  on first run (pre-baking the model layer is a future optimization).
- The web app is **not** containerized — it is static (`apps/web`: `npm run build` -> `dist/client`),
  deploy to S3/CloudFront (separate slice).
