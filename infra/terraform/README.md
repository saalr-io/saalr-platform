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
    modules/cicd/         GitHub Actions OIDC provider + a scoped deploy role (ECR push + ECS deploy)
    environments/dev/     dev stack: network/data/storage/compute/api_service/workers/cicd modules

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

## CI/CD (AWS-2e)

`modules/cicd/` creates a **GitHub Actions OIDC provider** (`token.actions.githubusercontent.com`)
and a **deploy role** that GH Actions assumes via OIDC — scoped by `sub` to
`repo:spayyavula/saalr-platform:*`, granting ECR push (on the project's repos), ECS
deploy (`RegisterTaskDefinition`/`UpdateService`/...), and `iam:PassRole` on the ECS roles. No
long-lived AWS keys in GitHub. (`create_oidc_provider = false` if the account already has the
GitHub OIDC provider.)

The deploy workflow is `.github/workflows/deploy.yml` (a **manual-trigger template** — switch
`workflow_dispatch` to `push: branches: [master]` to activate). Before it works: `terraform
apply` the stack, set the repo secret `AWS_DEPLOY_ROLE_ARN` to the `gha_deploy_role_arn` output,
and add a Dockerfile per app (only `apps/ingest-worker` has one today — the rest are a
build-tooling follow-up). Scheduled-worker image updates go through a task-def re-register
(`terraform apply`), not `update-service`.

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

## Production environment (`environments/prod/`, domain `saalr.io`)

`environments/prod/` composes the **same modules** as dev (`name_prefix = "saalr-prod"`,
`Environment = prod` tags, VPC CIDR `10.1.0.0/16` so it never overlaps dev's `10.0.0.0/16`), with
prod hardening flipped on: `db_multi_az = true`, `db_deletion_protection = true`,
`db_skip_final_snapshot = false`, `db_instance_class = "db.t4g.small"`. It additionally creates a
**Terraform-managed Route 53 hosted zone for `saalr.io`** and wires it into the `web` module, which
already provisions the ACM cert (us-east-1, DNS-validated), the CloudFront alias, and the
`/api/*` → ALB origin (a CloudFront Function strips the `/api` prefix).

**Audit Object Lock:** prod ships `audit_object_lock_mode = "GOVERNANCE"` (immutable, but a root
principal can override) — chosen for the beta so the stack can still be torn down. Switch to
`"COMPLIANCE"` only when going to regulated production: COMPLIANCE is **irreversible**, and audit
objects (and the bucket) cannot be deleted until their retention expires (`audit_retention_days`,
default 365), even by root.

### First apply — order matters (DNS delegation gates the cert)

The ACM cert validates by writing DNS records into the new `saalr.io` zone, but validation only
completes once that zone is authoritative — i.e. after you delegate NS at the **external
registrar**. So create the zone first, delegate, then apply the rest:

    cd environments/prod
    # 1. set a GLOBALLY-UNIQUE bucket_prefix in terraform.tfvars (e.g. append your account id)
    terraform init \
      -backend-config="bucket=<state_bucket>" \
      -backend-config="dynamodb_table=<lock_table>"   # reuse the same bootstrap bucket/table as dev

    # 2. create ONLY the hosted zone, then read its name servers
    terraform apply -target=aws_route53_zone.primary
    terraform output route53_name_servers
    #    -> set these 4 NS records at the saalr.io registrar; wait for propagation:
    #       dig +short NS saalr.io @8.8.8.8   (should return the AWS ns-*.awsdns-* set)

    # 3. apply the full stack (cert validation now resolves against the delegated zone)
    terraform plan        # review; provisions BILLABLE infra
    terraform apply

### After apply

- Set secret **values** out-of-band (never in state): the `saalr/app/*` keys and broker secrets,
  e.g. `aws secretsmanager put-secret-value --secret-id saalr/app/massive --secret-string '...'`.
- Set the GitHub repo secret `AWS_DEPLOY_ROLE_ARN` to the `gha_deploy_role_arn` output, then build
  & push the per-app images and roll the ECS services (see `.github/workflows/deploy.yml`).
- `saalr.io` resolves to CloudFront once the alias record + cert are live; the API is reachable
  same-origin at `https://saalr.io/api/*`.
