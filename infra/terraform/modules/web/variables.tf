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
