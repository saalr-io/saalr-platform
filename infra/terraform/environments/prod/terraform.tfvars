region = "us-east-1"

# MUST be globally unique across all of AWS S3 (account-id suffix).
bucket_prefix = "saalr-prod-992382415038"

# Non-overlapping with dev (10.0.0.0/16) so the VPCs can peer later if needed.
vpc_cidr             = "10.1.0.0/16"
azs                  = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.1.0.0/24", "10.1.1.0/24"]
private_subnet_cidrs = ["10.1.10.0/24", "10.1.11.0/24"]
single_nat_gateway   = true

# DNS: Terraform owns the saalr.io hosted zone + records (migrated off Netlify/NS1).
dns_zone_name = "saalr.io"

# Go-live: apex + www serve the AWS app via CloudFront (web module, include_www=true).
web_domain_name = "saalr.io"

# Prod hardening.
db_multi_az            = true
db_deletion_protection = true
db_skip_final_snapshot = false
db_instance_class      = "db.t4g.small"

# GOVERNANCE (root can override) for beta. Switch to "COMPLIANCE" (IRREVERSIBLE, 365-day lock)
# only when going to regulated production — see README.
audit_object_lock_mode = "GOVERNANCE"

# Stripe billing — non-secret price IDs from your Stripe products (test mode first).
# Secret key + webhook secret live in the saalr/app/stripe Secrets Manager container.
# Fill these with your real price_... IDs and re-apply. Annual is optional (""=monthly).
stripe_price_pro            = ""
stripe_price_premium        = ""
stripe_price_pro_annual     = ""
stripe_price_premium_annual = ""
