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
dns_zone_name     = "saalr.io"
netlify_site_host = "storied-llama-1beb21.netlify.app"

# Apex/www stay on Netlify (zero-downtime) until the AWS app is deployed + verified.
# Phase 2d cutover: set apex_on_netlify=false AND web_domain_name="saalr.io".
apex_on_netlify = true
web_domain_name = ""

# Prod hardening.
db_multi_az            = true
db_deletion_protection = true
db_skip_final_snapshot = false
db_instance_class      = "db.t4g.small"

# GOVERNANCE (root can override) for beta. Switch to "COMPLIANCE" (IRREVERSIBLE, 365-day lock)
# only when going to regulated production — see README.
audit_object_lock_mode = "GOVERNANCE"
