output "deploy_role_arn" {
  description = "ARN of the role GitHub Actions assumes via OIDC to deploy."
  value       = aws_iam_role.deploy.arn
}

output "oidc_provider_arn" {
  description = "ARN of the GitHub Actions OIDC provider."
  value       = local.oidc_provider_arn
}
