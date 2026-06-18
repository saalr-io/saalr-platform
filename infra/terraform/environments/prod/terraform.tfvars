region = "us-east-1"

# MUST be globally unique across all of AWS S3 — append your account id or similar before apply.
bucket_prefix = "saalr-prod"

# Non-overlapping with dev (10.0.0.0/16) so the VPCs can peer later if needed.
vpc_cidr             = "10.1.0.0/16"
azs                  = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.1.0.0/24", "10.1.1.0/24"]
private_subnet_cidrs = ["10.1.10.0/24", "10.1.11.0/24"]
single_nat_gateway   = true

# Custom domain. Terraform creates the saalr.io hosted zone; delegate NS at the registrar.
web_domain_name = "saalr.io"

# Prod hardening.
db_multi_az            = true
db_deletion_protection = true
db_skip_final_snapshot = false
db_instance_class      = "db.t4g.small"

# GOVERNANCE (root can override) for beta. Switch to "COMPLIANCE" (IRREVERSIBLE, 365-day lock)
# only when going to regulated production — see README.
audit_object_lock_mode = "GOVERNANCE"
