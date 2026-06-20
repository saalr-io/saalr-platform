variable "name_prefix" {
  description = "Prefix for resource names, tags, and the KMS alias."
  type        = string
}

variable "bucket_prefix" {
  description = "Globally-unique S3 bucket name prefix (set a unique suffix, e.g. your account id)."
  type        = string
}

variable "audit_object_lock_mode" {
  description = "Object Lock retention mode for the audit bucket (GOVERNANCE for dev, COMPLIANCE for prod)."
  type        = string
  default     = "GOVERNANCE"
}

variable "audit_retention_days" {
  description = "Default Object Lock retention (days) for the audit bucket."
  type        = number
  default     = 365
}

variable "secret_names" {
  description = "Secrets Manager secret containers to create (values are set out-of-band, never in state)."
  type        = list(string)
  default = [
    "saalr/brokers/alpaca-paper",
    "saalr/app/openai",
    "saalr/app/anthropic",
    "saalr/app/massive",
    "saalr/app/fred",
    "saalr/app/stripe",
  ]
}

variable "secret_recovery_window_days" {
  description = "Recovery window (days) for deleted secrets."
  type        = number
  default     = 7
}

variable "kms_deletion_window_days" {
  description = "Deletion window (days) for the KMS key."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
