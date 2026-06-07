variable "name_prefix" {
  description = "Prefix for resource names and tags."
  type        = string
}

variable "vpc_id" {
  description = "VPC id (from the network module)."
  type        = string
}

variable "ecr_repo_names" {
  description = "ECR repositories to create (one per deployable image)."
  type        = list(string)
  default = [
    "api",
    "ingest-worker",
    "backtest-worker",
    "oms-worker",
    "research-agent",
    "ml-worker",
    "content-worker",
  ]
}

variable "s3_bucket_names" {
  description = "S3 bucket names the task role may read/write (from the storage module)."
  type        = list(string)
}

variable "secret_arns" {
  description = "Secrets Manager secret ARNs the task/execution roles may read."
  type        = list(string)
}

variable "kms_key_arn" {
  description = "KMS key ARN used to decrypt the buckets/secrets."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention (days)."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
