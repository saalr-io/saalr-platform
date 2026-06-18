# AWS prod deployment + saalr.io — Implementation Plan

> ⚠️ **SUPERSEDED — do not execute.** This plan was written on the false premise that no
> Terraform existed in the repo. In fact `master` already carries a complete module-based stack
> (`infra/terraform/modules/*` + `environments/dev/`). The real work was much smaller: an
> `environments/prod/` reusing those modules + a `saalr.io` Route 53 zone. See
> **`infra/terraform/environments/prod/`** and the **"Production environment"** section of
> `infra/terraform/README.md` for the actual implementation. Retained only for its cost analysis
> and the `saalr.io` domain/CORS reasoning.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `saalr-prod` AWS stack with Terraform and serve the existing monorepo (web + API + workers + Postgres + Redis) at `https://saalr.io`.

**Architecture:** A single Terraform configuration (`infra/terraform/environments/prod`, region `us-east-1`) provisions: a 2-AZ VPC (1 NAT GW + S3/ECR/logs endpoints), ECR repos, RDS PostgreSQL 16 (single-AZ, pgvector), ElastiCache (Valkey), an internal-facing ALB, ECS Fargate **services** (api, research-agent, backtest-worker) plus **EventBridge-scheduled** task-defs (ingest/oms/ml/content), an S3+CloudFront static site, ACM TLS, a Route 53 public hosted zone delegated from the external registrar, Secrets Manager for all credentials, and a GitHub-OIDC deploy role. CloudFront serves the static web app and routes `/api/*` to the ALB origin so the whole product is same-origin on `saalr.io` (no CORS — preserves the existing `VITE_API_BASE_URL=/api` pattern).

**Tech Stack:** Terraform ≥1.7 (AWS provider ~>5.0), `terraform-aws-modules` for VPC/RDS/ElastiCache, ECS Fargate, RDS PostgreSQL 16, ElastiCache Valkey 7, CloudFront + S3 (OAC), ACM, Route 53, Secrets Manager, EventBridge Scheduler, GitHub Actions (existing `deploy.yml` / `deploy-web.yml`).

## Global Constraints

- **Region:** `us-east-1` (matches existing workflows; CloudFront ACM certs MUST live here anyway). Verbatim in every `provider`/resource.
- **Env / name prefix:** `saalr-prod` for all named resources (cluster `saalr-prod-cluster`, ECR `saalr-prod/<app>`, services `saalr-prod-<app>`, hosted zone `saalr.io`).
- **Domain:** `saalr.io`, registered at an **external registrar** (delegate via NS only — no registrar transfer).
- **DB engine:** PostgreSQL **16** (pgvector + HNSW index required by migration `0007_content_embeddings`).
- **Two DB roles:** master/admin (migrations, `ADMIN_DATABASE_URL`) and least-privilege login role `saalr_app` (app, `APP_DATABASE_URL`). Alembic rewrites `+asyncpg`→`+psycopg2` itself; pass it the `+asyncpg` URL.
- **API contract:** container listens on `:8000`, health path `/healthz`, factory entrypoint `saalr_api.main:create_app`.
- **Docker build:** context = repo root, `-f apps/<app>/Dockerfile .` (monorepo `uv sync --package`).
- **No static AWS keys anywhere** — GitHub Actions authenticates via OIDC role; ECS tasks use task roles; app credentials come from Secrets Manager, never `.tfvars` committed to git.
- **Reliability tier (this milestone):** public beta — single-AZ RDS, daily snapshots, no Multi-AZ, no read replicas, single NAT GW, single region. (Triggers to upgrade are documented per task.)
- **Secrets in state:** Terraform state will contain secret material → backend is encrypted S3 with restricted access (Task 0.1). Never commit `*.tfvars` containing secrets; use `TF_VAR_*` env or `-var-file` outside git.

---

## File Structure

```
infra/terraform/
  bootstrap/                      # one-time: remote-state bucket + lock table (local state)
    main.tf
  modules/
    network/                      # VPC, subnets, NAT, endpoints, security groups
      main.tf  variables.tf  outputs.tf
    data/                         # RDS + ElastiCache + saalr_app role bootstrap
      main.tf  variables.tf  outputs.tf
    ecs-service/                  # reusable Fargate service (api/research/backtest)
      main.tf  variables.tf  outputs.tf
    ecs-scheduled/                # reusable EventBridge-scheduled task-def (ingest/oms/ml/content)
      main.tf  variables.tf  outputs.tf
    web-delivery/                 # S3 + CloudFront(+OAC) + behaviors
      main.tf  variables.tf  outputs.tf
  environments/prod/
    backend.tf  providers.tf  variables.tf  terraform.tfvars  # tfvars: non-secret only
    dns.tf                        # Route53 zone + ACM cert + validation
    network.tf  data.tf  registry.tf  secrets.tf  oidc.tf
    compute.tf  delivery.tf  scheduled.tf
    outputs.tf
```

CI files modified: `.github/workflows/deploy.yml`, `.github/workflows/deploy-web.yml`.

---

## Phase 0 — Terraform foundation

### Task 0.1: Remote-state backend (bootstrap)

**Files:**
- Create: `infra/terraform/bootstrap/main.tf`

**Interfaces:**
- Produces: S3 bucket `saalr-prod-tfstate-<acct-id>`, DynamoDB lock table `saalr-prod-tflock`.

- [ ] **Step 1: Write the bootstrap config**

```hcl
# infra/terraform/bootstrap/main.tf — run ONCE with local state, then never again.
terraform { required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } } }
provider "aws" { region = "us-east-1" }
data "aws_caller_identity" "me" {}

resource "aws_s3_bucket" "state" {
  bucket = "saalr-prod-tfstate-${data.aws_caller_identity.me.account_id}"
}
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "aws:kms" } }
}
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_dynamodb_table" "lock" {
  name         = "saalr-prod-tflock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute { name = "LockID"; type = "S" }
}
output "state_bucket" { value = aws_s3_bucket.state.id }
```

- [ ] **Step 2: Apply bootstrap**

Run: `cd infra/terraform/bootstrap && terraform init && terraform apply`
Expected: prints `state_bucket = "saalr-prod-tfstate-<acct-id>"`.

- [ ] **Step 3: Commit**

```bash
git add infra/terraform/bootstrap/main.tf
git commit -m "infra(prod): bootstrap terraform remote state bucket + lock table"
```

### Task 0.2: Backend + provider + variables for the prod environment

**Files:**
- Create: `infra/terraform/environments/prod/backend.tf`, `providers.tf`, `variables.tf`, `terraform.tfvars`

**Interfaces:**
- Produces: initialized prod workspace; vars `domain_name`, `region`, `name_prefix`, `db_max_acu`/instance class, image tag.

- [ ] **Step 1: Write backend.tf**

```hcl
terraform {
  required_version = ">= 1.7"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
  backend "s3" {
    bucket         = "saalr-prod-tfstate-<ACCOUNT_ID>"   # fill from Task 0.1 output
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "saalr-prod-tflock"
    encrypt        = true
  }
}
```

- [ ] **Step 2: Write providers.tf + variables.tf**

```hcl
# providers.tf
provider "aws" {
  region = var.region
  default_tags { tags = { Project = "saalr", Env = "prod", ManagedBy = "terraform" } }
}
data "aws_caller_identity" "me" {}

# variables.tf
variable "region"       { type = string, default = "us-east-1" }
variable "name_prefix"  { type = string, default = "saalr-prod" }
variable "domain_name"  { type = string, default = "saalr.io" }
variable "github_repo"  { type = string }            # e.g. "spayyavula/saalr"
variable "db_instance_class" { type = string, default = "db.t4g.small" }
variable "image_tag"    { type = string, default = "latest" }
```

- [ ] **Step 3: Write terraform.tfvars (NON-SECRET only)**

```hcl
github_repo = "OWNER/REPO"   # the GitHub repo running the deploy workflows
```

- [ ] **Step 4: Init**

Run: `cd infra/terraform/environments/prod && terraform init`
Expected: `Terraform has been successfully initialized!` using the S3 backend.

- [ ] **Step 5: Commit**

```bash
git add infra/terraform/environments/prod/{backend.tf,providers.tf,variables.tf,terraform.tfvars}
git commit -m "infra(prod): terraform backend, provider, and variables"
```

---

## Phase 1 — DNS + TLS  *(independently shippable: delegates saalr.io, issues cert; touches nothing live)*

### Task 1.1: Route 53 hosted zone + ACM certificate

**Files:**
- Create: `infra/terraform/environments/prod/dns.tf`
- Modify: `infra/terraform/environments/prod/outputs.tf`

**Interfaces:**
- Produces: `aws_route53_zone.primary` (consumed by delivery + outputs), `aws_acm_certificate.web` (validated; consumed by CloudFront in Task 5.2), output `route53_name_servers`.

- [ ] **Step 1: Write dns.tf**

```hcl
resource "aws_route53_zone" "primary" { name = var.domain_name }

resource "aws_acm_certificate" "web" {
  domain_name               = var.domain_name
  subject_alternative_names = ["www.${var.domain_name}"]
  validation_method         = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for d in aws_acm_certificate.web.domain_validation_options :
    d.domain_name => { name = d.resource_record_name, type = d.resource_record_type, record = d.resource_record_value }
  }
  zone_id = aws_route53_zone.primary.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "web" {
  certificate_arn         = aws_acm_certificate.web.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}
```

- [ ] **Step 2: Add outputs**

```hcl
# outputs.tf
output "route53_name_servers" { value = aws_route53_zone.primary.name_servers }
```

- [ ] **Step 3: Validate + plan**

Run: `terraform validate && terraform plan -target=aws_route53_zone.primary`
Expected: validate passes; plan shows the zone + cert + 2 validation records to add.

- [ ] **Step 4: Apply the zone first (need NS before validation can complete)**

Run: `terraform apply -target=aws_route53_zone.primary`
Then: `terraform output route53_name_servers`
Expected: four `ns-*.awsdns-*` hostnames.

- [ ] **Step 5: Delegate at the external registrar (MANUAL — outside Terraform)**

At the registrar for `saalr.io`, replace the nameservers with the four from Step 4. Then verify delegation:
Run: `dig +short NS saalr.io @8.8.8.8`
Expected: the four AWS nameservers (may take minutes–48h to propagate).

- [ ] **Step 6: Apply the cert + validation once NS resolves**

Run: `terraform apply -target=aws_acm_certificate_validation.web`
Then: `aws acm describe-certificate --certificate-arn $(terraform output -raw web_certificate_arn 2>/dev/null || echo) --query 'Certificate.Status'` (or check console)
Expected: certificate `Status = ISSUED`.

- [ ] **Step 7: Commit**

```bash
git add infra/terraform/environments/prod/dns.tf infra/terraform/environments/prod/outputs.tf
git commit -m "infra(prod): Route53 hosted zone + DNS-validated ACM cert for saalr.io"
```

**Upgrade trigger:** add `app.saalr.io` / regional API cert only if you later split the API onto its own subdomain (you won't for this milestone — `/api/*` rides CloudFront).

---

## Phase 2 — Network, registry, secrets, OIDC  *(shippable: image push + secrets ready)*

### Task 2.1: VPC network module

**Files:**
- Create: `infra/terraform/modules/network/{main,variables,outputs}.tf`
- Create: `infra/terraform/environments/prod/network.tf`

**Interfaces:**
- Produces: `vpc_id`, `private_subnet_ids`, `public_subnet_ids`, and security-group IDs `alb_sg`, `app_sg`, `db_sg`, `cache_sg` (chained ALB→app→db/cache).

- [ ] **Step 1: Write modules/network/main.tf**

```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  name    = "${var.name_prefix}-vpc"
  cidr    = "10.20.0.0/16"
  azs             = ["us-east-1a", "us-east-1b"]
  private_subnets = ["10.20.1.0/24", "10.20.2.0/24"]
  public_subnets  = ["10.20.101.0/24", "10.20.102.0/24"]
  enable_nat_gateway = true
  single_nat_gateway = true            # 1 NAT for beta; per-AZ at first SLA
}

# Free gateway endpoint (no NAT data charge for S3 — ECR layers live in S3)
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
}
# Interface endpoints cut NAT data cost on image pulls + logs
locals { if_endpoints = ["ecr.api", "ecr.dkr", "logs", "secretsmanager"] }
resource "aws_vpc_endpoint" "iface" {
  for_each            = toset(local.if_endpoints)
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.app.id]
  private_dns_enabled = true
}

resource "aws_security_group" "alb"  { name = "${var.name_prefix}-alb",  vpc_id = module.vpc.vpc_id }
resource "aws_security_group" "app"  { name = "${var.name_prefix}-app",  vpc_id = module.vpc.vpc_id }
resource "aws_security_group" "db"   { name = "${var.name_prefix}-db",   vpc_id = module.vpc.vpc_id }
resource "aws_security_group" "cache"{ name = "${var.name_prefix}-cache",vpc_id = module.vpc.vpc_id }

# CloudFront → ALB on 443/80; app → ALB target on 8000; app → db 5432; app → cache 6379
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  ip_protocol = "tcp", from_port = 443, to_port = 443, cidr_ipv4 = "0.0.0.0/0"
}
resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id = aws_security_group.app.id
  ip_protocol = "tcp", from_port = 8000, to_port = 8000
  referenced_security_group_id = aws_security_group.alb.id
}
resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id = aws_security_group.db.id
  ip_protocol = "tcp", from_port = 5432, to_port = 5432
  referenced_security_group_id = aws_security_group.app.id
}
resource "aws_vpc_security_group_ingress_rule" "cache_from_app" {
  security_group_id = aws_security_group.cache.id
  ip_protocol = "tcp", from_port = 6379, to_port = 6379
  referenced_security_group_id = aws_security_group.app.id
}
# Egress-all on alb + app (NAT/endpoints handle outbound)
resource "aws_vpc_security_group_egress_rule" "alb_out" { security_group_id = aws_security_group.alb.id, ip_protocol = "-1", cidr_ipv4 = "0.0.0.0/0" }
resource "aws_vpc_security_group_egress_rule" "app_out" { security_group_id = aws_security_group.app.id, ip_protocol = "-1", cidr_ipv4 = "0.0.0.0/0" }
```

(Add `variables.tf` with `name_prefix`, `region`; `outputs.tf` exposing `vpc_id`, `private_subnets`, `public_subnets`, and the four SG ids.)

- [ ] **Step 2: Wire network.tf**

```hcl
module "network" {
  source      = "../../modules/network"
  name_prefix = var.name_prefix
  region      = var.region
}
```

- [ ] **Step 3: Validate + apply**

Run: `terraform validate && terraform apply -target=module.network`
Expected: VPC, 4 subnets, 1 NAT GW, 5 endpoints, 4 SGs created.

- [ ] **Step 4: Verify**

Run: `aws ec2 describe-vpcs --filters Name=tag:Name,Values=saalr-prod-vpc --query 'Vpcs[].CidrBlock'`
Expected: `["10.20.0.0/16"]`.

- [ ] **Step 5: Commit**

```bash
git add infra/terraform/modules/network infra/terraform/environments/prod/network.tf
git commit -m "infra(prod): 2-AZ VPC, single NAT, ECR/S3/logs endpoints, chained security groups"
```

**Upgrade trigger:** 3rd AZ + NAT-per-AZ at first uptime SLA; add `logs` data only if log egress >160GB/mo.

### Task 2.2: ECR repositories

**Files:**
- Create: `infra/terraform/environments/prod/registry.tf`

**Interfaces:**
- Produces: ECR repos `saalr-prod/<app>` for the 7 apps; output `ecr_registry`.

- [ ] **Step 1: Write registry.tf**

```hcl
locals {
  apps = ["api", "research-agent", "backtest-worker", "ingest-worker", "oms-worker", "ml-worker", "content-worker"]
}
resource "aws_ecr_repository" "app" {
  for_each             = toset(local.apps)
  name                 = "${var.name_prefix}/${each.value}"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_ecr_lifecycle_policy" "expire" {
  for_each   = aws_ecr_repository.app
  repository = each.value.name
  policy = jsonencode({ rules = [{
    rulePriority = 1, description = "keep last 10",
    selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 },
    action = { type = "expire" }
  }] })
}
```

- [ ] **Step 2: Apply + verify + commit**

Run: `terraform apply -target=aws_ecr_repository.app`
Run: `aws ecr describe-repositories --query 'repositories[].repositoryName' | grep saalr-prod`
Expected: 7 repos.
```bash
git add infra/terraform/environments/prod/registry.tf
git commit -m "infra(prod): ECR repos for the 7 service images with last-10 lifecycle"
```

### Task 2.3: Secrets Manager entries

**Files:**
- Create: `infra/terraform/environments/prod/secrets.tf`

**Interfaces:**
- Produces: secret ARNs `db_app`, `db_admin`, `app_runtime` (Massive/OpenAI/Anthropic/Stripe/Clerk/Redis). Consumed by ECS task defs (Task 4.x) via `secrets[].valueFrom`.

- [ ] **Step 1: Write secrets.tf (values injected out-of-band, not in git)**

```hcl
# Master DB password is generated by RDS (Task 3.1, manage_master_user_password).
# These hold app-role + runtime secrets. Create empty; set values via CLI (Step 2).
resource "aws_secretsmanager_secret" "app_db"      { name = "${var.name_prefix}/db/app_url" }
resource "aws_secretsmanager_secret" "admin_db"    { name = "${var.name_prefix}/db/admin_url" }
resource "aws_secretsmanager_secret" "app_runtime" { name = "${var.name_prefix}/app/runtime" }
```

- [ ] **Step 2: Apply, then set values via CLI (NOT committed)**

Run: `terraform apply -target=aws_secretsmanager_secret.app_db -target=aws_secretsmanager_secret.admin_db -target=aws_secretsmanager_secret.app_runtime`
Then (real values; `app_runtime` is JSON whose keys map to env var names ECS will inject individually):
```bash
aws secretsmanager put-secret-value --secret-id saalr-prod/app/runtime --secret-string '{
  "MASSIVE_API_KEY":"...","OPENAI_API_KEY":"...","ANTHROPIC_API_KEY":"...",
  "STRIPE_SECRET_KEY":"...","STRIPE_WEBHOOK_SECRET":"...",
  "CLERK_JWKS_URL":"https://...","CLERK_ISSUER":"https://..."
}'
```
(The DB URL secrets are populated in Task 3.2 once the RDS endpoint exists.)

- [ ] **Step 3: Commit (config only, no secret values)**

```bash
git add infra/terraform/environments/prod/secrets.tf
git commit -m "infra(prod): Secrets Manager entries for db + app runtime credentials"
```

### Task 2.4: GitHub OIDC deploy role

**Files:**
- Create: `infra/terraform/environments/prod/oidc.tf`
- Modify: `infra/terraform/environments/prod/outputs.tf`

**Interfaces:**
- Produces: output `gha_deploy_role_arn` (the exact name `deploy.yml`/`deploy-web.yml` expect as repo secret `AWS_DEPLOY_ROLE_ARN`).

- [ ] **Step 1: Write oidc.tf**

```hcl
data "tls_certificate" "gh" { url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration" }
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.gh.certificates[0].sha1_fingerprint]
}
data "aws_iam_policy_document" "gha_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals { type = "Federated", identifiers = [aws_iam_openid_connect_provider.github.arn] }
    condition { test = "StringEquals", variable = "token.actions.githubusercontent.com:aud", values = ["sts.amazonaws.com"] }
    condition { test = "StringLike", variable = "token.actions.githubusercontent.com:sub", values = ["repo:${var.github_repo}:*"] }
  }
}
resource "aws_iam_role" "gha_deploy" {
  name               = "${var.name_prefix}-gha-deploy"
  assume_role_policy = data.aws_iam_policy_document.gha_trust.json
}
# Scoped deploy permissions: ECR push, ECS update-service/register-task-def, S3 web sync, CloudFront invalidation, PassRole for task roles.
data "aws_iam_policy_document" "gha_perms" {
  statement { actions = ["ecr:GetAuthorizationToken"], resources = ["*"] }
  statement {
    actions   = ["ecr:BatchCheckLayerAvailability","ecr:CompleteLayerUpload","ecr:InitiateLayerUpload","ecr:PutImage","ecr:UploadLayerPart","ecr:BatchGetImage","ecr:GetDownloadUrlForLayer"]
    resources = [for r in aws_ecr_repository.app : r.arn]
  }
  statement { actions = ["ecs:UpdateService","ecs:DescribeServices","ecs:RegisterTaskDefinition","ecs:DescribeTaskDefinition","ecs:RunTask"], resources = ["*"] }
  statement { actions = ["s3:ListBucket","s3:PutObject","s3:DeleteObject","s3:GetObject"], resources = [aws_s3_bucket.web.arn, "${aws_s3_bucket.web.arn}/*"] }
  statement { actions = ["cloudfront:CreateInvalidation"], resources = ["*"] }
  statement { actions = ["iam:PassRole"], resources = [aws_iam_role.ecs_task_exec.arn, aws_iam_role.ecs_task.arn] }
}
resource "aws_iam_role_policy" "gha_perms" {
  role   = aws_iam_role.gha_deploy.id
  policy = data.aws_iam_policy_document.gha_perms.json
}
```

- [ ] **Step 2: Add output**

```hcl
# outputs.tf
output "gha_deploy_role_arn" { value = aws_iam_role.gha_deploy.arn }
```

- [ ] **Step 3: Apply + verify + commit**

Run: `terraform apply -target=aws_iam_role.gha_deploy`
Run: `terraform output gha_deploy_role_arn`
Expected: `arn:aws:iam::<acct>:role/saalr-prod-gha-deploy`.
```bash
git add infra/terraform/environments/prod/oidc.tf infra/terraform/environments/prod/outputs.tf
git commit -m "infra(prod): GitHub OIDC deploy role scoped to ECR/ECS/S3/CloudFront"
```

---

## Phase 3 — Data: RDS + ElastiCache

### Task 3.1: RDS PostgreSQL 16 + ElastiCache Valkey

**Files:**
- Create: `infra/terraform/modules/data/{main,variables,outputs}.tf`
- Create: `infra/terraform/environments/prod/data.tf`

**Interfaces:**
- Produces: `db_endpoint`, `db_master_secret_arn` (RDS-managed), `cache_endpoint`. Consumed by Task 3.2 (DB role + URLs) and ECS task defs.

- [ ] **Step 1: Write modules/data/main.tf**

```hcl
module "db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"
  identifier = "${var.name_prefix}-pg"
  engine               = "postgres"
  engine_version       = "16"
  family               = "postgres16"
  instance_class       = var.db_instance_class      # db.t4g.small
  allocated_storage    = 20
  max_allocated_storage = 100
  storage_type         = "gp3"
  db_name              = "saalr"
  username             = "saalr_admin"
  manage_master_user_password = true                # → Secrets Manager, rotated
  multi_az             = false                       # beta; flip true at paying-users
  backup_retention_period = 7
  deletion_protection  = true
  vpc_security_group_ids = [var.db_sg_id]
  db_subnet_group_name   = null
  subnet_ids             = var.private_subnet_ids
  create_db_subnet_group = true
  performance_insights_enabled = true
}

resource "aws_elasticache_subnet_group" "this" { name = "${var.name_prefix}-cache", subnet_ids = var.private_subnet_ids }
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.name_prefix}-redis"
  description          = "saalr prod queue/cache"
  engine               = "valkey"
  engine_version       = "7.2"
  node_type            = "cache.t4g.micro"
  num_cache_clusters   = 1
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.this.name
  security_group_ids   = [var.cache_sg_id]
  transit_encryption_enabled = false                 # in-VPC only; enable at compliance
}
```

(Variables: `name_prefix`, `db_instance_class`, `db_sg_id`, `cache_sg_id`, `private_subnet_ids`. Outputs: `db_endpoint = module.db.db_instance_endpoint`, `db_master_secret_arn = module.db.db_instance_master_user_secret_arn`, `cache_endpoint = aws_elasticache_replication_group.redis.primary_endpoint_address`.)

- [ ] **Step 2: Wire data.tf**

```hcl
module "data" {
  source             = "../../modules/data"
  name_prefix        = var.name_prefix
  db_instance_class  = var.db_instance_class
  db_sg_id           = module.network.db_sg
  cache_sg_id        = module.network.cache_sg
  private_subnet_ids = module.network.private_subnets
}
```

- [ ] **Step 3: Apply + verify**

Run: `terraform apply -target=module.data`
Run: `aws rds describe-db-instances --db-instance-identifier saalr-prod-pg --query 'DBInstances[0].[Engine,EngineVersion,DBInstanceStatus]'`
Expected: `["postgres","16.x","available"]`.

- [ ] **Step 4: Commit**

```bash
git add infra/terraform/modules/data infra/terraform/environments/prod/data.tf
git commit -m "infra(prod): RDS PostgreSQL 16 (single-AZ) + ElastiCache Valkey"
```

**Upgrade trigger:** `multi_az = true` + a reader when you have paying users; cap nothing here since RDS instance cost is fixed (no ACU surprise like Aurora Serverless).

### Task 3.2: `saalr_app` login role + URL secrets + pgvector preflight

**Files:**
- Modify: `infra/terraform/environments/prod/secrets.tf` (populate URL secrets via CLI — documented, not HCL)
- Create: `infra/terraform/environments/prod/db-bootstrap.sql`

**Interfaces:**
- Consumes: `module.data.db_endpoint`, `module.data.db_master_secret_arn`.
- Produces: DB role `saalr_app`; populated `app_db`/`admin_db` secrets used by ECS.

- [ ] **Step 1: Write db-bootstrap.sql**

```sql
-- Run once as the master user against the new RDS instance.
CREATE ROLE saalr_app LOGIN PASSWORD :'app_pw';
GRANT CONNECT ON DATABASE saalr TO saalr_app;
-- alembic (run as admin) creates tables and GRANTs table privileges to saalr_app per migration.
```

- [ ] **Step 2: Bootstrap the role (from a bastion/ECS-exec or a one-off task with VPC access)**

```bash
MASTER=$(aws secretsmanager get-secret-value --secret-id $(terraform output -raw db_master_secret_arn) --query SecretString --output text)
APP_PW=$(openssl rand -base64 24)
PGPASSWORD=$(echo "$MASTER" | jq -r .password) psql "host=$(terraform output -raw db_endpoint) user=saalr_admin dbname=saalr" \
  -v app_pw="$APP_PW" -f infra/terraform/environments/prod/db-bootstrap.sql
```

- [ ] **Step 3: Populate the URL secrets (note `+asyncpg`; alembic rewrites to psycopg2 itself)**

```bash
HOST=$(terraform output -raw db_endpoint)            # host:5432
aws secretsmanager put-secret-value --secret-id saalr-prod/db/app_url \
  --secret-string "postgresql+asyncpg://saalr_app:${APP_PW}@${HOST}/saalr"
aws secretsmanager put-secret-value --secret-id saalr-prod/db/admin_url \
  --secret-string "postgresql+asyncpg://saalr_admin:$(echo "$MASTER" | jq -r .password)@${HOST}/saalr"
```

- [ ] **Step 4: Verify pgvector is available (migration 0007 needs it)**

```bash
PGPASSWORD=... psql "host=$HOST user=saalr_admin dbname=saalr" -c "SELECT * FROM pg_available_extensions WHERE name='vector';"
```
Expected: a row for `vector` (RDS PG16 ships pgvector ≥0.5 → HNSW supported). If absent, raise the PG minor version.

- [ ] **Step 5: Commit**

```bash
git add infra/terraform/environments/prod/db-bootstrap.sql
git commit -m "infra(prod): saalr_app DB role bootstrap + pgvector preflight"
```

---

## Phase 4 — Compute: ALB + ECS services + migrations

### Task 4.1: ECS cluster, task roles, ALB, log group

**Files:**
- Create: `infra/terraform/environments/prod/compute.tf` (cluster + ALB + IAM roles section)

**Interfaces:**
- Produces: `aws_ecs_cluster.main` (`saalr-prod-cluster`), `aws_iam_role.ecs_task_exec`, `aws_iam_role.ecs_task`, `aws_lb.main`, default target group + HTTPS listener; outputs `alb_dns_name`, `alb_arn`, `alb_listener_arn`.

- [ ] **Step 1: Write cluster + roles + ALB**

```hcl
resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"
  setting { name = "containerInsights", value = "enabled" }   # credits cover it; useful for beta
}
resource "aws_cloudwatch_log_group" "ecs" { name = "/ecs/${var.name_prefix}", retention_in_days = 30 }

# Execution role: pull from ECR, read secrets, write logs
resource "aws_iam_role" "ecs_task_exec" {
  name = "${var.name_prefix}-task-exec"
  assume_role_policy = jsonencode({ Version="2012-10-17", Statement=[{ Effect="Allow", Principal={Service="ecs-tasks.amazonaws.com"}, Action="sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "exec_managed" {
  role = aws_iam_role.ecs_task_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
resource "aws_iam_role_policy" "exec_secrets" {
  role = aws_iam_role.ecs_task_exec.id
  policy = jsonencode({ Version="2012-10-17", Statement=[{ Effect="Allow",
    Action=["secretsmanager:GetSecretValue"],
    Resource=[aws_secretsmanager_secret.app_db.arn, aws_secretsmanager_secret.admin_db.arn, aws_secretsmanager_secret.app_runtime.arn, module.data.db_master_secret_arn] }] })
}
# Task role: app's own AWS calls (S3 transcripts bucket, etc.)
resource "aws_iam_role" "ecs_task" {
  name = "${var.name_prefix}-task"
  assume_role_policy = aws_iam_role.ecs_task_exec.assume_role_policy
}

resource "aws_lb" "main" {
  name               = "${var.name_prefix}-alb"
  load_balancer_type = "application"
  internal           = false                  # CloudFront reaches it over the internet origin
  subnets            = module.network.public_subnets
  security_groups    = [module.network.alb_sg]
}
resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.network.vpc_id
  health_check { path = "/healthz", matcher = "200" }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.web.arn          # SAN cert also covers ALB host
  default_action { type = "forward", target_group_arn = aws_lb_target_group.api.arn }
}
```

> Note: the ALB is internet-facing so CloudFront can use it as a custom origin, but its SG only admits 443; add a CloudFront-managed-prefix-list ingress restriction in a later hardening pass so only CloudFront can reach it.

- [ ] **Step 2: Apply + verify + commit**

Run: `terraform apply -target=aws_ecs_cluster.main -target=aws_lb.main -target=aws_lb_listener.https`
Run: `aws ecs describe-clusters --clusters saalr-prod-cluster --query 'clusters[0].status'` → `"ACTIVE"`.
```bash
git add infra/terraform/environments/prod/compute.tf
git commit -m "infra(prod): ECS cluster, task roles, internet-facing ALB + HTTPS listener"
```

### Task 4.2: Reusable `ecs-service` module + the three services

**Files:**
- Create: `infra/terraform/modules/ecs-service/{main,variables,outputs}.tf`
- Modify: `infra/terraform/environments/prod/compute.tf` (instantiate api/research/backtest)

**Interfaces:**
- Consumes: cluster arn, subnets, app SG, exec/task role arns, log group, secret arns, image tag.
- Produces: per-service `aws_ecs_service` named `saalr-prod-<app>` (matches `deploy.yml` service names) + task def.

- [ ] **Step 1: Write modules/ecs-service/main.tf**

```hcl
resource "aws_ecs_task_definition" "this" {
  family                   = "${var.name_prefix}-${var.app}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu               # "256"
  memory                   = var.memory            # "512"
  execution_role_arn       = var.exec_role_arn
  task_role_arn            = var.task_role_arn
  runtime_platform { cpu_architecture = "ARM64", operating_system_family = "LINUX" }  # Graviton: ~20% cheaper
  container_definitions = jsonencode([{
    name      = var.app
    image     = "${var.ecr_registry}/${var.name_prefix}/${var.app}:${var.image_tag}"
    essential = true
    portMappings = var.expose_port == 0 ? [] : [{ containerPort = var.expose_port }]
    environment = [
      { name = "AUTH_PROVIDER", value = "clerk" },
      { name = "AWS_REGION",    value = var.region },
      { name = "WEB_BASE_URL",  value = "https://${var.domain_name}" },
      { name = "CORS_ALLOW_ORIGINS", value = "https://${var.domain_name}" }
    ]
    secrets = [
      { name = "APP_DATABASE_URL", valueFrom = var.app_db_secret_arn },
      { name = "MASSIVE_API_KEY",      valueFrom = "${var.runtime_secret_arn}:MASSIVE_API_KEY::" },
      { name = "OPENAI_API_KEY",       valueFrom = "${var.runtime_secret_arn}:OPENAI_API_KEY::" },
      { name = "ANTHROPIC_API_KEY",    valueFrom = "${var.runtime_secret_arn}:ANTHROPIC_API_KEY::" },
      { name = "STRIPE_SECRET_KEY",    valueFrom = "${var.runtime_secret_arn}:STRIPE_SECRET_KEY::" },
      { name = "STRIPE_WEBHOOK_SECRET",valueFrom = "${var.runtime_secret_arn}:STRIPE_WEBHOOK_SECRET::" },
      { name = "CLERK_JWKS_URL",       valueFrom = "${var.runtime_secret_arn}:CLERK_JWKS_URL::" },
      { name = "CLERK_ISSUER",         valueFrom = "${var.runtime_secret_arn}:CLERK_ISSUER::" },
      { name = "REDIS_URL",            valueFrom = var.redis_url_secret_arn }
    ]
    logConfiguration = { logDriver = "awslogs", options = {
      "awslogs-group" = var.log_group, "awslogs-region" = var.region, "awslogs-stream-prefix" = var.app } }
  }])
}
resource "aws_ecs_service" "this" {
  name            = "${var.name_prefix}-${var.app}"
  cluster         = var.cluster_arn
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration { subnets = var.private_subnet_ids, security_groups = [var.app_sg] }
  deployment_circuit_breaker { enable = true, rollback = true }
  dynamic "load_balancer" {
    for_each = var.target_group_arn == "" ? [] : [1]
    content { target_group_arn = var.target_group_arn, container_name = var.app, container_port = var.expose_port }
  }
  lifecycle { ignore_changes = [task_definition] }   # CI rolls the image via update-service
}
```

> The `REDIS_URL` secret is a small per-env secret holding `redis://<cache_endpoint>:6379/0`; create it in `secrets.tf` and populate after Task 3.1 (the endpoint is known at apply time, so it can also be a plain `environment` var instead — simpler: set `REDIS_URL` as `environment` from `module.data.cache_endpoint`).

- [ ] **Step 2: Instantiate the three services in compute.tf**

```hcl
locals { services = {
  api             = { port = 8000, tg = aws_lb_target_group.api.arn, count = 1 }
  research-agent  = { port = 0,    tg = "",                          count = 1 }
  backtest-worker = { port = 0,    tg = "",                          count = 1 }
}}
module "service" {
  for_each = local.services
  source              = "../../modules/ecs-service"
  app                 = each.key
  expose_port         = each.value.port
  target_group_arn    = each.value.tg
  desired_count       = each.value.count
  cluster_arn         = aws_ecs_cluster.main.arn
  name_prefix         = var.name_prefix
  region              = var.region
  domain_name         = var.domain_name
  image_tag           = var.image_tag
  ecr_registry        = "${data.aws_caller_identity.me.account_id}.dkr.ecr.${var.region}.amazonaws.com"
  exec_role_arn       = aws_iam_role.ecs_task_exec.arn
  task_role_arn       = aws_iam_role.ecs_task.arn
  log_group           = aws_cloudwatch_log_group.ecs.name
  private_subnet_ids  = module.network.private_subnets
  app_sg              = module.network.app_sg
  app_db_secret_arn   = aws_secretsmanager_secret.app_db.arn
  runtime_secret_arn  = aws_secretsmanager_secret.app_runtime.arn
  redis_url_secret_arn = aws_secretsmanager_secret.redis_url.arn
  cpu = "256", memory = "512"
}
```

- [ ] **Step 3: Apply (services will fail health until images exist — that's expected; image push happens in Phase 7). Validate plan only here.**

Run: `terraform validate && terraform plan -target=module.service`
Expected: plan shows 3 task defs + 3 services. (Apply deferred to Phase 7 after first image push, OR apply now and let api stabilize after the first `deploy.yml` run.)

- [ ] **Step 4: Commit**

```bash
git add infra/terraform/modules/ecs-service infra/terraform/environments/prod/compute.tf
git commit -m "infra(prod): reusable Fargate service module + api/research/backtest services"
```

### Task 4.3: Migration run-task definition

**Files:**
- Modify: `infra/terraform/environments/prod/compute.tf`

**Interfaces:**
- Produces: task def `saalr-prod-migrate` (overrides entrypoint to run alembic with `ADMIN_DATABASE_URL`). Invoked by CI before service rollout.

- [ ] **Step 1: Add a migrate task def (reuses the api image; overrides command)**

```hcl
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${var.name_prefix}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu = "256", memory = "512"
  execution_role_arn = aws_iam_role.ecs_task_exec.arn
  task_role_arn      = aws_iam_role.ecs_task.arn
  runtime_platform { cpu_architecture = "ARM64", operating_system_family = "LINUX" }
  container_definitions = jsonencode([{
    name = "migrate"
    image = "${data.aws_caller_identity.me.account_id}.dkr.ecr.${var.region}.amazonaws.com/${var.name_prefix}/api:${var.image_tag}"
    essential = true
    command = ["uv","run","--no-sync","alembic","-c","infra/migrations/alembic.ini","upgrade","head"]
    secrets = [{ name = "ADMIN_DATABASE_URL", valueFrom = aws_secretsmanager_secret.admin_db.arn }]
    logConfiguration = { logDriver = "awslogs", options = {
      "awslogs-group" = aws_cloudwatch_log_group.ecs.name, "awslogs-region" = var.region, "awslogs-stream-prefix" = "migrate" } }
  }])
}
```

- [ ] **Step 2: Validate + commit**

Run: `terraform validate`
```bash
git add infra/terraform/environments/prod/compute.tf
git commit -m "infra(prod): one-off ECS migrate task (alembic upgrade head as admin role)"
```

---

## Phase 5 — Delivery: S3 + CloudFront + DNS records

### Task 5.1: Web S3 bucket

**Files:**
- Create: `infra/terraform/modules/web-delivery/{main,variables,outputs}.tf`
- Create: `infra/terraform/environments/prod/delivery.tf`

**Interfaces:**
- Produces: `web_bucket` (output for `deploy-web.yml` var `WEB_BUCKET`), `cloudfront_distribution_id` (var `WEB_DISTRIBUTION_ID`).

- [ ] **Step 1: Write web bucket (private, OAC-only)**

```hcl
resource "aws_s3_bucket" "web" { bucket = "${var.name_prefix}-web-${data.aws_caller_identity.me.account_id}" }
resource "aws_s3_bucket_public_access_block" "web" {
  bucket = aws_s3_bucket.web.id
  block_public_acls = true, block_public_policy = true, ignore_public_acls = true, restrict_public_buckets = true
}
```

- [ ] **Step 2: Apply + commit**

Run: `terraform apply -target=aws_s3_bucket.web`
```bash
git add infra/terraform/modules/web-delivery infra/terraform/environments/prod/delivery.tf
git commit -m "infra(prod): private S3 bucket for the static web app"
```

### Task 5.2: CloudFront distribution (S3 default origin + `/api/*` → ALB)

**Files:**
- Modify: `infra/terraform/environments/prod/delivery.tf`
- Modify: `infra/terraform/environments/prod/outputs.tf`

**Interfaces:**
- Consumes: `aws_acm_certificate_validation.web`, `aws_s3_bucket.web`, `aws_lb.main.dns_name`.
- Produces: distribution; outputs `web_bucket`, `cloudfront_distribution_id`, `cloudfront_domain_name`.

- [ ] **Step 1: Write OAC + distribution with two origins and the `/api/*` behavior**

```hcl
resource "aws_cloudfront_origin_access_control" "web" {
  name = "${var.name_prefix}-web-oac", origin_access_control_origin_type = "s3"
  signing_behavior = "always", signing_protocol = "sigv4"
}
resource "aws_cloudfront_distribution" "web" {
  enabled = true, default_root_object = "index.html"
  aliases = [var.domain_name, "www.${var.domain_name}"]

  origin {
    origin_id                = "s3-web"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }
  origin {
    origin_id   = "alb-api"
    domain_name = aws_lb.main.dns_name
    custom_origin_config { http_port = 80, https_port = 443, origin_protocol_policy = "https-only", origin_ssl_protocols = ["TLSv1.2"] }
  }

  default_cache_behavior {
    target_origin_id = "s3-web", viewer_protocol_policy = "redirect-to-https"
    allowed_methods = ["GET","HEAD","OPTIONS"], cached_methods = ["GET","HEAD"]
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"   # Managed-CachingOptimized
  }
  ordered_cache_behavior {
    path_pattern     = "/api/*"
    target_origin_id = "alb-api", viewer_protocol_policy = "redirect-to-https"
    allowed_methods  = ["GET","HEAD","OPTIONS","PUT","POST","PATCH","DELETE"]
    cached_methods   = ["GET","HEAD"]
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"   # Managed-CachingDisabled
    origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"   # Managed-AllViewerExceptHostHeader
  }
  # SPA fallback: serve index.html for client-routed paths
  custom_error_response { error_code = 403, response_code = 200, response_page_path = "/index.html" }
  custom_error_response { error_code = 404, response_code = 200, response_page_path = "/index.html" }

  viewer_certificate { acm_certificate_arn = aws_acm_certificate.web.arn, ssl_support_method = "sni-only", minimum_protocol_version = "TLSv1.2_2021" }
  restrictions { geo_restriction { restriction_type = "none" } }
  price_class = "PriceClass_100"
}
# Let CloudFront read the private bucket via OAC
data "aws_iam_policy_document" "web_bucket" {
  statement {
    actions = ["s3:GetObject"], resources = ["${aws_s3_bucket.web.arn}/*"]
    principals { type = "Service", identifiers = ["cloudfront.amazonaws.com"] }
    condition { test = "StringEquals", variable = "AWS:SourceArn", values = [aws_cloudfront_distribution.web.arn] }
  }
}
resource "aws_s3_bucket_policy" "web" { bucket = aws_s3_bucket.web.id, policy = data.aws_iam_policy_document.web_bucket.json }
```

- [ ] **Step 2: Add outputs**

```hcl
output "web_bucket"                 { value = aws_s3_bucket.web.id }
output "cloudfront_distribution_id" { value = aws_cloudfront_distribution.web.id }
output "cloudfront_domain_name"     { value = aws_cloudfront_distribution.web.domain_name }
```

- [ ] **Step 3: Apply + verify + commit**

Run: `terraform apply -target=aws_cloudfront_distribution.web`
Run: `terraform output cloudfront_domain_name` → `dxxxx.cloudfront.net`.
```bash
git add infra/terraform/environments/prod/delivery.tf infra/terraform/environments/prod/outputs.tf
git commit -m "infra(prod): CloudFront with S3 default origin + /api/* -> ALB (same-origin, no CORS)"
```

### Task 5.3: Route 53 alias records → CloudFront

**Files:**
- Modify: `infra/terraform/environments/prod/dns.tf`

**Interfaces:**
- Consumes: `aws_route53_zone.primary`, `aws_cloudfront_distribution.web`.

- [ ] **Step 1: Add apex + www alias records**

```hcl
resource "aws_route53_record" "apex" {
  zone_id = aws_route53_zone.primary.zone_id, name = var.domain_name, type = "A"
  alias { name = aws_cloudfront_distribution.web.domain_name, zone_id = "Z2FDTNDATAQYW2", evaluate_target_health = false }
}
resource "aws_route53_record" "www" {
  zone_id = aws_route53_zone.primary.zone_id, name = "www.${var.domain_name}", type = "A"
  alias { name = aws_cloudfront_distribution.web.domain_name, zone_id = "Z2FDTNDATAQYW2", evaluate_target_health = false }
}
```
(`Z2FDTNDATAQYW2` is CloudFront's fixed hosted-zone id.)

- [ ] **Step 2: Apply + verify + commit**

Run: `terraform apply -target=aws_route53_record.apex -target=aws_route53_record.www`
Run: `dig +short saalr.io` → CloudFront IPs (after propagation).
```bash
git add infra/terraform/environments/prod/dns.tf
git commit -m "infra(prod): Route53 alias records saalr.io + www -> CloudFront"
```

---

## Phase 6 — Scheduled workers

### Task 6.1: Reusable `ecs-scheduled` module + 4 schedules

**Files:**
- Create: `infra/terraform/modules/ecs-scheduled/{main,variables,outputs}.tf`
- Create: `infra/terraform/environments/prod/scheduled.tf`

**Interfaces:**
- Produces: task defs `saalr-prod-<worker>` (no service) + EventBridge Scheduler schedules invoking `ecs:RunTask`.

- [ ] **Step 1: Write the module (task def + schedule + scheduler role)**

```hcl
resource "aws_ecs_task_definition" "this" {
  family = "${var.name_prefix}-${var.app}"
  requires_compatibilities = ["FARGATE"], network_mode = "awsvpc", cpu = var.cpu, memory = var.memory
  execution_role_arn = var.exec_role_arn, task_role_arn = var.task_role_arn
  runtime_platform { cpu_architecture = "ARM64", operating_system_family = "LINUX" }
  container_definitions = jsonencode([{
    name = var.app
    image = "${var.ecr_registry}/${var.name_prefix}/${var.app}:${var.image_tag}"
    essential = true
    secrets = [
      { name = "APP_DATABASE_URL", valueFrom = var.app_db_secret_arn },
      { name = "REDIS_URL",        valueFrom = var.redis_url_secret_arn },
      { name = "MASSIVE_API_KEY",  valueFrom = "${var.runtime_secret_arn}:MASSIVE_API_KEY::" }
    ]
    logConfiguration = { logDriver = "awslogs", options = {
      "awslogs-group" = var.log_group, "awslogs-region" = var.region, "awslogs-stream-prefix" = var.app } }
  }])
}
resource "aws_scheduler_schedule" "this" {
  name = "${var.name_prefix}-${var.app}"
  flexible_time_window { mode = "OFF" }
  schedule_expression = var.schedule           # e.g. "rate(15 minutes)" / "cron(0 6 * * ? *)"
  target {
    arn      = var.cluster_arn
    role_arn = var.scheduler_role_arn
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.this.arn
      launch_type         = "FARGATE"
      network_configuration { subnets = var.private_subnet_ids, security_groups = [var.app_sg] }
    }
  }
}
```
(Plus a `scheduler.amazonaws.com` assume-role with `ecs:RunTask` + `iam:PassRole` on the task/exec roles — define once in `scheduled.tf`.)

- [ ] **Step 2: Instantiate the 4 workers with cadences in scheduled.tf**

```hcl
locals { schedules = {
  ingest-worker  = "rate(15 minutes)"
  ml-worker      = "cron(0 6 * * ? *)"
  content-worker = "cron(0 3 * * ? *)"
  oms-worker     = "rate(5 minutes)"          # adjust to OMS reconciliation cadence
}}
module "scheduled" {
  for_each = local.schedules
  source   = "../../modules/ecs-scheduled"
  app = each.key, schedule = each.value
  # ...same wiring inputs as module.service (cluster, roles, subnets, sg, secrets, registry, image_tag)...
}
```

- [ ] **Step 3: Validate + commit**

Run: `terraform validate && terraform plan -target=module.scheduled`
```bash
git add infra/terraform/modules/ecs-scheduled infra/terraform/environments/prod/scheduled.tf
git commit -m "infra(prod): EventBridge-scheduled Fargate task-defs for ingest/oms/ml/content"
```

---

## Phase 7 — Wire CI to prod + first deploy

### Task 7.1: Repoint workflows to `saalr-prod` + add migrate step

**Files:**
- Modify: `.github/workflows/deploy.yml`, `.github/workflows/deploy-web.yml`

**Interfaces:**
- Consumes: outputs `gha_deploy_role_arn`, `web_bucket`, `cloudfront_distribution_id`.

- [ ] **Step 1: Update deploy.yml env + matrix names dev→prod**

Change `ECS_CLUSTER: saalr-dev-cluster` → `saalr-prod-cluster`; repo paths `saalr-dev/<app>` → `saalr-prod/<app>`; services `saalr-dev-*` → `saalr-prod-*`.

- [ ] **Step 2: Add a migrate gate before service rollout (api image already pushed in the matrix)**

```yaml
  migrate:
    needs: deploy
    runs-on: ubuntu-latest
    permissions: { id-token: write, contents: read }
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with: { role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}, aws-region: us-east-1 }
      - name: Run alembic migrate task
        run: |
          aws ecs run-task --cluster saalr-prod-cluster --launch-type FARGATE \
            --task-definition saalr-prod-migrate \
            --network-configuration "awsvpcConfiguration={subnets=[<priv-subnet-ids>],securityGroups=[<app-sg>]}" \
            --query 'tasks[0].taskArn' --output text
```
(Subnet/SG ids come from `terraform output`; wire them as repo variables `PRIV_SUBNETS`, `APP_SG`.)

- [ ] **Step 3: Set GitHub repo secrets/vars (MANUAL via gh CLI)**

```bash
gh secret set AWS_DEPLOY_ROLE_ARN   -b "$(terraform output -raw gha_deploy_role_arn)"
gh variable set WEB_BUCKET          -b "$(terraform output -raw web_bucket)"
gh variable set WEB_DISTRIBUTION_ID -b "$(terraform output -raw cloudfront_distribution_id)"
gh variable set SITE_ORIGIN         -b "https://saalr.io"
gh variable set VITE_AUTH_PROVIDER  -b "clerk"
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy.yml .github/workflows/deploy-web.yml
git commit -m "ci(prod): repoint deploy workflows to saalr-prod + alembic migrate gate"
```

### Task 7.2: First deploy + service stabilization

- [ ] **Step 1: Trigger image build/push + service rollout**

Run: `gh workflow run "Deploy to ECS"` then watch: `gh run watch`
Expected: 7 images pushed; api/research/backtest services reach steady state.

- [ ] **Step 2: Apply remaining Terraform (services now have images)**

Run: `terraform apply` (full)
Run: `aws ecs describe-services --cluster saalr-prod-cluster --services saalr-prod-api --query 'services[0].deployments[0].rolloutState'`
Expected: `"COMPLETED"`.

- [ ] **Step 3: Deploy web**

Run: `gh workflow run "Deploy web (S3 + CloudFront)"`
Expected: `dist/client` synced to S3, CloudFront invalidated.

- [ ] **Step 4: Commit any tfvars/id wiring; no code commit if clean.**

---

## Phase 8 — Cutover verification

### Task 8.1: End-to-end smoke test on saalr.io

- [ ] **Step 1: TLS + web**

Run: `curl -sI https://saalr.io | head -5`
Expected: `HTTP/2 200`, `server: CloudFront`.

- [ ] **Step 2: Same-origin API through CloudFront**

Run: `curl -s https://saalr.io/api/healthz`  (or the api's health route under /api)
Expected: `200` JSON health — confirms `/api/*` → ALB → ECS path and **no CORS** (same origin).

- [ ] **Step 3: DB-backed endpoint + auth**

Sign in with Clerk on `https://saalr.io`; load a page that reads from Postgres (e.g. content/academy). Expected: data renders; ECS api logs show `saalr_app` DB connections, no permission errors.

- [ ] **Step 4: Scheduled worker fired**

Run: `aws logs tail /ecs/saalr-prod --since 20m --filter-pattern ingest`
Expected: an ingest-worker run logged on its schedule.

- [ ] **Step 5: mcp-edge data-class go-live gate (app-side)**

Confirm non-owner principals resolve to DELAYED (per `apps/mcp-edge`), since public signups are external recipients under OPRA. Run the existing property tests against the deployed config path before opening signups:
Run: `uv run pytest tests/mcp/ -q`
Expected: 16 passed; and a manual check that `mcp_owner_user_ids` in prod config contains only your user_id.

- [ ] **Step 6: Cost guardrails**

Set a budget alarm and check the credit balance/expiry:
```bash
aws budgets create-budget --account-id <acct> --budget '{"BudgetName":"saalr-prod-monthly","BudgetLimit":{"Amount":"250","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}'
```
Note the Activate credit expiry date (Billing → Credits) and add a calendar reminder ~60 days prior to right-size before the cliff.

---

## Self-Review notes

- **Spec coverage:** web→S3/CloudFront ✓, API+consumers→ECS services ✓, scheduled workers→EventBridge ✓, RDS Postgres+pgvector ✓, Redis→ElastiCache ✓, OIDC role ✓, saalr.io delegation+ACM+alias ✓, same-origin `/api` (CORS memory) ✓, secrets ✓, migrations ✓, cost guardrails + credit cliff ✓, mcp-edge go-live gate ✓.
- **Deferred (with triggers):** RDS Multi-AZ/replicas (paying users), 3rd AZ+NAT-per-AZ (first SLA), Fargate Spot for workers (credit expiry), CloudFront-prefix-list ALB lockdown (hardening pass), Vike SSR (SEO/GEO slice), staging env.
- **Naming consistency:** every named resource uses `saalr-prod` / `${var.name_prefix}`; service names match `deploy.yml` after Task 7.1; container port `8000` matches the API Dockerfile contract.
- **Known follow-ups intentionally light on literal HCL:** `variables.tf`/`outputs.tf` for the modules (signatures stated inline) and the scheduler assume-role policy (described in Task 6.1 Step 1).
