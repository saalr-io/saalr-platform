# Go-live: deploy the web app (S3 + CloudFront)

The Vike build (`apps/web/dist/client`) is hosted on a private S3 bucket behind one CloudFront
distribution that also fronts the API ALB at `/api/*`.

## Architecture

- **S3 (private)** holds the static build; CloudFront reads it via Origin Access Control (the bucket
  has public access fully blocked). The default behavior serves it.
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
