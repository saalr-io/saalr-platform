# ---------------------------------------------------------------------------
# One-off Alembic migration task. Reuses the api image (which now bundles
# alembic + psycopg2) and the compute roles/log group. env.py composes the
# admin DB URL from the injected DB_* (password URL-encoded) and runs against
# RDS via psycopg2. Invoked by the "migrate" job in deploy.yml after images
# are pushed; can also be run ad hoc with `aws ecs run-task`.
# ---------------------------------------------------------------------------
resource "aws_ecs_task_definition" "migrate" {
  family                   = "saalr-prod-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = module.compute.task_execution_role_arn
  task_role_arn            = module.compute.task_role_arn

  # The api image bundles CUDA torch; extraction needs more than the 20 GiB default.
  ephemeral_storage {
    size_in_gib = 80
  }

  container_definitions = jsonencode([
    {
      name       = "migrate"
      image      = "${module.compute.ecr_repository_urls["api"]}:latest"
      essential  = true
      entryPoint = ["sh", "-c"]
      command    = ["uv run --no-sync alembic -c alembic.ini upgrade head"]
      environment = [
        { name = "DB_HOST", value = module.data.db_endpoint },
        { name = "DB_PORT", value = tostring(module.data.db_port) },
        { name = "DB_NAME", value = module.data.db_name },
        { name = "DB_USER", value = "saalr_admin" },
      ]
      secrets = [
        { name = "DB_PASSWORD", valueFrom = "${module.data.db_master_user_secret_arn}:password::" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = module.compute.log_group_name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "migrate"
        }
      }
    }
  ])
}

output "migrate_task_family" {
  value = aws_ecs_task_definition.migrate.family
}
