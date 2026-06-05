# Go-live: first apply (bootstrap → dev stack → images → web)

The end-to-end sequence to stand up the dev environment from scratch. Run from a machine with the
**terraform CLI** and **AWS credentials** for the target account (`aws configure` / SSO / `AWS_*`
env). This repo's CI uses GitHub OIDC for deploys, but the initial `apply` is run by an operator.

> ⚠️ This provisions **real, billable** infrastructure: a VPC + NAT gateway(s), RDS, ElastiCache, an
> ALB, ECS Fargate, CloudFront, S3, KMS, Secrets Manager, IAM. Review `terraform plan` before
> applying, and `terraform destroy` when you are done evaluating.

## 0. One-time choices

- **`STATE_BUCKET`** — a globally-unique S3 bucket name for Terraform state (e.g. `saalr-tfstate-<acct-or-random>`).
- **`LOCK_TABLE`** — a DynamoDB table name for state locks (e.g. `saalr-terraform-locks`).
- **`BUCKET_PREFIX`** — a globally-unique prefix for the app S3 buckets (e.g. `saalr-dev-<suffix>`);
  set it in `infra/terraform/environments/dev/terraform.tfvars` (`bucket_prefix`).
- Region: `us-east-1` (matches `terraform.tfvars` + the CloudFront ACM requirement).

## 1. Bootstrap the Terraform state backend (local state)

```bash
cd infra/terraform/bootstrap
terraform init
terraform apply \
  -var="state_bucket_name=$STATE_BUCKET" \
  -var="lock_table_name=$LOCK_TABLE"
# outputs: state_bucket, lock_table
```

## 2. Initialise the dev stack against that backend

The dev `backend "s3"` block cannot use variables — pass the bootstrap names at init time:

```bash
cd ../environments/dev
terraform init \
  -backend-config="bucket=$STATE_BUCKET" \
  -backend-config="dynamodb_table=$LOCK_TABLE"
```

## 3. Set the unique bucket prefix + plan

Edit `terraform.tfvars` → `bucket_prefix = "<your unique prefix>"`. Then:

```bash
terraform plan
```

Review the plan. (Optional custom domain: set `web_domain_name` + `web_route53_zone_id` in
`terraform.tfvars` — the domain must already be in a Route53 hosted zone; ACM is provisioned in
us-east-1. Empty => the default `*.cloudfront.net` domain.)

## 4. Apply

```bash
terraform apply
```

Key outputs: `ecr_repository_urls`, `ecs_cluster_name`, `api_alb_dns_name`, `gha_deploy_role_arn`,
`web_bucket`, `cloudfront_distribution_id`, `cloudfront_domain_name`, `db_master_user_secret_arn`,
`secret_arns`.

## 5. Populate secrets (out-of-band — never in Terraform state)

Set the Secrets Manager values the API/workers read (the secrets themselves are created by Terraform;
their values are not):

```bash
for s in openai anthropic massive fred; do
  aws secretsmanager put-secret-value --secret-id "saalr/app/$s" --secret-string "<key>"
done
```

The RDS master DB secret is AWS-managed; the app builds `APP_DATABASE_URL` from
`DB_HOST/PORT/USER/NAME/PASSWORD` at startup (the password is injected from the managed secret).

## 6. Build & push the service images

Push all seven images to ECR (`saalr-dev/<app>` — note the **slash**). Either run the
`Deploy to ECS` GitHub Action (after step 7's CI setup) or do it manually — see
[`go-live-images.md`](go-live-images.md).

## 7. Wire CI/CD (GitHub repo secrets + variables)

- Secret `AWS_DEPLOY_ROLE_ARN` = the `gha_deploy_role_arn` output.
- Variables `WEB_BUCKET` = `web_bucket`, `WEB_DISTRIBUTION_ID` = `cloudfront_distribution_id`,
  `VITE_AUTH_PROVIDER` (`dev` or `clerk`), `SITE_ORIGIN` (e.g. `https://saalr.com` or the CloudFront
  domain).

Then run the `Deploy to ECS` and `Deploy web (S3 + CloudFront)` workflows (both manual). To make them
continuous, swap `workflow_dispatch` → `push: { branches: [master] }`.

## 8. Deploy the web app

Run the `Deploy web (S3 + CloudFront)` workflow, or manually — see [`go-live-web.md`](go-live-web.md)
(`pnpm build` → `aws s3 sync dist/client … --delete` → CloudFront invalidate).

## Verify

- `https://<cloudfront_domain_name>/` serves the landing page; `/learn`, `/glossary/theta`,
  `/academy` resolve (the dir-index function); `/app` boots the SPA (the SPA-fallback function);
  `/api/healthz` reaches the API (the `/api` strip + ALB origin).

## Teardown

```bash
# dev stack first, then bootstrap (the state backend) last
cd infra/terraform/environments/dev && terraform destroy
cd ../bootstrap && terraform destroy -var="state_bucket_name=$STATE_BUCKET" -var="lock_table_name=$LOCK_TABLE"
```

(Empty the S3 buckets — including the web bucket — before destroy if `force_delete`/versioning blocks
it.)
