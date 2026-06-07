# AWS-2c — Secrets + storage Terraform module (KMS + S3 + Secrets Manager) (design)

**Status:** approved 2026-06-03
**Slice:** AWS-2c (third sub-slice of the Terraform foundation; HLD ADR-008 / §4 model storage / §audit / §config secrets)
**Builds on:** AWS-2a (skeleton + network), AWS-2b (data). Provides the encryption key, object storage, and secret containers the app (AWS-1's S3TranscriptStore + SecretsManagerResolver) and later modules (AWS-2d) consume.

## Goal

Provision a `modules/storage/` with: a **KMS customer-managed key** (rotation on), **three S3 buckets** (transcripts, ml-models, audit — the last with Object Lock), and **Secrets Manager secret containers** (values set out-of-band, never in Terraform state). Wired into the `dev` environment. Same **validate-only** acceptance as AWS-2a/2b (Docker `fmt`/`validate`/`tflint`, no `apply`, no AWS account, no spend).

## Approved decisions

1. **One `modules/storage/`** — KMS + S3 + Secrets Manager together (the CMK encrypts both buckets and secrets; cohesive).
2. **Audit Object Lock = GOVERNANCE default + `var` for COMPLIANCE** — Object Lock is enabled at bucket creation (versioned), with `default_retention { mode = var.audit_object_lock_mode (default "GOVERNANCE"), days = var.audit_retention_days (default 365) }`. GOVERNANCE is bypassable-with-permission so a dev stack can be cleaned; prod sets `"COMPLIANCE"` per the HLD.
3. **Three buckets** — transcripts (RA-3c S3 backend, in use), audit (compliance archive), ml-models (HLD §4; forward-looking, no consumer until an ML-infra slice).

Settled (stated in the design, not re-litigated): secrets are **empty containers only** (no `aws_secretsmanager_secret_version`; values via `aws secretsmanager put-secret-value` out-of-band); **one KMS CMK** with `enable_key_rotation = true` encrypts buckets + secrets; bucket names need a globally-unique prefix (`var.bucket_prefix`, set a unique suffix).

## `modules/storage/`

Standalone module (no `module.network`/`module.data` inputs). `versions.tf` mirrors the others (`terraform >= 1.6`, `aws ~> 5.0`).

### `variables.tf`

| variable | type | default | purpose |
|----------|------|---------|---------|
| `name_prefix` | string | — | resource/tag/alias prefix (e.g. `saalr-dev`) |
| `bucket_prefix` | string | — | globally-unique S3 bucket name prefix (set a unique suffix) |
| `audit_object_lock_mode` | string | `"GOVERNANCE"` | audit bucket retention mode (`GOVERNANCE`/`COMPLIANCE`) |
| `audit_retention_days` | number | `365` | audit Object Lock default retention |
| `secret_names` | list(string) | `["saalr/brokers/alpaca-paper", "saalr/app/openai", "saalr/app/anthropic", "saalr/app/massive", "saalr/app/fred"]` | Secrets Manager secret containers to create |
| `secret_recovery_window_days` | number | `7` | SM secret recovery window |
| `kms_deletion_window_days` | number | `30` | KMS key deletion window |
| `tags` | map(string) | `{}` | merged onto every resource |

### `main.tf`

```hcl
# --- KMS ---
resource "aws_kms_key" "this" {
  description             = "${var.name_prefix} data encryption key"
  enable_key_rotation     = true
  deletion_window_in_days = var.kms_deletion_window_days
  tags                    = merge(var.tags, { Name = "${var.name_prefix}-kms" })
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.this.key_id
}

# --- S3 buckets ---
resource "aws_s3_bucket" "transcripts" {
  bucket = "${var.bucket_prefix}-transcripts"
  tags   = merge(var.tags, { Name = "${var.bucket_prefix}-transcripts" })
}

resource "aws_s3_bucket" "ml_models" {
  bucket = "${var.bucket_prefix}-ml-models"
  tags   = merge(var.tags, { Name = "${var.bucket_prefix}-ml-models" })
}

resource "aws_s3_bucket" "audit" {
  bucket              = "${var.bucket_prefix}-audit"
  object_lock_enabled = true
  tags                = merge(var.tags, { Name = "${var.bucket_prefix}-audit" })
}

locals {
  buckets = {
    transcripts = aws_s3_bucket.transcripts.id
    ml_models   = aws_s3_bucket.ml_models.id
    audit       = aws_s3_bucket.audit.id
  }
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = local.buckets
  bucket   = each.value
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets
  bucket   = each.value
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = local.buckets
  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    default_retention {
      mode = var.audit_object_lock_mode
      days = var.audit_retention_days
    }
  }
  depends_on = [aws_s3_bucket_versioning.this]
}

# --- Secrets Manager (containers only; values set out-of-band) ---
resource "aws_secretsmanager_secret" "this" {
  for_each                = toset(var.secret_names)
  name                    = each.value
  description             = "Managed by Terraform; value set out-of-band (never in state)."
  kms_key_id              = aws_kms_key.this.arn
  recovery_window_in_days = var.secret_recovery_window_days
  tags                    = merge(var.tags, { Name = each.value })
}
```

- The common bucket config (versioning / SSE-KMS / public-access-block) is `for_each`'d over `local.buckets` so all three buckets get versioning + KMS encryption (`bucket_key_enabled` to cut KMS request cost) + full public-access-block.
- `aws_s3_bucket_object_lock_configuration.audit` `depends_on` the versioning resources (Object Lock requires versioning; the bucket itself sets `object_lock_enabled = true` at creation).
- Secrets are **containers only** — no `aws_secretsmanager_secret_version`, so values never enter state. Each is KMS-encrypted with the CMK.

### `outputs.tf`

```hcl
output "kms_key_arn"        { value = aws_kms_key.this.arn }
output "kms_key_id"         { value = aws_kms_key.this.key_id }
output "kms_alias"          { value = aws_kms_alias.this.name }
output "transcripts_bucket" { value = aws_s3_bucket.transcripts.id }
output "ml_models_bucket"   { value = aws_s3_bucket.ml_models.id }
output "audit_bucket"       { value = aws_s3_bucket.audit.id }
output "secret_arns"        { value = { for k, s in aws_secretsmanager_secret.this : k => s.arn } }
```

## Dev environment wiring

`environments/dev/main.tf` adds, after `module "data"`:
```hcl
module "storage" {
  source        = "../../modules/storage"
  name_prefix   = "saalr-dev"
  bucket_prefix = "saalr-dev" # globally-unique — set a unique suffix before apply
}
```
`environments/dev/outputs.tf` adds re-exports:
```hcl
output "transcripts_bucket" { value = module.storage.transcripts_bucket }
output "audit_bucket"       { value = module.storage.audit_bucket }
output "kms_key_arn"        { value = module.storage.kms_key_arn }
output "secret_arns"        { value = module.storage.secret_arns }
```
(The storage module's defaults cover the audit/secret/KMS knobs; no new dev `variables.tf`/`tfvars` entries required.)

### App connection (deploy-time, not Terraform)

- AWS-2d's ECS task definition sets `TRANSCRIPT_S3_BUCKET` to the `transcripts_bucket` output, which lights up AWS-1's `S3TranscriptStore` (`make_transcript_store` returns the S3 store when `transcript_s3_bucket` is set).
- Broker accounts set `credential_ref = "secretsmanager:saalr/brokers/alpaca-paper"`, resolved by AWS-1's `SecretsManagerResolver` against the secret this module creates (value populated out-of-band).
- The ECS task role (AWS-2d) is granted `s3:*Object` on the buckets, `secretsmanager:GetSecretValue` on the secrets, and `kms:Decrypt`/`Encrypt` on the CMK — those IAM grants live with the roles in AWS-2d.

## Verification model

Validate-only, via Docker from the repo root (PowerShell tool; spaced-path caveat from AWS-2a):
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/storage hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/storage hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work ghcr.io/terraform-linters/tflint --recursive
```
Validating `environments/dev` now initializes `modules/network` + `modules/data` + `modules/storage` together. `init`/`validate` download the AWS provider (network) but need no AWS credentials. No `apply`/`plan`.

## README / docs

`infra/terraform/README.md` gains a `modules/storage/` line in the Layout block and a short **"Secrets & storage (AWS-2c)"** note: the KMS CMK encrypts the buckets + secrets; the three buckets (transcripts = RA-3c S3 backend, audit = Object Lock archive, ml-models = forward-looking); secret **containers** are created here but their **values are set out-of-band** (`aws secretsmanager put-secret-value --secret-id saalr/brokers/alpaca-paper --secret-string '{"key":"...","secret":"..."}'`); bucket names need a globally-unique `bucket_prefix`; and the app wires `TRANSCRIPT_S3_BUCKET` + the `secretsmanager:` refs at deploy time (AWS-2d).

## Out of scope (AWS-2d → 2e / later)

IAM policies/roles granting ECS access to the buckets/secrets/CMK (AWS-2d, with the task roles); S3 lifecycle policies (retention, noncurrent-version expiry, transcript TTL); re-keying RDS/Redis from the AWS-managed key to this CMK; bucket replication / cross-region; KMS key policies beyond the default (e.g. cross-account); the actual secret values; per-secret rotation Lambdas; the `prod` environment; `terraform plan`/`apply`.
