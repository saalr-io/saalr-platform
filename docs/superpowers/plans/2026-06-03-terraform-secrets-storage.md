# AWS-2c — Secrets + storage Terraform module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. This is Terraform (HCL) — acceptance is `terraform fmt`/`validate` + `tflint` via Docker (no `apply`, no AWS account). No pytest.

**Goal:** A `modules/storage/` (KMS CMK + 3 S3 buckets [transcripts/ml-models/audit-with-Object-Lock] + Secrets Manager secret containers) wired into the `dev` environment, validated statically.

**Architecture:** `infra/terraform/modules/storage/` (standalone — no upstream module deps) + a `module "storage"` call in `environments/dev/`. One CMK encrypts all buckets (SSE-KMS) + secrets; secrets are containers only (no values in state). `terraform >= 1.6`, `aws ~> 5.0`.

**Tech Stack:** Terraform (HCL), AWS provider v5, Docker (terraform/tflint images).

**Spec:** `docs/superpowers/specs/2026-06-03-terraform-secrets-storage-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F` (path has a SPACE: `SAALR F2F`).
- **Run Docker terraform/tflint via the PowerShell tool** (native Windows path), from the repo root:
  ```powershell
  docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/<subdir> hashicorp/terraform:1.9 <cmd>
  ```
  `init -backend=false` + `validate` download the AWS provider (network) but need NO AWS credentials. AWS-2a/2b confirmed Docker works here. Temp-dir-without-space fallback if the spaced mount fails.
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files (+ a `.terraform.lock.hcl` if `init` creates one). NEVER `git add -A`/`.`. **NEVER stage `.terraform/` or `*.tfstate*`** (git-ignored by `infra/terraform/.gitignore`). Never stage the root `.gitignore`, `.env`, `uv.lock`, or `tools/`.

---

### Task 1: `modules/storage` (KMS + S3 + Secrets Manager)

**Files:**
- Create: `infra/terraform/modules/storage/versions.tf`
- Create: `infra/terraform/modules/storage/variables.tf`
- Create: `infra/terraform/modules/storage/main.tf`
- Create: `infra/terraform/modules/storage/outputs.tf`

- [ ] **Step 1: Write the module**

Create `infra/terraform/modules/storage/versions.tf`:
```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```

Create `infra/terraform/modules/storage/variables.tf`:
```hcl
variable "name_prefix" {
  description = "Prefix for resource names, tags, and the KMS alias."
  type        = string
}

variable "bucket_prefix" {
  description = "Globally-unique S3 bucket name prefix (set a unique suffix, e.g. your account id)."
  type        = string
}

variable "audit_object_lock_mode" {
  description = "Object Lock retention mode for the audit bucket (GOVERNANCE for dev, COMPLIANCE for prod)."
  type        = string
  default     = "GOVERNANCE"
}

variable "audit_retention_days" {
  description = "Default Object Lock retention (days) for the audit bucket."
  type        = number
  default     = 365
}

variable "secret_names" {
  description = "Secrets Manager secret containers to create (values are set out-of-band, never in state)."
  type        = list(string)
  default = [
    "saalr/brokers/alpaca-paper",
    "saalr/app/openai",
    "saalr/app/anthropic",
    "saalr/app/massive",
    "saalr/app/fred",
  ]
}

variable "secret_recovery_window_days" {
  description = "Recovery window (days) for deleted secrets."
  type        = number
  default     = 7
}

variable "kms_deletion_window_days" {
  description = "Deletion window (days) for the KMS key."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
```

Create `infra/terraform/modules/storage/main.tf`:
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

Create `infra/terraform/modules/storage/outputs.tf`:
```hcl
output "kms_key_arn" {
  description = "ARN of the data-encryption KMS key."
  value       = aws_kms_key.this.arn
}

output "kms_key_id" {
  description = "Id of the KMS key."
  value       = aws_kms_key.this.key_id
}

output "kms_alias" {
  description = "Alias of the KMS key."
  value       = aws_kms_alias.this.name
}

output "transcripts_bucket" {
  description = "Name of the research-transcripts bucket."
  value       = aws_s3_bucket.transcripts.id
}

output "ml_models_bucket" {
  description = "Name of the ML-models bucket."
  value       = aws_s3_bucket.ml_models.id
}

output "audit_bucket" {
  description = "Name of the audit-log (Object Lock) bucket."
  value       = aws_s3_bucket.audit.id
}

output "secret_arns" {
  description = "Map of secret name => ARN for the created Secrets Manager containers."
  value       = { for k, s in aws_secretsmanager_secret.this : k => s.arn }
}
```

- [ ] **Step 2: Validate the module standalone (Docker, via PowerShell tool)**

From the repo root:
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/storage hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/storage hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
```
Expected: `validate` → `Success! The configuration is valid.` (validates against the AWS provider schema — catches wrong attribute names/types on `aws_kms_key`, `aws_s3_bucket_object_lock_configuration`, `aws_secretsmanager_secret`, the `for_each`/`bucket_key_enabled` usages, etc.). `fmt -check` exits 0. If `fmt -check` flags files, run `docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -recursive` then re-check. Report the EXACT validate output. If validate errors (e.g. an attribute that does not exist in v5), fix the HCL to match the provider schema and re-run — do not leave it failing.

- [ ] **Step 3: Commit**

Confirm `git status` shows no `.terraform/`/`*.tfstate` staged. Then:
```bash
git add infra/terraform/modules/storage/versions.tf infra/terraform/modules/storage/variables.tf infra/terraform/modules/storage/main.tf infra/terraform/modules/storage/outputs.tf
git add infra/terraform/modules/storage/.terraform.lock.hcl 2>/dev/null || true
git commit -m "feat(aws): terraform storage module — KMS + S3 buckets + Secrets Manager (AWS-2c)"
```
(Append the Co-Authored-By footer. Verify with `git show --stat HEAD` that no `.terraform/`/`*.tfstate` was committed.)

---

### Task 2: Wire the storage module into dev + README + whole-tree validation

**Files:**
- Modify: `infra/terraform/environments/dev/main.tf` (add `module "storage"`)
- Modify: `infra/terraform/environments/dev/outputs.tf` (re-export storage outputs)
- Modify: `infra/terraform/README.md` (storage module line + secrets/storage note)

- [ ] **Step 1: Add the `module "storage"` call**

In `infra/terraform/environments/dev/main.tf`, append AFTER the existing `module "data"` block:
```hcl
module "storage" {
  source        = "../../modules/storage"
  name_prefix   = "saalr-dev"
  bucket_prefix = "saalr-dev" # globally-unique — set a unique suffix before apply
}
```
(Leave the `terraform`, `provider`, `module "network"`, and `module "data"` blocks unchanged.)

- [ ] **Step 2: Re-export the storage outputs**

In `infra/terraform/environments/dev/outputs.tf`, append (keep the existing network + data outputs):
```hcl
output "transcripts_bucket" {
  value = module.storage.transcripts_bucket
}

output "audit_bucket" {
  value = module.storage.audit_bucket
}

output "kms_key_arn" {
  value = module.storage.kms_key_arn
}

output "secret_arns" {
  value = module.storage.secret_arns
}
```

- [ ] **Step 3: Update the README**

In `infra/terraform/README.md`:
- In the `## Layout` block, add a `modules/storage/` line right after the `modules/data/` line:
```
    modules/storage/      KMS CMK + S3 buckets (transcripts/audit/ml-models) + Secrets Manager containers
```
- Add a new section after the `## Database (TimescaleDB note)` section (before `## One-time bootstrap`):
```markdown
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
```

- [ ] **Step 4: Validate dev (network + data + storage) + fmt + tflint**

From the repo root (PowerShell tool):
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work ghcr.io/terraform-linters/tflint --recursive
```
Expected: `init -backend=false` initializes the provider + `../../modules/{network,data,storage}`; `validate` → `Success! The configuration is valid.`; `fmt -check` exits 0; `tflint --recursive` reports no errors (best-effort — `validate` is the hard gate). Report the EXACT validate output + the tflint outcome. Fix any `fmt` diff with `... fmt -recursive`.

- [ ] **Step 5: Commit**

Confirm no `.terraform/`/`*.tfstate` staged. Then:
```bash
git add infra/terraform/environments/dev/main.tf infra/terraform/environments/dev/outputs.tf infra/terraform/README.md
git commit -m "feat(aws): wire the storage module into the dev environment + README (AWS-2c)"
```
(Append the Co-Authored-By footer. Verify with `git show --stat HEAD` that exactly those 3 files committed, no `.terraform/`/state.)

---

## Final verification (after all tasks)

From the repo root (PowerShell tool):
- [ ] `fmt -check -recursive` on `/work` — exit 0.
- [ ] `modules/storage`: `init -backend=false` + `validate` → valid.
- [ ] `environments/dev`: `init -backend=false` + `validate` → valid (network + data + storage together).
- [ ] `tflint --recursive` — no errors (best-effort).
- [ ] `git status` clean of `.terraform/` + `*.tfstate*`; the new `.terraform.lock.hcl` (if any) tracked.
- [ ] **Final code-review subagent** over the whole AWS-2c diff (HCL correctness, security posture, no-secret-in-state, the outputs contract).

## Self-review notes
- **Spec coverage:** storage module — KMS CMK + 3 buckets (versioning/SSE-KMS/public-block via for_each; audit Object Lock GOVERNANCE-default) + secret containers (no versions) + outputs (T1); dev wiring + storage output re-exports + README secrets/storage note (T2); validate-only acceptance. All spec sections map to a task.
- **Consistency:** the storage module's variables (`name_prefix`, `bucket_prefix`, `audit_object_lock_mode`, …) match the dev env's `module "storage"` call (which relies on defaults for the rest); the module outputs (`transcripts_bucket`, `audit_bucket`, `kms_key_arn`, `secret_arns`) match the dev env's re-exports.
- **Deliberate choices flagged for the reviewer:** **no `aws_secretsmanager_secret_version`** (values out-of-band; nothing secret in state); audit Object Lock GOVERNANCE default (COMPLIANCE via var for prod); SSE-KMS with `bucket_key_enabled` (cost) on all buckets + full public-access-block; one CMK with rotation; bucket names need a unique `bucket_prefix`; IAM grants deferred to AWS-2d; validate-only (no `apply`).
- **Environment caveat:** the checks need Docker + network (to pull the terraform/tflint images + the AWS provider). If unavailable, hand-verify the HCL against the spec and have the reviewer scrutinize it.
