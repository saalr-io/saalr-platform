# Terraform — Saalr cloud foundation

AWS single-cloud (ADR-008), region `us-east-1`. Terraform `>= 1.6`, AWS provider `~> 5.0`.

## Layout

    bootstrap/            one-time: creates the S3 state bucket + DynamoDB lock table (local state)
    modules/network/      VPC, subnets, IGW, single NAT, route tables (outputs consumed by later modules)
    modules/data/         RDS Postgres + ElastiCache Redis + subnet groups + security groups
    modules/storage/      KMS CMK + S3 buckets (transcripts/audit/ml-models) + Secrets Manager containers
    modules/compute/      ECR repos + ECS cluster + IAM task/exec roles + CloudWatch logs + ECS app SG
    modules/api_service/  internet-facing ALB + target group + listener + API ECS task def + Fargate service
    modules/workers/      worker task defs + EventBridge scheduled tasks + long-running consumer services
    environments/dev/     dev stack: S3 backend + the network/data/storage/compute/api_service/workers modules

## Database (TimescaleDB note)

The app uses TimescaleDB for the `bars` hypertable, but **AWS RDS for PostgreSQL does
not support the TimescaleDB extension**. AWS-2b provisions managed RDS Postgres, where
`bars` runs as a plain Postgres table (queries are correct; only the time-partitioning
optimization is absent). The migrations that `CREATE EXTENSION timescaledb` /
`create_hypertable(...)` need an RDS-specific guard or path before applying to RDS. The
hypertable optimization at scale is a deferred decision: native `pg_partman` partitioning,
or Timescale Cloud (off-AWS). The RDS master password is **managed by RDS in Secrets
Manager** (the module's `db_master_user_secret_arn` output) — the app reads it at deploy
time to build `APP_DATABASE_URL`; no password lives in Terraform state.

## Secrets & storage (AWS-2c)

A KMS customer-managed key encrypts the S3 buckets and the Secrets Manager secrets. Three
buckets: `*-transcripts` (the RA-3c `S3TranscriptStore` backend), `*-audit` (Object Lock,
GOVERNANCE in dev / COMPLIANCE in prod), `*-ml-models` (forward-looking). Bucket names need
a globally-unique `bucket_prefix`.

Secret **containers** are created here, but their **values are set out-of-band** (never in
Terraform state), e.g.:

    aws secretsmanager put-secret-value --secret-id saalr/brokers/alpaca-paper \
      --secret-string '{"key":"<ALPACA_KEY>","secret":"<ALPACA_SECRET>"}'

At deploy time (AWS-2d), the app wires `TRANSCRIPT_S3_BUCKET` to the transcripts-bucket output
(lighting up `S3TranscriptStore`) and points broker `credential_ref`s at
`secretsmanager:saalr/brokers/...`. The ECS task-role IAM grants for the buckets/secrets/key
land with the roles in AWS-2d.

## Compute foundation (AWS-2d-1)

`modules/compute/` provides the shared compute substrate: an ECR repo per deployable image
(`api`, the workers), an ECS Fargate cluster (Container Insights on), a CloudWatch log group,
and two IAM roles — the **execution role** (ECR pull + log write + secret injection) and the
**task role** (runtime `s3:*Object`/`ListBucket` on the AWS-2c buckets, `secretsmanager:GetSecretValue`
on the secrets, `kms:Decrypt`/`GenerateDataKey` on the CMK). It also creates the **ECS app
security group** (egress-all; ALB ingress is added in AWS-2d-2), and the data tier now accepts
SG-to-SG ingress from it (`modules/data` `app_security_group_id`). Task definitions, services,
the internal ALB, and EventBridge scheduled tasks land in AWS-2d-2/2d-3.

## API service (AWS-2d-2)

`modules/api_service/` runs the API monolith on ECS Fargate behind an **internet-facing ALB**
(public subnets, HTTP:80 — HTTPS/ACM is a later hardening). The ALB SG allows 80 from the
internet; the ECS app SG accepts the container port (8000) only from the ALB SG; tasks run in
private subnets (`assign_public_ip = false`) and register with the target group (health check
`/healthz`). The task definition pulls the `api` image from ECR, logs to the compute log group,
and runs under the compute task/execution roles.

**Container config (deploy-time):** the env (`AWS_REGION`, `REDIS_URL`, `TRANSCRIPT_S3_BUCKET`,
`DB_HOST/PORT/USER/NAME`) + secrets (the four `saalr/app/*` API keys, and `DB_PASSWORD` pulled
from the RDS-managed secret's `password` JSON key) are passed by the dev env. Note: RDS manages
the password as a Secrets-Manager JSON blob that can't be interpolated into a single env, so the
app builds `APP_DATABASE_URL` from `DB_HOST/PORT/USER/NAME/PASSWORD` at startup — a small
app-config follow-up before the first real deploy.

## Workers (AWS-2d-3)

`modules/workers/` provisions the background workers on Fargate, in two shapes:
- **Scheduled** (EventBridge `cron`/`rate` → `ecs:RunTask` via an invoke role): `ingest-worker`
  (daily 21:30 UTC), `oms-reconcile` (every 5 min), `sentiment` (daily 22:00 UTC).
- **Long-running consumers** (Fargate services, no ALB): `backtest-worker`, `research-agent`
  (Redis-queue consumers, `desired_count = 1`).

All share the API's env/secrets contract (DB/Redis/S3/LLM/market) and run in private subnets
under the app SG + compute task/execution roles. `cpu`/`memory` are shared defaults
(`512`/`1024`) — per-worker sizing (e.g. more memory for the torch-based `ml-worker`) is a later
refinement. The EventBridge invoke role is scoped to `ecs:RunTask` on the scheduled task defs +
`iam:PassRole` on the two ECS roles.

Set a globally-unique bucket name first (e.g. append your account id), then:

    cd bootstrap
    terraform init
    terraform apply        # creates the state bucket + lock table

Put the resulting bucket/table names into each environment's `backend "s3"` block.

## Per-environment

    cd environments/dev
    terraform init         # uses the S3 backend
    terraform plan         # review; `apply` provisions BILLABLE infra (single NAT ~= $32/mo)

## Static validation (no AWS account, no spend) — the CI/acceptance gate

Run via Docker from the repo root (the AWS provider is downloaded by `init`; no creds needed):

    docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
    docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 init -backend=false
    docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 validate
    docker run --rm -v "${PWD}\infra\terraform:/work" -w /work ghcr.io/terraform-linters/tflint --recursive

`apply` is run deliberately by an operator against a funded account — never in CI for this slice.
