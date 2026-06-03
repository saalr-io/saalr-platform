output "scheduled_task_definition_arns" {
  description = "Map of scheduled-worker name => task-definition ARN."
  value       = { for k, t in aws_ecs_task_definition.scheduled : k => t.arn }
}

output "service_task_definition_arns" {
  description = "Map of service-worker name => task-definition ARN."
  value       = { for k, t in aws_ecs_task_definition.service : k => t.arn }
}

output "service_names" {
  description = "Map of service-worker name => ECS service name."
  value       = { for k, s in aws_ecs_service.service : k => s.name }
}

output "events_role_arn" {
  description = "ARN of the EventBridge invoke role."
  value       = aws_iam_role.events.arn
}
