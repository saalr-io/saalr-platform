variable "name_prefix" {
  description = "Prefix for resource names and tags."
  type        = string
}

variable "ephemeral_storage_gib" {
  description = "Fargate task ephemeral storage (GiB, 21-200). 0 keeps the 20 GiB default. Raise for large images (e.g. CUDA torch)."
  type        = number
  default     = 0
}

variable "vpc_id" {
  description = "VPC id (from the network module)."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet ids for the internet-facing ALB."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Private subnet ids for the Fargate tasks."
  type        = list(string)
}

variable "app_security_group_id" {
  description = "ECS app security group (from the compute module); ALB ingress is added to it here."
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

variable "db_secret_arn" {
  description = "RDS-managed master-password secret ARN; granted to the execution role for injection."
  type        = string
}

variable "task_role_arn" {
  description = "ECS task role ARN (from the compute module)."
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

variable "image" {
  description = "Full container image URI (ECR repo URL + tag)."
  type        = string
}

variable "container_port" {
  description = "Port the API container listens on."
  type        = number
  default     = 8000
}

variable "desired_count" {
  description = "Number of API tasks."
  type        = number
  default     = 1
}

variable "cpu" {
  description = "Fargate task CPU units (string)."
  type        = string
  default     = "512"
}

variable "memory" {
  description = "Fargate task memory MiB (string)."
  type        = string
  default     = "1024"
}

variable "health_check_path" {
  description = "ALB target-group health-check path."
  type        = string
  default     = "/healthz"
}

variable "environment" {
  description = "Plain environment variables for the container (name => value)."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secret env vars for the container (name => Secrets Manager valueFrom ARN)."
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
