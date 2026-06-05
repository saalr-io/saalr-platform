variable "region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_prefix" {
  description = "Globally-unique prefix for all S3 bucket names (transcripts/ml-models/audit/web). MUST be globally unique — set a unique suffix before apply."
  type        = string
  default     = "saalr-dev"
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
