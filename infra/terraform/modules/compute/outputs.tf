output "cluster_id" {
  description = "ECS cluster id."
  value       = aws_ecs_cluster.this.id
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.this.arn
}

output "ecr_repository_urls" {
  description = "Map of image name => ECR repository URL."
  value       = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}

output "task_execution_role_arn" {
  description = "ECS task-execution role ARN."
  value       = aws_iam_role.execution.arn
}

output "task_role_arn" {
  description = "ECS task role ARN (app runtime access)."
  value       = aws_iam_role.task.arn
}

output "app_security_group_id" {
  description = "Security group id for ECS app tasks."
  value       = aws_security_group.app.id
}

output "log_group_name" {
  description = "CloudWatch log group for ECS tasks."
  value       = aws_cloudwatch_log_group.ecs.name
}
