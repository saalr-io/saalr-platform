output "db_endpoint" {
  description = "RDS endpoint address."
  value       = aws_db_instance.this.address
}

output "db_port" {
  description = "RDS port."
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "Initial database name."
  value       = aws_db_instance.this.db_name
}

output "db_master_user_secret_arn" {
  description = "ARN of the RDS-managed master-password secret in Secrets Manager."
  value       = try(aws_db_instance.this.master_user_secret[0].secret_arn, null)
}

output "rds_security_group_id" {
  description = "Security group id for the RDS instance."
  value       = aws_security_group.rds.id
}

output "redis_endpoint" {
  description = "ElastiCache Redis node endpoint address."
  value       = aws_elasticache_cluster.this.cache_nodes[0].address
}

output "redis_port" {
  description = "Redis port."
  value       = aws_elasticache_cluster.this.port
}

output "redis_security_group_id" {
  description = "Security group id for the Redis cluster."
  value       = aws_security_group.redis.id
}
