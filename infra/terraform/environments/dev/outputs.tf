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
