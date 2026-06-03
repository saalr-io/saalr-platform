# AWS-2a — Terraform skeleton + state bootstrap + network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This is Terraform (HCL), not application code — the acceptance gate is `terraform fmt`/`validate` + `tflint` run via Docker, NOT pytest. There is no `apply`.

**Goal:** Stand up the Terraform foundation skeleton — repo structure + version pins, an S3/DynamoDB remote-state backend with a one-time `bootstrap/`, and the network (VPC) module + a `dev` environment that wires it — all validated statically (no AWS account, no spend).

**Architecture:** `infra/terraform/{bootstrap,modules/network,environments/dev}`. The network module emits `vpc_id`/subnet-ids/etc. that AWS-2b–2d consume. `terraform >= 1.6`, `aws ~> 5.0`.

**Tech Stack:** Terraform (HCL), AWS provider v5, Docker (for `terraform`/`tflint` images).

**Spec:** `docs/superpowers/specs/2026-06-03-terraform-network-foundation-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. The path contains a space (`SAALR F2F`).
- **Run the Docker terraform/tflint commands via the PowerShell tool** (native Windows path; cleaner than git-bash MSYS mangling). Pattern (mount `infra/terraform` at `/work`):
  ```powershell
  docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
  docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/<dir> hashicorp/terraform:1.9 init -backend=false
  docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/<dir> hashicorp/terraform:1.9 validate
  docker run --rm -v "${PWD}\infra\terraform:/work" -w /work ghcr.io/terraform-linters/tflint --recursive
  ```
  Run these from the repo root (so `${PWD}` is the repo root). If the spaced-path mount fails in this environment, FALLBACK: `Copy-Item infra\terraform <temp-no-space> -Recurse` and mount that for the validate run (the HCL is identical). `init`/`validate` need network (to download the AWS provider) but NO AWS credentials.
- Lint: `uvx ruff check` is N/A here. The acceptance checks are `fmt -check` + `validate` (+ best-effort `tflint`).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. NEVER `git add -A`/`.`. **NEVER stage `.terraform/`, `*.tfstate*`, or `crash.log`** (created by `init`/`validate`); DO commit `.terraform.lock.hcl`. Never stage the root `.gitignore`, `.env`, `uv.lock`, or `tools/`.

---

### Task 1: Skeleton + state bootstrap

**Files:**
- Create: `infra/terraform/.gitignore`
- Create: `infra/terraform/README.md` (replaces the placeholder)
- Create: `infra/terraform/bootstrap/versions.tf`
- Create: `infra/terraform/bootstrap/variables.tf`
- Create: `infra/terraform/bootstrap/main.tf`
- Create: `infra/terraform/bootstrap/outputs.tf`

- [ ] **Step 1: Git-ignore + README**

Create `infra/terraform/.gitignore`:
```gitignore
# Terraform local artifacts — never commit these. (.terraform.lock.hcl IS committed.)
.terraform/
*.tfstate
*.tfstate.*
crash.log
crash.*.log
override.tf
override.tf.json
*_override.tf
*_override.tf.json
```

Create `infra/terraform/README.md` (the existing file is a one-line placeholder — overwrite it):
```markdown
# Terraform — Saalr cloud foundation

AWS single-cloud (ADR-008), region `us-east-1`. Terraform `>= 1.6`, AWS provider `~> 5.0`.

## Layout

    bootstrap/            one-time: creates the S3 state bucket + DynamoDB lock table (local state)
    modules/network/      VPC, subnets, IGW, single NAT, route tables (outputs consumed by later modules)
    environments/dev/     dev stack: S3 backend + the network module

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
```

- [ ] **Step 2: Bootstrap config**

Create `infra/terraform/bootstrap/versions.tf`:
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

Create `infra/terraform/bootstrap/variables.tf`:
```hcl
variable "region" {
  description = "AWS region for the Terraform state backend."
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = "Globally-unique S3 bucket for Terraform state (append a unique suffix, e.g. your account id)."
  type        = string
  default     = "saalr-terraform-state"
}

variable "lock_table_name" {
  description = "DynamoDB table name for Terraform state locking."
  type        = string
  default     = "saalr-terraform-locks"
}
```

Create `infra/terraform/bootstrap/main.tf`:
```hcl
provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "saalr"
      ManagedBy = "terraform"
      Component = "tf-state"
    }
  }
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "locks" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
```

Create `infra/terraform/bootstrap/outputs.tf`:
```hcl
output "state_bucket" {
  description = "S3 bucket holding Terraform state."
  value       = aws_s3_bucket.state.id
}

output "lock_table" {
  description = "DynamoDB table for state locking."
  value       = aws_dynamodb_table.locks.name
}
```

- [ ] **Step 3: Validate the bootstrap (Docker, via PowerShell)**

From the repo root, run (PowerShell tool):
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/bootstrap hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/bootstrap hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
```
Expected: `init` succeeds (downloads `hashicorp/aws ~> 5.0`); `validate` prints `Success! The configuration is valid.`; `fmt -check` exits 0 (no diff). If `fmt -check` flags files, run `... fmt -recursive` to fix, then re-check. If the spaced-path mount errors, use the temp-dir fallback (see conventions). If Docker/network is unavailable in this environment, say so and proceed — but the HCL must be hand-verified against the spec; note it in the report.

- [ ] **Step 4: Commit**

Confirm `git status` shows NO `.terraform/` or `*.tfstate` staged (the `.gitignore` covers them; if they appear, they are under `infra/terraform/bootstrap/.terraform/` and must NOT be added). Stage the source + the lock file:
```bash
git add infra/terraform/.gitignore infra/terraform/README.md infra/terraform/bootstrap/versions.tf infra/terraform/bootstrap/variables.tf infra/terraform/bootstrap/main.tf infra/terraform/bootstrap/outputs.tf
git add -f infra/terraform/bootstrap/.terraform.lock.hcl   # the provider lock IS committed (it's git-ignored only by pattern? no — add explicitly if needed)
git commit -m "feat(aws): terraform skeleton + S3/DynamoDB state bootstrap (AWS-2a)"
```
NOTE on the lock file: `.terraform.lock.hcl` is NOT matched by the `.gitignore` patterns above, so a plain `git add infra/terraform/bootstrap/.terraform.lock.hcl` works (drop the `-f`). Verify it is tracked. (Append the Co-Authored-By footer.)

---

### Task 2: Network (VPC) module

**Files:**
- Create: `infra/terraform/modules/network/versions.tf`
- Create: `infra/terraform/modules/network/variables.tf`
- Create: `infra/terraform/modules/network/main.tf`
- Create: `infra/terraform/modules/network/outputs.tf`

- [ ] **Step 1: Write the module**

Create `infra/terraform/modules/network/versions.tf`:
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

Create `infra/terraform/modules/network/variables.tf`:
```hcl
variable "name_prefix" {
  description = "Prefix for resource names and tags."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
}

variable "azs" {
  description = "Availability zones to spread subnets across."
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the public subnets (one per AZ)."
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for the private subnets (one per AZ)."
  type        = list(string)
}

variable "single_nat_gateway" {
  description = "Use a single shared NAT gateway (cost-optimized) instead of one per AZ."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
```

Create `infra/terraform/modules/network/main.tf`:
```hcl
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = merge(var.tags, { Name = "${var.name_prefix}-vpc" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Name = "${var.name_prefix}-igw" })
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = merge(var.tags, { Name = "${var.name_prefix}-public-${var.azs[count.index]}" })
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.azs[count.index]
  tags              = merge(var.tags, { Name = "${var.name_prefix}-private-${var.azs[count.index]}" })
}

resource "aws_eip" "nat" {
  count  = var.single_nat_gateway ? 1 : 0
  domain = "vpc"
  tags   = merge(var.tags, { Name = "${var.name_prefix}-nat-eip" })
}

resource "aws_nat_gateway" "this" {
  count         = var.single_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
  tags          = merge(var.tags, { Name = "${var.name_prefix}-nat" })
  depends_on    = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-public-rt" })
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[0].id
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-private-rt" })
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
```
(The private route table assumes `single_nat_gateway = true`; per-AZ HA NAT is a future expansion of this module, out of scope for AWS-2a.)

Create `infra/terraform/modules/network/outputs.tf`:
```hcl
output "vpc_id" {
  description = "VPC id."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "VPC CIDR block."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet ids."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet ids."
  value       = aws_subnet.private[*].id
}

output "nat_gateway_id" {
  description = "NAT gateway id (null if disabled)."
  value       = try(aws_nat_gateway.this[0].id, null)
}

output "public_route_table_id" {
  description = "Public route table id."
  value       = aws_route_table.public.id
}

output "private_route_table_id" {
  description = "Private route table id."
  value       = aws_route_table.private.id
}
```

- [ ] **Step 2: Validate the module standalone (Docker)**

From the repo root (PowerShell tool):
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/network hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/modules/network hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
```
Expected: `validate` → `Success! The configuration is valid.` (a module validates standalone; variables without defaults are fine for `validate` — no plan is run). `fmt -check` exits 0. Fix any `fmt` diff with `... fmt -recursive`.

- [ ] **Step 3: Commit**
```bash
git add infra/terraform/modules/network/versions.tf infra/terraform/modules/network/variables.tf infra/terraform/modules/network/main.tf infra/terraform/modules/network/outputs.tf
git add infra/terraform/modules/network/.terraform.lock.hcl   # if init created one here; verify it's tracked
git commit -m "feat(aws): terraform network (VPC) module — subnets, IGW, NAT, routes (AWS-2a)"
```
(Confirm no `.terraform/`/`*.tfstate` staged. Append the Co-Authored-By footer.)

---

### Task 3: Dev environment + whole-tree validation

**Files:**
- Create: `infra/terraform/environments/dev/versions.tf`
- Create: `infra/terraform/environments/dev/main.tf`
- Create: `infra/terraform/environments/dev/variables.tf`
- Create: `infra/terraform/environments/dev/outputs.tf`
- Create: `infra/terraform/environments/dev/terraform.tfvars`

- [ ] **Step 1: Write the dev stack**

Create `infra/terraform/environments/dev/versions.tf`:
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

Create `infra/terraform/environments/dev/main.tf`:
```hcl
terraform {
  backend "s3" {
    bucket         = "saalr-terraform-state" # set to the bootstrap bucket (your unique name)
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
  source               = "../../modules/network"
  name_prefix          = "saalr-dev"
  vpc_cidr             = var.vpc_cidr
  azs                  = var.azs
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway   = var.single_nat_gateway
}
```

Create `infra/terraform/environments/dev/variables.tf`:
```hcl
variable "region" {
  type    = string
  default = "us-east-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "single_nat_gateway" {
  type    = bool
  default = true
}
```

Create `infra/terraform/environments/dev/outputs.tf`:
```hcl
output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "nat_gateway_id" {
  value = module.network.nat_gateway_id
}
```

Create `infra/terraform/environments/dev/terraform.tfvars`:
```hcl
region               = "us-east-1"
vpc_cidr             = "10.0.0.0/16"
azs                  = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.0.0.0/24", "10.0.1.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]
single_nat_gateway   = true
```

- [ ] **Step 2: Validate dev (transitively validates the module) + whole-tree fmt + tflint**

From the repo root (PowerShell tool):
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 init -backend=false
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work/environments/dev hashicorp/terraform:1.9 validate
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive
```
Expected: `init -backend=false` initializes the provider + the `../../modules/network` module; `validate` → `Success! The configuration is valid.` (this exercises the env + the module together); `fmt -check` exits 0.

Then **tflint** (best-effort — the hard gate is `fmt` + `validate`):
```powershell
docker run --rm -v "${PWD}\infra\terraform:/work" -w /work ghcr.io/terraform-linters/tflint --recursive
```
Expected: tflint runs the core ruleset and reports no errors (the AWS provider plugin is not initialized, so this is HCL/best-practice lint only). If tflint flags anything, fix it; if the image/network is unavailable, note it and rely on `validate`.

- [ ] **Step 3: Commit**
```bash
git add infra/terraform/environments/dev/versions.tf infra/terraform/environments/dev/main.tf infra/terraform/environments/dev/variables.tf infra/terraform/environments/dev/outputs.tf infra/terraform/environments/dev/terraform.tfvars
git add infra/terraform/environments/dev/.terraform.lock.hcl   # if created; verify tracked
git commit -m "feat(aws): terraform dev environment wiring the network module (AWS-2a)"
```
(Confirm `git status` shows no `.terraform/`/`*.tfstate`; append the Co-Authored-By footer.)

---

## Final verification (after all tasks)

From the repo root (PowerShell tool), the full acceptance gate:
- [ ] `docker run --rm -v "${PWD}\infra\terraform:/work" -w /work hashicorp/terraform:1.9 fmt -check -recursive` — exit 0 (whole tree formatted).
- [ ] bootstrap: `init -backend=false` + `validate` → valid.
- [ ] modules/network: `init -backend=false` + `validate` → valid.
- [ ] environments/dev: `init -backend=false` + `validate` → valid (env + module together).
- [ ] `tflint --recursive` — no errors (best-effort).
- [ ] `git status` clean of `.terraform/` + `*.tfstate*`; `.terraform.lock.hcl` files tracked.
- [ ] **Final code-review subagent** over the whole AWS-2a diff (HCL correctness, security posture, the outputs contract).

## Self-review notes
- **Spec coverage:** `.gitignore` + README + bootstrap (T1); network module — VPC/subnets/IGW/single-NAT/routes/outputs (T2); dev env — S3 backend + provider default_tags + module call + tfvars + outputs (T3); validate-only acceptance via Docker throughout. All spec sections map to a task.
- **Consistency:** the module's variable names (`name_prefix`, `vpc_cidr`, `azs`, `public_subnet_cidrs`, `private_subnet_cidrs`, `single_nat_gateway`, `tags`) match the dev env's `module "network"` call; the module's outputs (`vpc_id`, `public_subnet_ids`, …) match the dev env's `outputs.tf` references; `aws ~> 5.0` idioms used throughout (`aws_eip.domain = "vpc"`, separate `aws_s3_bucket_versioning`/`_server_side_encryption_configuration` resources).
- **Deliberate choices flagged for the reviewer:** validate-only (no `apply`/`plan` against an account — Docker `init -backend=false` + `validate` is the gate); single NAT (private RT references `aws_nat_gateway.this[0]`; HA is a future toggle); no SGs/flow logs in 2a (deferred to the owning services); the `backend "s3"` bucket/table names are literals to be set after the bootstrap apply; `.terraform.lock.hcl` committed, `.terraform/`/state ignored.
- **Environment caveat:** the checks require Docker + network (to pull the terraform/tflint images + the AWS provider). If unavailable, the HCL is hand-verified against the spec and the reviewer scrutinizes it; this is the known ceiling for IaC verification without a terraform binary or AWS account.
