# Web static deploy (S3 + CloudFront) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Host `apps/web/dist/client` on a private S3 bucket behind one CloudFront distribution that also fronts the API ALB for same-origin `/api`, plus a deploy workflow. Author + offline-verify only. Spec: `docs/superpowers/specs/2026-06-05-web-static-deploy-design.md`.

**Architecture:** A new `modules/web` (S3 + OAC + CloudFront 2-origin/2-function + optional ACM/Route53), wired into `environments/dev`, with the `cicd` OIDC role extended for S3 + CloudFront, and a `deploy-web.yml` GitHub Actions workflow.

**Tech Stack:** Terraform (`aws ~> 5.0`), CloudFront Functions (cloudfront-js-2.0), GitHub Actions, pnpm/Vike.

**Conventions (apply to every task):**
- Commit footer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- NEVER stage `.terraform/` or `*.tfstate*`; DO commit `.terraform.lock.hcl` if a provider changes. Never modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`. Stage ONLY each task's files.
- The `terraform` CLI is NOT installed locally — `fmt`/`validate` run via the dockerized `hashicorp/terraform` image (Windows: PowerShell `${PWD}` mount).
- Mirror the existing module conventions (`modules/storage`, `modules/cicd`).

---

### Task 1: `modules/web` — S3 + CloudFront + functions + optional domain

**Files:** Create `infra/terraform/modules/web/{versions.tf,variables.tf,main.tf,outputs.tf}`.

- [ ] **Step 1: `versions.tf`** (declares the us-east-1 aliased provider requirement):

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 5.0"
      configuration_aliases = [aws.us_east_1]
    }
  }
}
```

- [ ] **Step 2: `variables.tf`**:

```hcl
variable "name_prefix" {
  description = "Prefix for resource names and tags."
  type        = string
}

variable "bucket_prefix" {
  description = "Globally-unique prefix for the web bucket name."
  type        = string
}

variable "alb_domain_name" {
  description = "DNS name of the API ALB (the /api/* origin)."
  type        = string
}

variable "web_domain_name" {
  description = "Custom domain (e.g. saalr.com). Empty => default CloudFront domain."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route53 hosted zone id for web_domain_name (required only when web_domain_name is set)."
  type        = string
  default     = ""
}

variable "price_class" {
  description = "CloudFront price class."
  type        = string
  default     = "PriceClass_100"
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
```

- [ ] **Step 3: `main.tf`**:

```hcl
locals {
  use_custom_domain = var.web_domain_name != ""
}

# --- Private S3 bucket for the static site ---
resource "aws_s3_bucket" "web" {
  bucket = "${var.bucket_prefix}-web"
  tags   = merge(var.tags, { Name = "${var.bucket_prefix}-web" })
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- Origin Access Control (CloudFront reads the private bucket via sigv4) ---
resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${var.name_prefix}-web-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# --- CloudFront Functions ---
resource "aws_cloudfront_function" "rewrite" {
  name    = "${var.name_prefix}-web-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Directory-index + SPA fallback for /app/*."
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;
      if (uri === '/app' || uri.indexOf('/app/') === 0) {
        if (uri.indexOf('.') === -1) { request.uri = '/app/index.html'; }
        return request;
      }
      if (uri.endsWith('/')) { request.uri = uri + 'index.html'; }
      else if (uri.indexOf('.') === -1) { request.uri = uri + '/index.html'; }
      return request;
    }
  EOT
}

resource "aws_cloudfront_function" "api_strip" {
  name    = "${var.name_prefix}-web-api-strip"
  runtime = "cloudfront-js-2.0"
  comment = "Strip the /api prefix before forwarding to the API ALB."
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      request.uri = request.uri.replace(/^\/api/, '');
      if (request.uri === '') { request.uri = '/'; }
      return request;
    }
  EOT
}

# --- AWS-managed cache/origin-request policies ---
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}
data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}
data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

# --- ACM cert (us-east-1) + Route53 validation, only with a custom domain ---
resource "aws_acm_certificate" "web" {
  count             = local.use_custom_domain ? 1 : 0
  provider          = aws.us_east_1
  domain_name       = var.web_domain_name
  validation_method = "DNS"
  tags              = merge(var.tags, { Name = "${var.name_prefix}-web-cert" })
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = local.use_custom_domain ? {
    for dvo in aws_acm_certificate.web[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  } : {}
  zone_id = var.route53_zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "web" {
  count                   = local.use_custom_domain ? 1 : 0
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.web[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# --- CloudFront distribution ---
resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = var.price_class
  comment             = "${var.name_prefix} web"
  aliases             = local.use_custom_domain ? [var.web_domain_name] : []
  tags                = merge(var.tags, { Name = "${var.name_prefix}-web" })

  origin {
    origin_id                = "s3"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  origin {
    origin_id   = "api"
    domain_name = var.alb_domain_name
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.rewrite.arn
    }
  }

  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.api_strip.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = local.use_custom_domain ? false : true
    acm_certificate_arn            = local.use_custom_domain ? aws_acm_certificate_validation.web[0].certificate_arn : null
    ssl_support_method             = local.use_custom_domain ? "sni-only" : null
    minimum_protocol_version       = local.use_custom_domain ? "TLSv1.2_2021" : null
  }
}

# --- Bucket policy: only this distribution may read ---
data "aws_iam_policy_document" "web_bucket" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.web.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.web.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = data.aws_iam_policy_document.web_bucket.json
}

# --- Optional Route53 alias to the distribution ---
resource "aws_route53_record" "web_alias" {
  count   = local.use_custom_domain ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.web_domain_name
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}
```

- [ ] **Step 4: `outputs.tf`**:

```hcl
output "bucket" {
  value = aws_s3_bucket.web.id
}
output "bucket_arn" {
  value = aws_s3_bucket.web.arn
}
output "distribution_id" {
  value = aws_cloudfront_distribution.web.id
}
output "distribution_arn" {
  value = aws_cloudfront_distribution.web.arn
}
output "distribution_domain_name" {
  value = aws_cloudfront_distribution.web.domain_name
}
```

- [ ] **Step 5: commit** (after Task 5's `fmt` pass; commit message):

```bash
git add infra/terraform/modules/web/
git commit -m "feat(infra): web module — private S3 + CloudFront (OAC, dir-index/SPA + /api-strip functions, optional ACM/Route53)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: extend `modules/cicd` for the web deploy grant

**Files:** Modify `infra/terraform/modules/cicd/variables.tf`, `infra/terraform/modules/cicd/main.tf`.

- [ ] **Step 1: add to `variables.tf`**:

```hcl
variable "web_bucket_arn" {
  description = "ARN of the web static-site S3 bucket (empty disables the S3 deploy grant)."
  type        = string
  default     = ""
}

variable "cloudfront_distribution_arn" {
  description = "ARN of the web CloudFront distribution (empty disables the invalidation grant)."
  type        = string
  default     = ""
}
```

- [ ] **Step 2: in `main.tf`**, inside the existing `data "aws_iam_policy_document" "deploy"` block, AFTER the `PassRole` statement (before the closing `}` of the data block), add:

```hcl
  dynamic "statement" {
    for_each = var.web_bucket_arn != "" ? [1] : []
    content {
      sid       = "WebS3Sync"
      actions   = ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetObject"]
      resources = [var.web_bucket_arn, "${var.web_bucket_arn}/*"]
    }
  }

  dynamic "statement" {
    for_each = var.cloudfront_distribution_arn != "" ? [1] : []
    content {
      sid       = "WebCloudFrontInvalidate"
      actions   = ["cloudfront:CreateInvalidation"]
      resources = [var.cloudfront_distribution_arn]
    }
  }
```

- [ ] **Step 3: commit** (with Task 3, after fmt):

```bash
git add infra/terraform/modules/cicd/variables.tf infra/terraform/modules/cicd/main.tf
git commit -m "feat(infra): cicd role — optional S3 sync + CloudFront invalidation grants for web deploy

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: wire `module "web"` + the us-east-1 provider into `environments/dev`

**Files:** Modify `infra/terraform/environments/dev/main.tf`, `variables.tf`, `outputs.tf`.

- [ ] **Step 1: add the us-east-1 aliased provider** to `main.tf` (right after the existing `provider "aws"` block):

```hcl
# CloudFront ACM certs must live in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = {
      Project     = "saalr"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}
```

- [ ] **Step 2: add the `module "web"` block** to `main.tf` (after `module "api_service"`):

```hcl
module "web" {
  source          = "../../modules/web"
  name_prefix     = "saalr-dev"
  bucket_prefix   = "saalr-dev" # globally-unique — set a unique suffix before apply
  alb_domain_name = module.api_service.alb_dns_name
  web_domain_name = var.web_domain_name
  route53_zone_id = var.web_route53_zone_id
  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }
}
```

- [ ] **Step 3: extend the `module "cicd"` block** in `main.tf` — add the two args:

```hcl
  web_bucket_arn              = module.web.bucket_arn
  cloudfront_distribution_arn = module.web.distribution_arn
```

- [ ] **Step 4: add to `variables.tf`**:

```hcl
variable "web_domain_name" {
  description = "Custom domain for the web app (e.g. saalr.com). Empty uses the default CloudFront domain."
  type        = string
  default     = ""
}

variable "web_route53_zone_id" {
  description = "Route53 hosted zone id for web_domain_name (only needed when web_domain_name is set)."
  type        = string
  default     = ""
}
```

- [ ] **Step 5: add to `outputs.tf`**:

```hcl
output "web_bucket" {
  value = module.web.bucket
}

output "cloudfront_domain_name" {
  value = module.web.distribution_domain_name
}

output "cloudfront_distribution_id" {
  value = module.web.distribution_id
}
```

- [ ] **Step 6: commit** (with Task 1+2, after fmt):

```bash
git add infra/terraform/environments/dev/main.tf infra/terraform/environments/dev/variables.tf infra/terraform/environments/dev/outputs.tf
git commit -m "feat(infra): wire web module + us-east-1 provider into dev; grant cicd role web deploy

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(Tasks 1–3 may be committed together after the Task 5 `fmt` pass; the separate commit messages above are fine to squash into the natural order.)

---

### Task 4: `deploy-web.yml` workflow + runbook

**Files:** Create `.github/workflows/deploy-web.yml`, `docs/runbooks/go-live-web.md`.

- [ ] **Step 1: create** `.github/workflows/deploy-web.yml`:

```yaml
# Build & deploy the static web app to S3 + CloudFront. Manual trigger only until activated.
#
# Prerequisites:
#   1. terraform apply the dev stack (creates the web bucket + CloudFront distribution and grants the
#      gha-deploy role S3 + cloudfront:CreateInvalidation).
#   2. Repo secret AWS_DEPLOY_ROLE_ARN = the gha_deploy_role_arn output.
#   3. Repo variables WEB_BUCKET + WEB_DISTRIBUTION_ID (from web_bucket / cloudfront_distribution_id),
#      and optionally VITE_AUTH_PROVIDER + SITE_ORIGIN.
#
# To activate on every push, replace `workflow_dispatch` with `push: { branches: [master], paths: [apps/web/**] }`.
name: Deploy web (S3 + CloudFront)

on:
  workflow_dispatch: {}

permissions:
  id-token: write # required for OIDC
  contents: read

env:
  AWS_REGION: us-east-1

jobs:
  deploy-web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
          cache-dependency-path: apps/web/pnpm-lock.yaml

      - run: pnpm install --frozen-lockfile

      - name: Build
        env:
          VITE_API_BASE_URL: /api
          VITE_AUTH_PROVIDER: ${{ vars.VITE_AUTH_PROVIDER }}
          SITE_ORIGIN: ${{ vars.SITE_ORIGIN }}
        run: pnpm build

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Sync to S3
        run: aws s3 sync dist/client "s3://${{ vars.WEB_BUCKET }}" --delete

      - name: Invalidate CloudFront
        run: aws cloudfront create-invalidation --distribution-id "${{ vars.WEB_DISTRIBUTION_ID }}" --paths "/*"
```

- [ ] **Step 2: create** `docs/runbooks/go-live-web.md`:

```markdown
# Go-live: deploy the web app (S3 + CloudFront)

The Vike build (`apps/web/dist/client`) is hosted on a private S3 bucket behind one CloudFront
distribution that also fronts the API ALB at `/api/*`.

## Architecture

- **S3 (private)** holds the static build; CloudFront reads it via Origin Access Control (the bucket
  has public access fully blocked). Default behavior serves it.
- **`/api/*` -> the API ALB** (origin B). A CloudFront Function strips the `/api` prefix, so the SPA's
  `/api/v1/...` reaches the FastAPI `/v1/...`. Same-origin => no CORS.
- A CloudFront Function on the default behavior rewrites directory URLs to `index.html` and sends
  `/app` + `/app/*` (no extension) to `/app/index.html` for the client-side router.

## Custom domain (optional)

Set `web_domain_name` (e.g. `saalr.com`) + `web_route53_zone_id` in the dev tfvars. Terraform then
provisions an ACM cert (**must be us-east-1** for CloudFront), DNS-validates it via Route53, adds the
CloudFront alias, and an A-alias record to the distribution. Empty => the default `*.cloudfront.net`
domain.

## Deploy

The `Deploy web (S3 + CloudFront)` workflow (manual) builds and ships it. One-time setup:

- Secret `AWS_DEPLOY_ROLE_ARN` = the `gha_deploy_role_arn` output.
- Variables `WEB_BUCKET` = `web_bucket` output, `WEB_DISTRIBUTION_ID` = `cloudfront_distribution_id`
  output, plus `VITE_AUTH_PROVIDER` (`dev` or `clerk`) and `SITE_ORIGIN` (e.g. `https://saalr.com`).

Manual equivalent:

```bash
cd apps/web
VITE_API_BASE_URL=/api SITE_ORIGIN=https://saalr.com pnpm build
aws s3 sync dist/client "s3://<web_bucket>" --delete
aws cloudfront create-invalidation --distribution-id "<distribution_id>" --paths "/*"
```

## Notes

- The build bakes env at build time (`VITE_API_BASE_URL`, `VITE_AUTH_PROVIDER`, `SITE_ORIGIN`) — a
  config change requires a rebuild + redeploy.
- Genuine public 404s return S3's 404 unmasked (real 404s stay 404 for SEO); only `/app/*` falls back
  to the SPA shell.
- CloudFront -> ALB is HTTP:80 (TLS terminates at the edge); ALB-origin TLS is a hardening follow-up.
```

- [ ] **Step 3: commit**:

```bash
git add .github/workflows/deploy-web.yml docs/runbooks/go-live-web.md
git commit -m "ci(deploy): web S3+CloudFront deploy workflow + runbook

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: verify (offline — fmt, validate, actionlint, pnpm build)

- [ ] **Step 1: `terraform fmt`** (dockerized; the CLI isn't installed). From the repo root, PowerShell:

```powershell
docker run --rm -v "${PWD}/infra/terraform:/tf" -w /tf hashicorp/terraform:latest fmt -recursive
```
Re-run with `-check` to confirm zero diffs after formatting. Stage any reformatting into the relevant task's commit.

- [ ] **Step 2: `terraform validate`** (best-effort; downloads the aws provider, NO creds needed via `-backend=false`). PowerShell:

```powershell
docker run --rm -v "${PWD}/infra/terraform:/tf" -w /tf/environments/dev hashicorp/terraform:latest init -backend=false
docker run --rm -v "${PWD}/infra/terraform:/tf" -w /tf/environments/dev hashicorp/terraform:latest validate
```
Expected: `Success! The configuration is valid.` If the provider download is impractical here, record that `validate`/`plan` must be run by the operator/CI, and rely on `fmt` + review. (Do NOT commit the `.terraform/` dir the init creates — it is gitignored under `infra/terraform/.gitignore`; confirm `git status` shows no `.terraform/` staged.)

- [ ] **Step 3: actionlint** the workflow (dockerized). PowerShell:

```powershell
docker run --rm -v "${PWD}:/repo" -w /repo rhysd/actionlint:latest -color .github/workflows/deploy-web.yml
```
Expected: no findings.

- [ ] **Step 4: `pnpm build` the web** and assert the build output the CloudFront Functions assume:

```bash
cd apps/web && pnpm build
```
Confirm these exist in `dist/client/`: `index.html`, `app/index.html` (the SPA shell), `glossary/theta/index.html` (a sample SSG page), and an `assets/` dir. If `app/index.html` is NOT produced, the SPA-fallback target is wrong — STOP and reconcile (the function targets `/app/index.html`).

- [ ] **Step 5: final `git status`** — confirm only the intended files are staged across the tasks, and that NO `.terraform/` or `*.tfstate*` is staged. Commit any outstanding fmt changes into the appropriate task commits.

---

## Self-Review notes (for the executor)

- **us-east-1 provider:** CloudFront ACM certs MUST be in us-east-1; the web module declares
  `configuration_aliases = [aws.us_east_1]` and dev passes `providers = { aws.us_east_1 = aws.us_east_1 }`.
- **OAC, not OAI:** the bucket stays fully private; only the distribution (by `AWS:SourceArn`) can read.
- **Two functions, one per behavior:** default behavior = dir-index/SPA rewrite; `/api/*` behavior =
  prefix strip. The `/api/*` behavior also disables caching + forwards AllViewer so auth headers/
  cookies reach the API.
- **viewer_certificate:** when `web_domain_name == ""`, `cloudfront_default_certificate = true` and the
  acm fields are `null`; when set, `false` + the validated ACM arn.
- **Don't apply.** Offline verification only; the runbook documents the apply + first deploy.
- **No `.terraform/`/tfstate** ever staged; `infra/terraform/.gitignore` already excludes them.
```
