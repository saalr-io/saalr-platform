# Terraform — Saalr cloud foundation

AWS single-cloud (ADR-008), region `us-east-1`. Terraform `>= 1.6`, AWS provider `~> 5.0`.

## Layout

    bootstrap/            one-time: creates the S3 state bucket + DynamoDB lock table (local state)
    modules/network/      VPC, subnets, IGW, single NAT, route tables (outputs consumed by later modules)
    modules/data/         RDS Postgres + ElastiCache Redis + subnet groups + security groups
    modules/storage/      KMS CMK + S3 buckets (transcripts/audit/ml-models) + Secrets Manager containers
    environments/dev/     dev stack: S3 backend + the network, data, and storage modules

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

## One-time bootstrap (creates remote state)

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
