# AWS-2b — Data-layer Terraform module (RDS Postgres + ElastiCache Redis) (design)

**Status:** approved 2026-06-03
**Slice:** AWS-2b (second sub-slice of the Terraform foundation; HLD ADR-008 / §infra / §6 storage)
**Builds on:** AWS-2a (the Terraform skeleton + network module). Consumes the network module's `vpc_id` / `private_subnet_ids` / `vpc_cidr` outputs.

## Goal

Provision the managed data tier — an **RDS Postgres** instance and a single-node **ElastiCache Redis** cluster, with their subnet groups (private subnets) and security groups — as a `modules/data/` module wired into the `dev` environment. Same **validate-only** acceptance as AWS-2a (Docker `fmt`/`validate`/`tflint`, no `apply`, no AWS account, no spend).

## Approved decisions

1. **RDS Postgres** (managed) — AWS RDS cannot run the TimescaleDB extension (the HLD's "RDS + TimescaleDB" is inaccurate). The app uses TimescaleDB only for the `bars` hypertable (an optimization; queries are correct on a plain table), so `bars` deploys as a plain Postgres table; the hypertable/time-partitioning strategy (`pg_partman` or Timescale Cloud) is a documented scale-time follow-up.
2. **RDS-managed master password** — `manage_master_user_password = true`; RDS creates + manages the password in Secrets Manager (rotation-ready). No password in Terraform HCL or state. The module outputs the managed secret ARN.
3. **Single-node ElastiCache Redis** (dev, `cache.t4g.micro`); a replication-group HA variant is a later/prod toggle.

## `modules/data/`

A new module consuming the network outputs and provisioning Postgres + Redis. Uses the AWS-provider-v5 `aws_vpc_security_group_ingress_rule` / `aws_vpc_security_group_egress_rule` resources (preferred over inline `ingress {}`/`egress {}` blocks).

### `variables.tf`

| variable | type | default | purpose |
|----------|------|---------|---------|
| `name_prefix` | string | — | resource/tag prefix (e.g. `saalr-dev`) |
| `vpc_id` | string | — | from `module.network.vpc_id` |
| `vpc_cidr` | string | — | from `module.network.vpc_cidr` (SG ingress default) |
| `private_subnet_ids` | list(string) | — | from `module.network.private_subnet_ids` |
| `ingress_cidr_blocks` | list(string) | `[]` | SG ingress sources; empty → `[var.vpc_cidr]` |
| `db_engine_version` | string | `"16"` | Postgres major version |
| `db_instance_class` | string | `"db.t4g.micro"` | |
| `db_allocated_storage` | number | `20` | GB (gp3) |
| `db_name` | string | `"saalr"` | |
| `db_username` | string | `"saalr_admin"` | master username (password is RDS-managed) |
| `db_multi_az` | bool | `false` | dev off; prod on |
| `db_deletion_protection` | bool | `false` | dev off (so `destroy` works) |
| `db_skip_final_snapshot` | bool | `true` | dev true |
| `db_backup_retention_days` | number | `7` | |
| `redis_engine_version` | string | `"7.1"` | |
| `redis_node_type` | string | `"cache.t4g.micro"` | |
| `tags` | map(string) | `{}` | merged onto every resource |

### `main.tf`

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

### `outputs.tf`

```hcl
output "db_endpoint"               { value = aws_db_instance.this.address }
output "db_port"                   { value = aws_db_instance.this.port }
output "db_name"                   { value = aws_db_instance.this.db_name }
output "db_master_user_secret_arn" { value = try(aws_db_instance.this.master_user_secret[0].secret_arn, null) }
output "rds_security_group_id"     { value = aws_security_group.rds.id }
output "redis_endpoint"            { value = aws_elasticache_cluster.this.cache_nodes[0].address }
output "redis_port"                { value = aws_elasticache_cluster.this.port }
output "redis_security_group_id"   { value = aws_security_group.redis.id }
```

`aws_db_instance.this.master_user_secret` is the list attribute populated when `manage_master_user_password = true`; `[0].secret_arn` is the managed Secrets Manager secret the app reads (via the AWS-1 `SecretsManagerResolver` pattern) to build `APP_DATABASE_URL`. `cache_nodes[0].address` is the single node's endpoint. (Each output `value`-only; descriptions omitted for brevity, consistent with the dev env's existing outputs.)

`versions.tf` mirrors AWS-2a (`terraform >= 1.6`, `aws ~> 5.0`).

## Dev environment wiring

`environments/dev/main.tf` adds, after the existing `module "network"`:
```hcl
module "data" {
  source             = "../../modules/data"
  name_prefix        = "saalr-dev"
  vpc_id             = module.network.vpc_id
  vpc_cidr           = module.network.vpc_cidr
  private_subnet_ids = module.network.private_subnet_ids
}
```
(Defaults cover engine versions / sizing / dev toggles; the env can override via variables later.)

`environments/dev/outputs.tf` adds re-exports:
```hcl
output "db_endpoint"               { value = module.data.db_endpoint }
output "db_master_user_secret_arn" { value = module.data.db_master_user_secret_arn }
output "redis_endpoint"            { value = module.data.redis_endpoint }
```
No new `environments/dev/variables.tf` or `terraform.tfvars` entries are required (the data module's dev defaults apply); the network variables are unchanged.

## Verification model

Validate-only, via Docker from the repo root (PowerShell tool; the spaced-path mount caveat from AWS-2a applies):
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/data hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/data hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work ghcr.io/terraform-linters/tflint --recursive
```
Validating `environments/dev` initializes both `modules/network` and `modules/data`, exercising the full stack. `init`/`validate` download the AWS provider (network) but need no AWS credentials. No `apply`/`plan`.

## README / docs

`infra/terraform/README.md` (from AWS-2a) gains:
- a `modules/data/` line in the Layout section;
- a **"Database (TimescaleDB note)"** subsection: RDS Postgres does not support the TimescaleDB extension; `bars` runs as a plain table on RDS; the hypertable optimization (`CREATE EXTENSION timescaledb` / `create_hypertable`) is a deferred scale-time decision (`pg_partman` or Timescale Cloud); the migrations that create the extension/hypertable need a guard or an RDS-specific path before applying to RDS;
- a note that the DB master password is RDS-managed in Secrets Manager (`db_master_user_secret_arn` output) and the app reads it at deploy time.

## Out of scope (AWS-2c → 2e / later)

The TimescaleDB hypertable strategy + the RDS-specific migration path; SG-to-SG tightening (ingress from the ECS app SG — AWS-2d, when that SG exists); customer-managed KMS CMK for RDS/Redis (default AWS-managed keys for now; CMK in 2c); RDS read replicas, Multi-AZ-prod, custom parameter/option groups, Performance Insights; Redis replication-group HA + auth-token/TLS; the `prod` environment; running app migrations against RDS; `terraform plan`/`apply`.
