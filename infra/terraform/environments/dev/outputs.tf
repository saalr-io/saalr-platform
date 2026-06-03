output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "nat_gateway_id" {
  value = module.network.nat_gateway_id
}

output "db_endpoint" {
  value = module.data.db_endpoint
}

output "db_master_user_secret_arn" {
  value = module.data.db_master_user_secret_arn
}

output "redis_endpoint" {
  value = module.data.redis_endpoint
}

output "transcripts_bucket" {
  value = module.storage.transcripts_bucket
}

output "audit_bucket" {
  value = module.storage.audit_bucket
}

output "kms_key_arn" {
  value = module.storage.kms_key_arn
}

output "secret_arns" {
  value = module.storage.secret_arns
}

output "ecr_repository_urls" {
  value = module.compute.ecr_repository_urls
}

output "ecs_cluster_name" {
  value = module.compute.cluster_name
}

output "task_role_arn" {
  value = module.compute.task_role_arn
}

output "api_alb_dns_name" {
  value = module.api_service.alb_dns_name
}

output "gha_deploy_role_arn" {
  value = module.cicd.deploy_role_arn
}
