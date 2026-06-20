variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "bucket_prefix" {
  description = "Globally-unique prefix for all S3 bucket names (transcripts/ml-models/audit/web). MUST be globally unique — set a unique suffix before apply."
  type        = string
  default     = "saalr-prod"
}

variable "vpc_cidr" {
  description = "CIDR block for the prod VPC. Non-overlapping with dev (10.0.0.0/16) so the VPCs can peer later if needed."
  type        = string
  default     = "10.1.0.0/16"
}

variable "azs" {
  description = "Availability zones to deploy subnets into."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ)."
  type        = list(string)
  default     = ["10.1.0.0/24", "10.1.1.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ)."
  type        = list(string)
  default     = ["10.1.10.0/24", "10.1.11.0/24"]
}

variable "single_nat_gateway" {
  description = "Use a single shared NAT gateway (cost-saving; set false for full AZ-redundancy)."
  type        = bool
  default     = true
}

variable "web_domain_name" {
  description = "Custom domain the WEB MODULE binds to CloudFront (cert + apex alias). Empty => CloudFront default domain. Kept empty until the app is deployed + verified; set to saalr.io only at the apex cutover (Phase 2d)."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# DNS — the Route 53 hosted zone + records are managed independently of the
# web module so the apex can be cut over deliberately (Phase 2d) rather than
# the instant CloudFront is created. See dns_records.tf and the README.
# ---------------------------------------------------------------------------

variable "dns_zone_name" {
  description = "Domain to create + manage a Route 53 public hosted zone for (e.g. saalr.io). Empty => no zone. Decoupled from web_domain_name so the zone persists across the apex cutover."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Stripe billing — non-secret price IDs (from your Stripe products). Secret key
# + webhook secret come from the saalr/app/stripe Secrets Manager container.
# Annual IDs are optional ("" => fall back to monthly).
# ---------------------------------------------------------------------------

variable "stripe_price_pro" {
  description = "Stripe price ID for the Pro monthly plan (price_...)."
  type        = string
  default     = ""
}

variable "stripe_price_premium" {
  description = "Stripe price ID for the Premium monthly plan (price_...)."
  type        = string
  default     = ""
}

variable "stripe_price_pro_annual" {
  description = "Stripe price ID for the Pro annual plan (optional)."
  type        = string
  default     = ""
}

variable "stripe_price_premium_annual" {
  description = "Stripe price ID for the Premium annual plan (optional)."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Prod hardening — data tier
# ---------------------------------------------------------------------------

variable "db_multi_az" {
  description = "Enable Multi-AZ standby for RDS (recommended true for prod)."
  type        = bool
  default     = true
}

variable "db_deletion_protection" {
  description = "Prevent accidental RDS instance deletion (recommended true for prod)."
  type        = bool
  default     = true
}

variable "db_skip_final_snapshot" {
  description = "Skip the final snapshot on destroy. Keep false for prod to preserve data."
  type        = bool
  default     = false
}

variable "db_instance_class" {
  description = "RDS instance class for prod."
  type        = string
  default     = "db.t4g.small"
}

# ---------------------------------------------------------------------------
# Prod hardening — storage tier
# ---------------------------------------------------------------------------

variable "audit_object_lock_mode" {
  description = "Object Lock retention mode for the audit bucket. GOVERNANCE for beta prod (root can override); switch to COMPLIANCE (irreversible, 365-day lock) only for regulated production."
  type        = string
  default     = "GOVERNANCE"
}
