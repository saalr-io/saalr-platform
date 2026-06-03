output "kms_key_arn" {
  description = "ARN of the data-encryption KMS key."
  value       = aws_kms_key.this.arn
}

output "kms_key_id" {
  description = "Id of the KMS key."
  value       = aws_kms_key.this.key_id
}

output "kms_alias" {
  description = "Alias of the KMS key."
  value       = aws_kms_alias.this.name
}

output "transcripts_bucket" {
  description = "Name of the research-transcripts bucket."
  value       = aws_s3_bucket.transcripts.id
}

output "ml_models_bucket" {
  description = "Name of the ML-models bucket."
  value       = aws_s3_bucket.ml_models.id
}

output "audit_bucket" {
  description = "Name of the audit-log (Object Lock) bucket."
  value       = aws_s3_bucket.audit.id
}

output "secret_arns" {
  description = "Map of secret name => ARN for the created Secrets Manager containers."
  value       = { for k, s in aws_secretsmanager_secret.this : k => s.arn }
}
