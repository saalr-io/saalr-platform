variable "name_prefix" {
  description = "Prefix for resource names and tags."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet ids for the Fargate tasks."
  type        = list(string)
}

variable "app_security_group_id" {
  description = "ECS app security group (from the compute module)."
  type        = string
}

variable "cluster_arn" {
  description = "ECS cluster ARN (from the compute module)."
  type        = string
}

variable "execution_role_arn" {
  description = "ECS task-execution role ARN (from the compute module)."
  type        = string
}

variable "execution_role_name" {
  description = "ECS task-execution role NAME (to attach the DB-secret read policy)."
  type        = string
}

variable "task_role_arn" {
  description = "ECS task role ARN (from the compute module)."
  type        = string
}

variable "db_secret_arn" {
  description = "RDS-managed master-password secret ARN; granted to the execution role for injection."
  type        = string
}

variable "log_group_name" {
  description = "CloudWatch log group (from the compute module)."
  type        = string
}

variable "aws_region" {
  description = "AWS region (for the awslogs driver)."
  type        = string
}

variable "cpu" {
  description = "Fargate task CPU units (string), shared across workers (per-worker sizing is a later refinement)."
  type        = string
  default     = "512"
}

variable "memory" {
  description = "Fargate task memory MiB (string), shared across workers."
  type        = string
  default     = "1024"
}

variable "environment" {
  description = "Plain environment variables for every worker container (name => value)."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secret env vars for every worker container (name => Secrets Manager valueFrom ARN)."
  type        = map(string)
  default     = {}
}

variable "scheduled_workers" {
  description = "EventBridge-scheduled workers: name => { image, command, schedule_expression }."
  type = map(object({
    image               = string
    command             = list(string)
    schedule_expression = string
  }))
  default = {}
}

variable "service_workers" {
  description = "Long-running consumer workers: name => { image, command, desired_count }."
  type = map(object({
    image         = string
    command       = list(string)
    desired_count = number
  }))
  default = {}
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
