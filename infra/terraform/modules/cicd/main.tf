# --- GitHub Actions OIDC provider (one per account per URL) ---
resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_oidc_provider ? 1 : 0
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
  tags            = merge(var.tags, { Name = "${var.name_prefix}-github-oidc" })
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

# --- Deploy role assumed by GitHub Actions via OIDC, scoped to this repo ---
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_owner}/${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${var.name_prefix}-gha-deploy"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = merge(var.tags, { Name = "${var.name_prefix}-gha-deploy" })
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = var.ecr_repository_arns
  }
  statement {
    # RegisterTaskDefinition / UpdateService do not support resource-level scoping well;
    # tightening UpdateService to specific service ARNs is a later refinement.
    sid = "EcsDeploy"
    actions = [
      "ecs:RegisterTaskDefinition",
      "ecs:DeregisterTaskDefinition",
      "ecs:DescribeTaskDefinition",
      "ecs:DescribeServices",
      "ecs:UpdateService",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "PassRole"
    actions   = ["iam:PassRole"]
    resources = var.passable_role_arns
  }

  dynamic "statement" {
    for_each = var.web_bucket_arn != "" ? [1] : []
    content {
      sid       = "WebS3Sync"
      actions   = ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetObject"]
      resources = [var.web_bucket_arn, "${var.web_bucket_arn}/*"]
    }
  }

  dynamic "statement" {
    for_each = var.cloudfront_distribution_arn != "" ? [1] : []
    content {
      sid       = "WebCloudFrontInvalidate"
      actions   = ["cloudfront:CreateInvalidation"]
      resources = [var.cloudfront_distribution_arn]
    }
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "${var.name_prefix}-gha-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
