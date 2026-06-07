region = "us-east-1"

# MUST be globally unique across all of AWS S3 — change this suffix before apply
# (drives the transcripts/ml-models/audit/web bucket names).
bucket_prefix = "saalr-dev"


vpc_cidr             = "10.0.0.0/16"
azs                  = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.0.0.0/24", "10.0.1.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]
single_nat_gateway   = true
