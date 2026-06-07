# AWS-2b — Data-layer Terraform module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. This is Terraform (HCL) — acceptance is `terraform fmt`/`validate` + `tflint` via Docker (no `apply`, no AWS account). No pytest.

**Goal:** A `modules/data/` module (RDS Postgres + single-node ElastiCache Redis + subnet groups + security groups) consuming the AWS-2a network module's outputs, wired into the `dev` environment, validated statically.

**Architecture:** `infra/terraform/modules/data/` (RDS-managed master password in Secrets Manager; SGs via v5 `aws_vpc_security_group_*_rule` resources) + a `module "data"` call in `environments/dev/`. `terraform >= 1.6`, `aws ~> 5.0`.

**Tech Stack:** Terraform (HCL), AWS provider v5, Docker (terraform/tflint images).

**Spec:** `docs/superpowers/specs/2026-06-03-terraform-data-layer-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F` (path has a SPACE: `SAALR F2F`).
- **Run Docker terraform/tflint via the PowerShell tool** (native Windows path), from the repo root:
  ```powershell
  docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/<subdir> hashicorp/terraform:1.9 <cmd>
  ```
  `init -backend=false` + `validate` download the AWS provider (network) but need NO AWS credentials. AWS-2a confirmed Docker works here. Temp-dir-without-space fallback if the spaced mount fails.
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files (+ a `.terraform.lock.hcl` if `init` creates one). NEVER `git add -A`/`.`. **NEVER stage `.terraform/` or `*.tfstate*`** (git-ignored by `infra/terraform/.gitignore`). Never stage the root `.gitignore`, `.env`, `uv.lock`, or `tools/`.

---

### Task 1: `modules/data` (RDS Postgres + ElastiCache Redis)

**Files:**
- Create: `infra/terraform/modules/data/versions.tf`
- Create: `infra/terraform/modules/data/variables.tf`
- Create: `infra/terraform/modules/data/main.tf`
- Create: `infra/terraform/modules/data/outputs.tf`

- [ ] **Step 1: Write the module**

Create `infra/terraform/modules/data/versions.tf`:
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

Create `infra/terraform/modules/data/variables.tf`:
```hcl
variable "name_prefix" {
  description = "Prefix for resource names and tags."
  type        = string
}

variable "vpc_id" {
  description = "VPC id (from the network module)."
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block (default SG ingress source)."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet ids for the DB/cache subnet groups."
  type        = list(string)
}

variable "ingress_cidr_blocks" {
  description = "CIDR blocks allowed to reach the data tier; empty => [vpc_cidr]."
  type        = list(string)
  default     = []
}

variable "db_engine_version" {
  description = "Postgres major version."
  type        = string
  default     = "16"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage (GB, gp3)."
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "saalr"
}

variable "db_username" {
  description = "Master username (password is RDS-managed in Secrets Manager)."
  type        = string
  default     = "saalr_admin"
}

variable "db_multi_az" {
  description = "Multi-AZ RDS (prod on, dev off)."
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "RDS deletion protection (dev off so destroy works)."
  type        = bool
  default     = false
}

variable "db_skip_final_snapshot" {
  description = "Skip the final snapshot on destroy (dev true)."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "RDS automated backup retention (days)."
  type        = number
  default     = 7
}

variable "redis_engine_version" {
  description = "ElastiCache Redis engine version."
  type        = string
  default     = "7.1"
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
```

Create `infra/terraform/modules/data/main.tf`:
```hcl
locals {
  ingress_cidrs = length(var.ingress_cidr_blocks) > 0 ? var.ingress_cidr_blocks : [var.vpc_cidr]
}

# --- Postgres (RDS) ---
resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db"
  subnet_ids = var.private_subnet_ids
  tags       = merge(var.tags, { Name = "${var.name_prefix}-db-subnets" })
}

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds-sg"
  description = "Postgres access from within the VPC"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-rds-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "rds" {
  count             = length(local.ingress_cidrs)
  security_group_id = aws_security_group.rds.id
  cidr_ipv4         = local.ingress_cidrs[count.index]
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
  description       = "Postgres from VPC"
}

resource "aws_vpc_security_group_egress_rule" "rds" {
  security_group_id = aws_security_group.rds.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All egress"
}

resource "aws_db_instance" "this" {
  identifier                  = "${var.name_prefix}-pg"
  engine                      = "postgres"
  engine_version              = var.db_engine_version
  instance_class              = var.db_instance_class
  allocated_storage           = var.db_allocated_storage
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = var.db_name
  username                    = var.db_username
  manage_master_user_password = true
  multi_az                    = var.db_multi_az
  db_subnet_group_name        = aws_db_subnet_group.this.name
  vpc_security_group_ids      = [aws_security_group.rds.id]
  backup_retention_period     = var.db_backup_retention_days
  deletion_protection         = var.db_deletion_protection
  skip_final_snapshot         = var.db_skip_final_snapshot
  final_snapshot_identifier   = var.db_skip_final_snapshot ? null : "${var.name_prefix}-pg-final"
  apply_immediately           = true
  tags                        = merge(var.tags, { Name = "${var.name_prefix}-pg" })
}

# --- Redis (ElastiCache) ---
resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis"
  subnet_ids = var.private_subnet_ids
  tags       = merge(var.tags, { Name = "${var.name_prefix}-redis-subnets" })
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "Redis access from within the VPC"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-redis-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "redis" {
  count             = length(local.ingress_cidrs)
  security_group_id = aws_security_group.redis.id
  cidr_ipv4         = local.ingress_cidrs[count.index]
  from_port         = 6379
  to_port           = 6379
  ip_protocol       = "tcp"
  description       = "Redis from VPC"
}

resource "aws_vpc_security_group_egress_rule" "redis" {
  security_group_id = aws_security_group.redis.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All egress"
}

resource "aws_elasticache_cluster" "this" {
  cluster_id         = "${var.name_prefix}-redis"
  engine             = "redis"
  engine_version     = var.redis_engine_version
  node_type          = var.redis_node_type
  num_cache_nodes    = 1
  port               = 6379
  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]
  tags               = merge(var.tags, { Name = "${var.name_prefix}-redis" })
}
```

Create `infra/terraform/modules/data/outputs.tf`:
```hcl
output "db_endpoint" {
  description = "RDS endpoint address."
  value       = aws_db_instance.this.address
}

output "db_port" {
  description = "RDS port."
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "Initial database name."
  value       = aws_db_instance.this.db_name
}

output "db_master_user_secret_arn" {
  description = "ARN of the RDS-managed master-password secret in Secrets Manager."
  value       = try(aws_db_instance.this.master_user_secret[0].secret_arn, null)
}

output "rds_security_group_id" {
  description = "Security group id for the RDS instance."
  value       = aws_security_group.rds.id
}

output "redis_endpoint" {
  description = "ElastiCache Redis node endpoint address."
  value       = aws_elasticache_cluster.this.cache_nodes[0].address
}

output "redis_port" {
  description = "Redis port."
  value       = aws_elasticache_cluster.this.port
}

output "redis_security_group_id" {
  description = "Security group id for the Redis cluster."
  value       = aws_security_group.redis.id
}
```

- [ ] **Step 2: Validate the module standalone (Docker, via PowerShell tool)**

From the repo root:
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/data hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/data hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
```
Expected: `validate` → `Success! The configuration is valid.` (validates the data module against the AWS provider schema — catches any wrong attribute names/types, e.g. on `aws_db_instance`/`aws_elasticache_cluster`/the SG-rule resources). `fmt -check` exits 0. If `fmt -check` flags files, run `... -w /work hashicorp/terraform:1.9 fmt -recursive` then re-check. Report the exact validate output.

- [ ] **Step 3: Commit**

Confirm `git status` shows no `.terraform/`/`*.tfstate` staged. Then:
```bash
git add infra/terraform/modules/data/versions.tf infra/terraform/modules/data/variables.tf infra/terraform/modules/data/main.tf infra/terraform/modules/data/outputs.tf
git add infra/terraform/modules/data/.terraform.lock.hcl 2>/dev/null || true
git commit -m "feat(aws): terraform data module — RDS Postgres + ElastiCache Redis (AWS-2b)"
```
(Append the Co-Authored-By footer. Verify with `git show --stat HEAD` that no `.terraform/`/state was committed.)

---

### Task 2: Wire the data module into dev + README + whole-tree validation

**Files:**
- Modify: `infra/terraform/environments/dev/main.tf` (add `module "data"`)
- Modify: `infra/terraform/environments/dev/outputs.tf` (re-export data outputs)
- Modify: `infra/terraform/README.md` (data module line + TimescaleDB note)

- [ ] **Step 1: Add the `module "data"` call**

In `infra/terraform/environments/dev/main.tf`, append AFTER the existing `module "network"` block:
```hcl
module "data" {
  source             = "../../modules/data"
  name_prefix        = "saalr-dev"
  vpc_id             = module.network.vpc_id
  vpc_cidr           = module.network.vpc_cidr
  private_subnet_ids = module.network.private_subnet_ids
}
```
(Leave the `terraform { backend "s3" ... }`, `provider "aws"`, and `module "network"` blocks unchanged.)

- [ ] **Step 2: Re-export the data outputs**

In `infra/terraform/environments/dev/outputs.tf`, append (keep the existing network outputs):
```hcl
output "db_endpoint" {
  value = module.data.db_endpoint
}

output "db_master_user_secret_arn" {
  value = module.data.db_master_user_secret_arn
}

output "redis_endpoint" {
  value = module.data.redis_endpoint
}
```

- [ ] **Step 3: Update the README**

In `infra/terraform/README.md`:
- In the `## Layout` block, add the `modules/data/` line under `modules/network/`:
```
    modules/data/         RDS Postgres + ElastiCache Redis + subnet groups + security groups
```
- Add a new section after the Layout block (before `## One-time bootstrap`):
```markdown
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
```

- [ ] **Step 4: Validate dev (network + data together) + fmt + tflint**

From the repo root (PowerShell tool):
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work ghcr.io/terraform-linters/tflint --recursive
```
Expected: `init -backend=false` initializes the provider + both `../../modules/network` and `../../modules/data`; `validate` → `Success! The configuration is valid.`; `fmt -check` exits 0; `tflint --recursive` reports no errors (best-effort — `validate` is the hard gate). Report the exact validate output + tflint outcome. Fix any `fmt` diff with `... fmt -recursive`.

- [ ] **Step 5: Commit**

Confirm no `.terraform/`/`*.tfstate` staged (the dev env's `.terraform/` is regenerated by `init` — do NOT add it). Then:
```bash
git add infra/terraform/environments/dev/main.tf infra/terraform/environments/dev/outputs.tf infra/terraform/README.md
git commit -m "feat(aws): wire the data module into the dev environment + TimescaleDB note (AWS-2b)"
```
(Append the Co-Authored-By footer.)

---

## Final verification (after all tasks)

From the repo root (PowerShell tool):
- [ ] `fmt -check -recursive` on `/work` — exit 0.
- [ ] `modules/data`: `init -backend=false` + `validate` → valid.
- [ ] `environments/dev`: `init -backend=false` + `validate` → valid (network + data together).
- [ ] `tflint --recursive` — no errors (best-effort).
- [ ] `git status` clean of `.terraform/` + `*.tfstate*`; the new `.terraform.lock.hcl` (if any) tracked.
- [ ] **Final code-review subagent** over the whole AWS-2b diff (HCL correctness, security posture, the outputs contract, the TimescaleDB note).

## Self-review notes
- **Spec coverage:** data module — RDS Postgres (managed password) + single-node Redis + subnet groups + v5 SG rules + outputs (T1); dev wiring + data output re-exports + README/TimescaleDB note (T2); validate-only acceptance throughout. All spec sections map to a task.
- **Consistency:** the data module's variables (`name_prefix`, `vpc_id`, `vpc_cidr`, `private_subnet_ids`, …) match the dev env's `module "data"` call; the module outputs (`db_endpoint`, `db_master_user_secret_arn`, `redis_endpoint`, …) match the dev env's re-exports; the `module.network.{vpc_id,vpc_cidr,private_subnet_ids}` references match AWS-2a's network outputs.
- **Deliberate choices flagged for the reviewer:** `manage_master_user_password = true` (no secret in state; `master_user_secret[0].secret_arn` output); validate-only (no `apply`); SG ingress from the VPC CIDR via `ingress_cidr_blocks` default-to-`[vpc_cidr]` (SG-to-SG tightening deferred to 2d); single-node Redis (HA is a later toggle); dev toggles (`deletion_protection=false`/`skip_final_snapshot=true`/`multi_az=false`) so a dev stack can be destroyed; the documented RDS-can't-run-TimescaleDB gap; default AWS-managed KMS (CMK deferred to 2c).
- **Environment caveat:** the checks need Docker + network (to pull the terraform/tflint images + the AWS provider). If unavailable, hand-verify the HCL against the spec and have the reviewer scrutinize it — the known ceiling for IaC verification without a terraform binary / AWS account.
