output "alb_dns_name" {
  description = "Public DNS name of the API ALB."
  value       = aws_lb.this.dns_name
}

output "alb_arn" {
  description = "ARN of the API ALB."
  value       = aws_lb.this.arn
}

output "target_group_arn" {
  description = "ARN of the API target group."
  value       = aws_lb_target_group.this.arn
}

output "service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.this.name
}

output "task_definition_arn" {
  description = "ECS task-definition ARN."
  value       = aws_ecs_task_definition.this.arn
}

output "alb_security_group_id" {
  description = "Security group id of the API ALB."
  value       = aws_security_group.alb.id
}
