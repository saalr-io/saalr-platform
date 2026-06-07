# --- ECR ---
resource "aws_ecr_repository" "this" {
  for_each             = toset(var.ecr_repo_names)
  name                 = "${var.name_prefix}/${each.value}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}/${each.value}" })
}

# --- ECS cluster ---
resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-cluster" })
}

# --- CloudWatch logs ---
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.name_prefix}"
  retention_in_days = var.log_retention_days
  tags              = merge(var.tags, { Name = "${var.name_prefix}-ecs-logs" })
}

# --- IAM ---
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: ECR pull + log write (managed) + secret injection at container start.
resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = merge(var.tags, { Name = "${var.name_prefix}-ecs-execution" })
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid       = "InjectSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns
  }
  statement {
    sid       = "DecryptSecrets"
    actions   = ["kms:Decrypt"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${var.name_prefix}-ecs-execution-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# Task role: the app's runtime access to S3 / Secrets Manager / KMS.
resource "aws_iam_role" "task" {
  name               = "${var.name_prefix}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = merge(var.tags, { Name = "${var.name_prefix}-ecs-task" })
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "S3Objects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [for b in var.s3_bucket_names : "arn:aws:s3:::${b}/*"]
  }
  statement {
    sid       = "S3List"
    actions   = ["s3:ListBucket"]
    resources = [for b in var.s3_bucket_names : "arn:aws:s3:::${b}"]
  }
  statement {
    sid       = "Secrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns
  }
  statement {
    sid       = "Kms"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "${var.name_prefix}-ecs-task"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# --- App security group (ingress added by the ALB in 2d-2) ---
resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-ecs-app-sg"
  description = "ECS app tasks; ingress added by the ALB (2d-2)"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-ecs-app-sg" })
}

resource "aws_vpc_security_group_egress_rule" "app" {
  security_group_id = aws_security_group.app.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All egress"
}
