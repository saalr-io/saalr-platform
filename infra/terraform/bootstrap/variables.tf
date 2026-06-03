variable "region" {
  description = "AWS region for the Terraform state backend."
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = "Globally-unique S3 bucket for Terraform state (append a unique suffix, e.g. your account id)."
  type        = string
  default     = "saalr-terraform-state"
}

variable "lock_table_name" {
  description = "DynamoDB table name for Terraform state locking."
  type        = string
  default     = "saalr-terraform-locks"
}
