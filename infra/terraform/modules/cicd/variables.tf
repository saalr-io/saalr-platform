variable "name_prefix" {
  description = "Prefix for resource names and tags."
  type        = string
}

variable "github_owner" {
  description = "GitHub org/user that owns the repo (for the OIDC sub condition)."
  type        = string
  default     = "spayyavula"
}

variable "github_repo" {
  description = "GitHub repository name (for the OIDC sub condition)."
  type        = string
  default     = "saalr-platform"
}

variable "ecr_repository_arns" {
  description = "ECR repository ARNs the deploy role may push to."
  type        = list(string)
}

variable "passable_role_arns" {
  description = "IAM role ARNs the deploy role may PassRole (ECS execution + task roles)."
  type        = list(string)
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider (set false if the account already has one)."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
