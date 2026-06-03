# AWS-2a — Terraform skeleton + state bootstrap + network module (design)

**Status:** approved 2026-06-03
**Slice:** AWS-2a (first sub-slice of the Terraform foundation; HLD ADR-008 / §infra)
**Builds on:** AWS-1 (app-side cloud integrations). First piece of the IaC that provisions the cloud foundation the platform deploys onto.

## Goal

Stand up the Terraform foundation's **skeleton** — repo structure, version/provider pins, a remote-state backend (S3 + DynamoDB) with a one-time bootstrap, and the **network (VPC) module** — whose outputs (VPC id, subnet ids) every later module consumes. Acceptance is **static validation only** (`fmt` / `validate` / `tflint` via Docker); `plan`/`apply` against a real account are explicitly out of scope (run when the infra is funded).

## Approved decisions

1. **Validate-only acceptance** (no `apply`, no spend, no creds in this slice): `terraform fmt -check -recursive`, `terraform init -backend=false` + `terraform validate` per config dir, `tflint --recursive`, all via Docker images (`hashicorp/terraform`, `ghcr.io/terraform-linters/tflint`).
2. **S3 + DynamoDB remote state with a `bootstrap/`** (local state) that creates the state bucket + lock table once; environments use the S3 backend. Validated with `init -backend=false` so the bucket needn't exist yet.
3. **Single NAT gateway** (`var.single_nat_gateway = true`), cost-optimized; per-AZ HA NAT is a later toggle.

## Verification model

Terraform isn't installed locally, but Docker is. All checks run via containers (no AWS credentials, no provisioning):

```bash
TF="docker run --rm -v \"$(pwd):/work\" -w /work hashicorp/terraform:1.9"
# formatting (whole tree)
docker run --rm -v "$(pwd)/infra/terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
# validate each config dir (downloads the AWS provider via init; no creds needed with -backend=false)
docker run --rm -v "$(pwd)/infra/terraform:/work" -w /work/bootstrap        hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "$(pwd)/infra/terraform:/work" -w /work/bootstrap        hashicorp/terraform:1.9 validate
docker run --rm -v "$(pwd)/infra/terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "$(pwd)/infra/terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 validate
# lint
docker run --rm -v "$(pwd)/infra/terraform:/work" -w /work ghcr.io/terraform-linters/tflint --recursive
```

**Path caveat:** the repo path contains a space (`SAALR F2F`). Docker splits `-v src:dst` on the last `:`, so quote the whole `-v` argument; a space inside the quoted source path is fine. Validating `environments/dev` transitively validates `modules/network` (the env calls it), so the module is covered; a standalone `modules/network` validate is also run for a focused signal. If a Docker mount with the spaced path proves unworkable in this environment, the fallback is to copy `infra/terraform/` into a space-free temp dir for the validate run — the HCL is identical; only the mount path changes.

## Repo structure

```
infra/terraform/
  README.md                 # replaces the placeholder; the bootstrap → validate → plan → apply workflow
  .gitignore                # .terraform/  *.tfstate*  *.tfstate.backup  crash.log  (KEEP .terraform.lock.hcl)
  bootstrap/
    versions.tf  main.tf  variables.tf  outputs.tf
  modules/
    network/
      versions.tf  main.tf  variables.tf  outputs.tf
  environments/
    dev/
      versions.tf  main.tf  variables.tf  outputs.tf  terraform.tfvars
```

A `versions.tf` in each config/module pins:
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

## State backend bootstrap

`bootstrap/` uses **local state** (default backend) and creates the remote-state infrastructure once:
- `aws_s3_bucket` (the state bucket) + `aws_s3_bucket_versioning` (Enabled) + `aws_s3_bucket_server_side_encryption_configuration` (SSE-S3/AES256) + `aws_s3_bucket_public_access_block` (all four blocks true).
- `aws_dynamodb_table` lock table: hash key `LockID` (S), `billing_mode = "PAY_PER_REQUEST"`.
- `provider "aws" { region = var.region }` (default `us-east-1`).
- Variables: `region` (default `us-east-1`), `state_bucket_name`, `lock_table_name` (defaults `saalr-terraform-state`, `saalr-terraform-locks`). The bucket name must be globally unique — the default is documented as "set a unique suffix (e.g. your account id)".
- Outputs: `state_bucket`, `lock_table`.

The bootstrap is **not** part of the dev state; it's a manual one-time `apply` (out of scope to run now). Its outputs feed the dev backend config.

## Network module (`modules/network`)

**`main.tf`:**
- `aws_vpc` — `cidr_block = var.vpc_cidr`, `enable_dns_hostnames = true`, `enable_dns_support = true`.
- public subnets (one per AZ) — `aws_subnet` with `map_public_ip_on_launch = true`, CIDRs from `var.public_subnet_cidrs`, `availability_zone` from `var.azs`.
- private subnets (one per AZ) — `aws_subnet`, CIDRs from `var.private_subnet_cidrs`.
- `aws_internet_gateway` attached to the VPC.
- `aws_eip` (one, `domain = "vpc"`) + `aws_nat_gateway` (one, in the first public subnet) — created when `var.single_nat_gateway` (the HA toggle is a future `count`/per-AZ expansion).
- `aws_route_table` public → `0.0.0.0/0` via IGW, associated to the public subnets; `aws_route_table` private → `0.0.0.0/0` via the NAT, associated to the private subnets.
- All resources tagged via `merge(var.tags, { Name = "${var.name_prefix}-..." })`.

Subnet/AZ fan-out uses `count` over `var.azs` (length-aligned with the CIDR lists), keeping the module simple and `validate`-clean.

**`variables.tf`:** `name_prefix`, `vpc_cidr`, `azs` (list(string)), `public_subnet_cidrs` (list), `private_subnet_cidrs` (list), `single_nat_gateway` (bool, default `true`), `tags` (map, default `{}`).

**`outputs.tf`:** `vpc_id`, `vpc_cidr`, `public_subnet_ids` (list), `private_subnet_ids` (list), `nat_gateway_id`, `public_route_table_id`, `private_route_table_id`. These are the contract AWS-2b (RDS/ElastiCache subnet groups + SG VPC), 2c, and 2d (ECS/ALB subnets + SGs) consume.

No security groups and no VPC flow logs in this module (SGs ship with the services that own them; flow logs are a later hardening).

## Dev environment (`environments/dev`)

**`main.tf`:**
```hcl
terraform {
  backend "s3" {
    bucket         = "saalr-terraform-state"     # the bootstrap bucket (set your unique name)
    key            = "dev/network.tfstate"
    region         = "us-east-1"
    dynamodb_table = "saalr-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "saalr"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

module "network" {
  source              = "../../modules/network"
  name_prefix         = "saalr-dev"
  vpc_cidr            = var.vpc_cidr
  azs                 = var.azs
  public_subnet_cidrs = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway  = var.single_nat_gateway
}
```

**`variables.tf` / `terraform.tfvars`** dev defaults:
```hcl
region               = "us-east-1"
vpc_cidr             = "10.0.0.0/16"
azs                  = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.0.0.0/24", "10.0.1.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]
single_nat_gateway   = true
```

**`outputs.tf`** re-exports the module outputs (`vpc_id`, `public_subnet_ids`, `private_subnet_ids`, etc.) so later environments/stacks can reference them (eventually via `terraform_remote_state`).

The `backend "s3"` block uses literal bucket/table names; validation runs with `init -backend=false`, so the bucket needn't exist. The `default_tags` on the provider tag every resource (belt-and-suspenders with the module's `Name` tags).

## Conventions

- `terraform >= 1.6`, `aws ~> 5.0` pinned in every `versions.tf`.
- Region `us-east-1` (ADR-008; ap-south-1 region-pinning is a later, Phase-4 concern).
- Naming `${name_prefix}-<resource>`; tags `Project`/`Environment`/`ManagedBy` (provider `default_tags` + module `Name`).
- `.terraform.lock.hcl` (provider checksum lock) **is committed**; `.terraform/`, `*.tfstate*`, `crash.log` git-ignored via `infra/terraform/.gitignore` (the root `.gitignore` is untouched — a protected file).
- The implementer must NOT stage `.terraform/` or any `*.tfstate` produced by `init`/`validate`.

## Out of scope (AWS-2b → 2e / later)

RDS (TimescaleDB) + ElastiCache + subnet groups + their SGs (2b); Secrets Manager secrets + S3 buckets (transcripts/audit-Object-Lock/ML-models) + KMS (2c); ECR + ECS cluster/task-defs/services + internal ALB + EventBridge scheduled tasks + IAM task/exec roles + CloudWatch log groups + autoscaling (2d); CI/CD image build+push+deploy (2e); VPC flow logs; per-AZ HA NAT; the `prod` environment; ap-south-1 region-pinning; `terraform plan`/`apply` against the account; `terraform test` (.tftest.hcl).

## Runbook / README

`infra/terraform/README.md` (replacing the placeholder) documents: the directory layout; the one-time bootstrap (`cd bootstrap && terraform init && terraform apply` to create the state bucket + lock table, with the unique-bucket-name note); per-environment usage (`cd environments/dev && terraform init && terraform plan`); the Docker-based validate/fmt/tflint commands (the acceptance gate, copied from the Verification model above); and an explicit note that `apply` provisions billable infra (single NAT ≈ $32/mo) and is run deliberately, not in CI, for this slice.
