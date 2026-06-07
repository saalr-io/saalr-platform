# Web static deploy (S3 + CloudFront) — design

**Status:** approved design, 2026-06-05. A go-live follow-up; the Dockerfiles + CI/CD deploy
workflow shipped earlier. The Terraform foundation (network/data/storage/compute/api_service/
workers/cicd) is already authored.

## Goal

Host the Vike build (`apps/web/dist/client` — statically prerendered public pages + the
client-only `/app` SPA) on a private S3 bucket behind one CloudFront distribution that ALSO fronts
the API ALB for same-origin `/api` (no CORS, no backend change), plus a GitHub Actions deploy
workflow. **Author + offline-verify only** — `terraform apply` and the first deploy need AWS creds.

## Current state (relevant facts)

- `apps/web` is Vike with global `prerender: true`; `/app/*` opts out (`ssr:false`, client-only,
  `<BrowserRouter basename="/app">`). The build emits prerendered `…/index.html` for public routes
  (`/`, `/learn/<slug>/`, `/academy/<slug>/`, `/glossary` + `/glossary/<slug>/`) and a client shell
  at `dist/client/app/index.html` for the SPA. Hashed assets live under `/assets/*`; `sitemap.xml`,
  `llms.txt`, `llms-full.txt`, `robots.txt`, `favicon.svg` are real files at the root.
- The web client calls `BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'` then `${BASE}/v1/...`.
- The API ALB listens on **HTTP :80** (`module.api_service` `aws_lb_listener "http"`), output as
  `module.api_service.alb_dns_name`. The FastAPI routes have NO `/api` prefix (`/v1/...`, `/me`,
  `/healthz`, `/auth/...`).
- The `cicd` module's OIDC deploy role currently grants ECR push + ECS deploy only.
- Module convention: `versions.tf` = `required_version >= 1.6`, `aws ~> 5.0`. The storage module is
  the S3 pattern (KMS, versioning, public-access-block). The `terraform` CLI is NOT installed
  locally — verify via the dockerized `hashicorp/terraform` image.

## Decisions (locked)

- **CloudFront fronts both** the static site (S3, default behavior) AND the API (ALB origin, `/api/*`
  behavior) → the SPA calls same-origin `/api/v1/...`, no CORS.
- **Custom domain is optional, variable-gated** (`web_domain_name`, default `""`): empty → the default
  `*.cloudfront.net` domain (apply-able today); set → ACM (us-east-1) + Route53 alias + CloudFront
  aliases, all `count`-gated.

## Architecture — one distribution, two origins, two functions

**Origin A — private S3 bucket** (`${bucket_prefix}-web`): `block_public_*` all on; SSE-S3 (AES256 —
simpler than KMS for CloudFront-read public content); read via an **Origin Access Control** (sigv4);
a bucket policy granting `s3:GetObject` to the distribution only (`Condition` on
`AWS:SourceArn = <distribution ARN>`). Default cache behavior → this origin, `redirect-to-https`,
caching enabled (long max-age for `/assets/*`, short for HTML).

**Origin B — the API ALB** (`alb_domain_name`, `custom_origin_config` HTTP-only, port 80; CloudFront
terminates TLS at the edge — ALB-origin TLS is a hardening follow-up). Ordered cache behavior
`/api/*` → this origin, `CachingDisabled` + `AllViewer` origin-request policy (forward all
headers/cookies/query), all methods (GET/HEAD/OPTIONS/PUT/POST/PATCH/DELETE).

**CloudFront Function 1 (viewer-request) on the DEFAULT behavior — directory index + SPA fallback:**
```js
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  // SPA: /app and any /app/* without a file extension -> the client shell
  if (uri === '/app' || uri.indexOf('/app/') === 0) {
    if (uri.indexOf('.') === -1) { request.uri = '/app/index.html'; }
    return request; // assets under /app (have a dot) pass through
  }
  // SSG directory URLs -> index.html
  if (uri.endsWith('/')) { request.uri = uri + 'index.html'; }
  else if (uri.indexOf('.') === -1) { request.uri = uri + '/index.html'; }
  return request;
}
```
(Real files — `/assets/x.js`, `/sitemap.xml`, `/llms.txt`, `/favicon.svg` — contain a dot and pass
through unchanged.)

**CloudFront Function 2 (viewer-request) on the `/api/*` behavior — strip the prefix:**
```js
function handler(event) {
  var request = event.request;
  request.uri = request.uri.replace(/^\/api/, '');
  if (request.uri === '') { request.uri = '/'; }
  return request;
}
```
So `/api/v1/strategies` → `/v1/strategies` reaches the FastAPI ALB.

**Viewer certificate / aliases:** `web_domain_name == ""` → `cloudfront_default_certificate = true`,
no aliases. Else → `acm_certificate_arn` (us-east-1, DNS-validated) + `aliases = [web_domain_name]` +
`ssl_support_method = "sni-only"` + `minimum_protocol_version = "TLSv1.2_2021"`.

## Files

- **`infra/terraform/modules/web/`** *(new)* — `versions.tf` (`aws ~> 5.0` with
  `configuration_aliases = [aws.us_east_1]`), `variables.tf` (`name_prefix`, `bucket_prefix`,
  `alb_domain_name`, `web_domain_name = ""`, `route53_zone_id = ""` optional, `tags = {}`), `main.tf`
  (bucket + public-access-block + SSE + OAC + bucket policy + the 2 `aws_cloudfront_function`s +
  `aws_cloudfront_distribution` + the `count`-gated `aws_acm_certificate` [`provider = aws.us_east_1`]
  + validation + `aws_route53_record` alias), `outputs.tf` (`bucket`, `bucket_arn`, `distribution_id`,
  `distribution_arn`, `distribution_domain_name`).
- **`infra/terraform/environments/dev/`** — `versions.tf` (or `main.tf`): declare the
  `aws.us_east_1` aliased provider (CloudFront ACM must be us-east-1). `main.tf`: a `module "web"`
  block passing `alb_domain_name = module.api_service.alb_dns_name`, `web_domain_name =
  var.web_domain_name`, `providers = { aws.us_east_1 = aws.us_east_1 }`; pass `web_bucket_arn` +
  `cloudfront_distribution_arn` to `module "cicd"`. `variables.tf`: `web_domain_name` (default `""`)
  + `web_route53_zone_id` (default `""`). `outputs.tf`: `web_bucket`, `cloudfront_domain_name`,
  `cloudfront_distribution_id`.
- **`infra/terraform/modules/cicd/`** — add `web_bucket_arn = ""` + `cloudfront_distribution_arn = ""`
  variables; when non-empty, add an S3 statement (`s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket`
  on the bucket + `/*`) and a CloudFront statement (`cloudfront:CreateInvalidation` on the
  distribution ARN) to the deploy policy (`dynamic` blocks gated on the var). Existing apply with the
  vars empty is unchanged.
- **`.github/workflows/deploy-web.yml`** *(new)* — `workflow_dispatch`; `permissions: id-token:
  write, contents: read`; OIDC `configure-aws-credentials` with `role-to-assume:
  secrets.AWS_DEPLOY_ROLE_ARN`; `pnpm/action-setup@v4` (v10) + `setup-node@v4` (node 22, pnpm cache);
  `pnpm install --frozen-lockfile` (in `apps/web`); `pnpm build` with env `VITE_API_BASE_URL=/api`,
  `VITE_AUTH_PROVIDER=${{ vars.VITE_AUTH_PROVIDER }}`, `SITE_ORIGIN=${{ vars.SITE_ORIGIN }}`; then
  `aws s3 sync apps/web/dist/client "s3://${{ vars.WEB_BUCKET }}" --delete`; then `aws cloudfront
  create-invalidation --distribution-id "${{ vars.WEB_DISTRIBUTION_ID }}" --paths "/*"`.
- **`docs/runbooks/go-live-web.md`** — build env vars; the S3 sync + invalidation; the `/api` routing
  + the two CloudFront Functions; `web_domain_name`/`web_route53_zone_id` wiring; the
  **ACM-must-be-us-east-1** note; the repo vars/secrets to set (`AWS_DEPLOY_ROLE_ARN`, `WEB_BUCKET`,
  `WEB_DISTRIBUTION_ID`, `VITE_AUTH_PROVIDER`, `SITE_ORIGIN`).

## Error handling

The SPA-fallback function makes every `/app/*` resolve to `/app/index.html` (200). Genuine public
404s return S3's 404 unmasked (no `custom_error_response` remap, so real 404s stay 404 for SEO). The
`/api/*` behavior disables caching so API responses are never cached. Build is reproducible
(`--frozen-lockfile`).

## Testing / verification (offline — no AWS creds)

- **`terraform fmt`** the new + edited `.tf` (dockerized `hashicorp/terraform fmt -recursive` since
  the CLI isn't installed locally). **`terraform validate`** the dev env if feasible: dockerized
  `terraform -chdir=infra/terraform/environments/dev init -backend=false && … validate` (downloads
  the aws provider; no creds needed). If the provider download is impractical, fall back to careful
  review + `fmt`, and note that `validate`/`plan` must be run in CI/by the operator.
- **`actionlint`** `deploy-web.yml` (dockerized; on Windows run via PowerShell `${PWD}` mount).
- **`pnpm build`** `apps/web` and assert the build output the functions assume exists:
  `dist/client/app/index.html` (SPA shell), `dist/client/index.html`, a sample
  `dist/client/glossary/theta/index.html`, and `dist/client/assets/` — confirming the directory-index
  + SPA-fallback rewrites target real files.
- No `terraform apply`. Existing pytest/web suites are untouched.

## Out of scope (follow-ups)

The actual `terraform apply` + first deploy (AWS creds); ALB-origin TLS + a dedicated API subdomain;
WAF; CloudFront access logging to the audit bucket; cache-policy fine-tuning beyond the
static/HTML/api split; `content-worker`-style image follow-ups (already done).
