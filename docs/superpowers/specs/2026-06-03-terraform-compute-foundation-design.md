# AWS-2d-1 — Terraform compute foundation (ECR + ECS cluster + IAM + logs + app SG) (combined design + plan)

**Status:** approved (autonomous /ralph) 2026-06-03
**Slice:** AWS-2d-1 (first sub-slice of AWS-2d compute; HLD ADR-008 / §infra). AWS-2d decomposed into **2d-1** (this — compute foundation), **2d-2** (API service + internal ALB), **2d-3** (workers + EventBridge scheduled tasks).
**Builds on:** AWS-2a (network), AWS-2b (data), AWS-2c (storage/secrets/KMS). Consumes their outputs.

> Combined design+plan doc (autonomous mode — halves doc overhead). Validate-only acceptance via Docker (`fmt`/`validate`/`tflint`), no `apply`. HCL authored inline by the controller (the Docker-`init` stall makes impl-subagents unreliable for Terraform); a final review subagent scrutinizes the diff.

## Goal

The shared compute substrate every service/worker (2d-2/2d-3) will use: an **ECR registry** (one repo per deployable image), an **ECS Fargate cluster** (+ Container Insights), the **IAM task-execution + task roles** (the task role granted the AWS-2c S3 buckets / Secrets Manager secrets / KMS key; the execution role granted ECR pull + log write + secret injection), a **CloudWatch log group**, and the **ECS app security group**. Plus closing AWS-2b's deferred item: the data SGs gain an SG-referencing ingress from the app SG.

## Decisions (controller, autonomous defaults)

1. **`modules/compute/`** holds ECR + cluster + IAM + logs + app SG (cohesive compute foundation). Consumes `module.network.vpc_id` + `module.storage.{bucket names, secret_arns, kms_key_arn}`.
2. **IAM policies via `aws_iam_policy_document` data sources** (cleaner than inline `jsonencode`). Task role: `s3:{Get,Put,Delete}Object`+`ListBucket` on the 3 buckets, `secretsmanager:GetSecretValue` on the secrets, `kms:{Decrypt,GenerateDataKey}` on the CMK. Execution role: managed `AmazonECSTaskExecutionRolePolicy` + `secretsmanager:GetSecretValue`/`kms:Decrypt` (for secret injection at container start).
3. **App SG** has egress-all + **no ingress** (ingress is added by the ALB in 2d-2). The **data SGs gain an optional SG-ref ingress** (`modules/data` gets an `app_security_group_id` var; when set, a `referenced_security_group_id` ingress on 5432/6379 is added alongside the existing VPC-CIDR rules).
4. **ECR repos** (default list): `api, ingest-worker, backtest-worker, oms-worker, research-agent, ml-worker, content-worker` (the deployable workspace apps), named `${name_prefix}/<name>`, `force_delete = true` (dev), scan-on-push.

## Files

- Create: `infra/terraform/modules/compute/{versions,variables,main,outputs}.tf`
- Modify: `infra/terraform/modules/data/{variables,main,outputs}.tf` (add `app_security_group_id` var + conditional SG-ref ingress rules)
- Modify: `infra/terraform/environments/dev/{main,outputs}.tf` (add `module "compute"`, pass its app SG to `module "data"`, re-export)
- Modify: `infra/terraform/README.md` (compute layout line + a short note)

## `modules/compute` HCL

`versions.tf`: standard (`>= 1.6`, `aws ~> 5.0`).

`variables.tf`: `name_prefix` (string), `vpc_id` (string), `ecr_repo_names` (list(string), default the 7 above), `s3_bucket_names` (list(string)), `secret_arns` (list(string)), `kms_key_arn` (string), `log_retention_days` (number, default 30), `tags` (map, default {}).

`main.tf`:
```hcl
# --- ECR ---
resource "aws_ecr_repository" "this" {
  for_each             = toset(var.ecr_repo_names)
  name                 = "${var.name_prefix}/${each.value}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration { scan_on_push = true }
  tags = merge(var.tags, { Name = "${var.name_prefix}/${each.value}" })
}

# --- ECS cluster ---
resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-cluster" })
}

# --- CloudWatch logs ---
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.name_prefix}"
  retention_in_days = var.log_retention_days
  tags              = merge(var.tags, { Name = "${var.name_prefix}-ecs-logs" })
}

# --- IAM ---
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# execution role: ECR pull + log write (managed) + secret injection
resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = merge(var.tags, { Name = "${var.name_prefix}-ecs-execution" })
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid       = "InjectSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns
  }
  statement {
    sid       = "DecryptSecrets"
    actions   = ["kms:Decrypt"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${var.name_prefix}-ecs-execution-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# task role: app access to S3 / Secrets / KMS
resource "aws_iam_role" "task" {
  name               = "${var.name_prefix}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = merge(var.tags, { Name = "${var.name_prefix}-ecs-task" })
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "S3Objects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [for b in var.s3_bucket_names : "arn:aws:s3:::${b}/*"]
  }
  statement {
    sid       = "S3List"
    actions   = ["s3:ListBucket"]
    resources = [for b in var.s3_bucket_names : "arn:aws:s3:::${b}"]
  }
  statement {
    sid       = "Secrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns
  }
  statement {
    sid       = "Kms"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "${var.name_prefix}-ecs-task"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# --- App security group (ingress added by the ALB in 2d-2) ---
resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-ecs-app-sg"
  description = "ECS app tasks; ingress added by the ALB (2d-2)"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-ecs-app-sg" })
}

resource "aws_vpc_security_group_egress_rule" "app" {
  security_group_id = aws_security_group.app.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All egress"
}
```

`outputs.tf`: `cluster_id`/`cluster_name`/`cluster_arn` (= `aws_ecs_cluster.this.{id,name,arn}`), `ecr_repository_urls` (`{ for k, r in aws_ecr_repository.this : k => r.repository_url }`), `task_execution_role_arn` (`aws_iam_role.execution.arn`), `task_role_arn` (`aws_iam_role.task.arn`), `app_security_group_id` (`aws_security_group.app.id`), `log_group_name` (`aws_cloudwatch_log_group.ecs.name`).

## `modules/data` change (SG tightening)

`variables.tf` += `variable "app_security_group_id" { type = string, default = "" }`.
`main.tf` += (after the existing rds/redis ingress rules):
```hcl
resource "aws_vpc_security_group_ingress_rule" "rds_app" {
  count                        = var.app_security_group_id != "" ? 1 : 0
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = var.app_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Postgres from the ECS app SG"
}

resource "aws_vpc_security_group_ingress_rule" "redis_app" {
  count                        = var.app_security_group_id != "" ? 1 : 0
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = var.app_security_group_id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
  description                  = "Redis from the ECS app SG"
}
```
(No outputs change needed; the existing VPC-CIDR rules remain — a prod config can set `ingress_cidr_blocks = []` to rely solely on the SG-ref path.)

## Dev wiring

`environments/dev/main.tf` += after `module "storage"`:
```hcl
module "compute" {
  source          = "../../modules/compute"
  name_prefix     = "saalr-dev"
  vpc_id          = module.network.vpc_id
  s3_bucket_names = [module.storage.transcripts_bucket, module.storage.ml_models_bucket, module.storage.audit_bucket]
  secret_arns     = values(module.storage.secret_arns)
  kms_key_arn     = module.storage.kms_key_arn
}
```
and `module "data"` gains `app_security_group_id = module.compute.app_security_group_id`.

`environments/dev/outputs.tf` += `ecr_repository_urls` (= `module.compute.ecr_repository_urls`), `ecs_cluster_name` (= `module.compute.cluster_name`), `task_role_arn` (= `module.compute.task_role_arn`).

## Tasks (executed inline by the controller)

- [ ] **T1:** write `modules/compute/*` → `docker ... -w /work/modules/compute init -backend=false && validate` + `fmt -check` → commit.
- [ ] **T2:** edit `modules/data` (SG-ref ingress) → validate the data module standalone → commit (with the dev wiring).
- [ ] **T3:** wire `module "compute"` + the `data.app_security_group_id` into dev + README → validate `environments/dev` (network+data+storage+compute together) + `fmt` + `tflint` → commit.
- [ ] **Final review** subagent over the AWS-2d-1 diff.

## Verification

Docker, repo root (PowerShell): `init -backend=false` + `validate` for `modules/compute`, `modules/data`, and `environments/dev`; `fmt -check -recursive`; `tflint --recursive`. No `apply`.

## Out of scope (2d-2 / 2d-3 / later)

ECS task definitions + Fargate services + the internal ALB + target groups + listener (2d-2, API); worker task defs + EventBridge scheduled tasks (ingest/reconcile/sentiment) + long-running consumer services (2d-3); ECR lifecycle policies; service autoscaling; ECS exec; capacity providers / Fargate Spot; `prod` env; `terraform apply`.
