variable "name_prefix" {
  description = "Prefix for resource names and tags."
  type        = string
}

variable "vpc_id" {
  description = "VPC id (from the network module)."
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block (default SG ingress source)."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet ids for the DB/cache subnet groups."
  type        = list(string)
}

variable "ingress_cidr_blocks" {
  description = "CIDR blocks allowed to reach the data tier; empty => [vpc_cidr]."
  type        = list(string)
  default     = []
}

variable "app_security_group_id" {
  description = "ECS app SG allowed to reach the data tier (SG-to-SG); empty => CIDR-only."
  type        = string
  default     = ""
}

variable "db_engine_version" {
  description = "Postgres major version."
  type        = string
  default     = "16"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage (GB, gp3)."
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Initial database name."
  type        = string
  default     = "saalr"
}

variable "db_username" {
  description = "Master username (password is RDS-managed in Secrets Manager)."
  type        = string
  default     = "saalr_admin"
}

variable "db_multi_az" {
  description = "Multi-AZ RDS (prod on, dev off)."
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "RDS deletion protection (dev off so destroy works)."
  type        = bool
  default     = false
}

variable "db_skip_final_snapshot" {
  description = "Skip the final snapshot on destroy (dev true)."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "RDS automated backup retention (days)."
  type        = number
  default     = 7
}

variable "redis_engine_version" {
  description = "ElastiCache Redis engine version."
  type        = string
  default     = "7.1"
}

variable "redis_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}
