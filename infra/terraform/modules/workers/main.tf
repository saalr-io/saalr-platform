locals {
  container_env     = [for k, v in var.environment : { name = k, value = v }]
  container_secrets = [for k, v in var.secrets : { name = k, valueFrom = v }]
}

# Allow the execution role to inject the RDS-managed DB password secret at container start.
# (Self-contained per module to avoid relying on another module's grant.)
data "aws_iam_policy_document" "exec_db_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }
}

resource "aws_iam_role_policy" "exec_db_secret" {
  name   = "${var.name_prefix}-workers-exec-db-secret"
  role   = var.execution_role_name
  policy = data.aws_iam_policy_document.exec_db_secret.json
}

# --- Task definitions (scheduled + service) ---
resource "aws_ecs_task_definition" "scheduled" {
  for_each                 = var.scheduled_workers
  family                   = "${var.name_prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  dynamic "ephemeral_storage" {
    for_each = var.ephemeral_storage_gib > 0 ? [1] : []
    content {
      size_in_gib = var.ephemeral_storage_gib
    }
  }

  container_definitions = jsonencode([
    {
      name        = each.key
      image       = each.value.image
      essential   = true
      command     = each.value.command
      environment = local.container_env
      secrets     = local.container_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = var.log_group_name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = each.key
        }
      }
    }
  ])

  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}" })
}

resource "aws_ecs_task_definition" "service" {
  for_each                 = var.service_workers
  family                   = "${var.name_prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  dynamic "ephemeral_storage" {
    for_each = var.ephemeral_storage_gib > 0 ? [1] : []
    content {
      size_in_gib = var.ephemeral_storage_gib
    }
  }

  container_definitions = jsonencode([
    {
      name        = each.key
      image       = each.value.image
      essential   = true
      command     = each.value.command
      environment = local.container_env
      secrets     = local.container_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = var.log_group_name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = each.key
        }
      }
    }
  ])

  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}" })
}

# --- EventBridge invoke role (events.amazonaws.com runs the scheduled tasks) ---
data "aws_iam_policy_document" "events_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "events" {
  name               = "${var.name_prefix}-events-invoke"
  assume_role_policy = data.aws_iam_policy_document.events_assume.json
  tags               = merge(var.tags, { Name = "${var.name_prefix}-events-invoke" })
}

data "aws_iam_policy_document" "events" {
  statement {
    sid       = "RunTask"
    actions   = ["ecs:RunTask"]
    resources = [for k, t in aws_ecs_task_definition.scheduled : t.arn]
  }
  statement {
    sid       = "PassRole"
    actions   = ["iam:PassRole"]
    resources = [var.execution_role_arn, var.task_role_arn]
  }
}

resource "aws_iam_role_policy" "events" {
  name   = "${var.name_prefix}-events-invoke"
  role   = aws_iam_role.events.id
  policy = data.aws_iam_policy_document.events.json
}

# --- Scheduled rules + targets ---
resource "aws_cloudwatch_event_rule" "scheduled" {
  for_each            = var.scheduled_workers
  name                = "${var.name_prefix}-${each.key}"
  schedule_expression = each.value.schedule_expression
  tags                = merge(var.tags, { Name = "${var.name_prefix}-${each.key}" })
}

resource "aws_cloudwatch_event_target" "scheduled" {
  for_each = var.scheduled_workers
  rule     = aws_cloudwatch_event_rule.scheduled[each.key].name
  arn      = var.cluster_arn
  role_arn = aws_iam_role.events.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.scheduled[each.key].arn
    task_count          = 1
    launch_type         = "FARGATE"

    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [var.app_security_group_id]
      assign_public_ip = false
    }
  }
}

# --- Long-running consumer services (no ALB) ---
resource "aws_ecs_service" "service" {
  for_each        = var.service_workers
  name            = "${var.name_prefix}-${each.key}"
  cluster         = var.cluster_arn
  task_definition = aws_ecs_task_definition.service[each.key].arn
  desired_count   = each.value.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-${each.key}" })
}
