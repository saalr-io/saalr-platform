terraform {
  # Backend blocks cannot use variables. Override the bucket/table at init time with the
  # bootstrap outputs (your globally-unique names), e.g.:
  #   terraform init -backend-config="bucket=<state_bucket>" -backend-config="dynamodb_table=<lock_table>"
  # The literals below are defaults/placeholders.
  backend "s3" {
    bucket         = "saalr-terraform-state"
    key            = "prod/stack.tfstate"
    region         = "us-east-1"
    dynamodb_table = "saalr-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "saalr"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

# CloudFront ACM certs must live in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = {
      Project     = "saalr"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

# ---------------------------------------------------------------------------
# Route 53 hosted zone for the custom domain.
# Prod creates and owns its zone; delegate NS records at the registrar.
# ---------------------------------------------------------------------------
resource "aws_route53_zone" "primary" {
  count = var.web_domain_name != "" ? 1 : 0
  name  = var.web_domain_name
}

module "network" {
  source               = "../../modules/network"
  name_prefix          = "saalr-prod"
  vpc_cidr             = var.vpc_cidr
  azs                  = var.azs
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway   = var.single_nat_gateway
}

module "data" {
  source                 = "../../modules/data"
  name_prefix            = "saalr-prod"
  vpc_id                 = module.network.vpc_id
  vpc_cidr               = module.network.vpc_cidr
  private_subnet_ids     = module.network.private_subnet_ids
  enable_app_sg_ingress  = true
  app_security_group_id  = module.compute.app_security_group_id
  db_multi_az            = var.db_multi_az
  db_deletion_protection = var.db_deletion_protection
  db_skip_final_snapshot = var.db_skip_final_snapshot
  db_instance_class      = var.db_instance_class
}

module "storage" {
  source                 = "../../modules/storage"
  name_prefix            = "saalr-prod"
  bucket_prefix          = var.bucket_prefix
  audit_object_lock_mode = var.audit_object_lock_mode
}

module "compute" {
  source      = "../../modules/compute"
  name_prefix = "saalr-prod"
  vpc_id      = module.network.vpc_id
  s3_bucket_names = [
    module.storage.transcripts_bucket,
    module.storage.ml_models_bucket,
    module.storage.audit_bucket,
  ]
  secret_arns = values(module.storage.secret_arns)
  kms_key_arn = module.storage.kms_key_arn
}

module "api_service" {
  source                = "../../modules/api_service"
  name_prefix           = "saalr-prod"
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  app_security_group_id = module.compute.app_security_group_id
  cluster_arn           = module.compute.cluster_arn
  execution_role_arn    = module.compute.task_execution_role_arn
  execution_role_name   = module.compute.task_execution_role_name
  task_role_arn         = module.compute.task_role_arn
  db_secret_arn         = module.data.db_master_user_secret_arn
  log_group_name        = module.compute.log_group_name
  aws_region            = var.region
  image                 = "${module.compute.ecr_repository_urls["api"]}:latest"

  environment = {
    AWS_REGION           = var.region
    REDIS_URL            = "redis://${module.data.redis_endpoint}:6379/0"
    TRANSCRIPT_S3_BUCKET = module.storage.transcripts_bucket
    DB_HOST              = module.data.db_endpoint
    DB_PORT              = tostring(module.data.db_port)
    DB_NAME              = module.data.db_name
    DB_USER              = "saalr_admin"
  }

  # DB_PASSWORD pulls the `password` key from the RDS-managed secret JSON. The app builds
  # APP_DATABASE_URL from DB_HOST/PORT/USER/NAME/PASSWORD at startup (app-config follow-up).
  secrets = {
    OPENAI_API_KEY    = module.storage.secret_arns["saalr/app/openai"]
    ANTHROPIC_API_KEY = module.storage.secret_arns["saalr/app/anthropic"]
    MASSIVE_API_KEY   = module.storage.secret_arns["saalr/app/massive"]
    FRED_API_KEY      = module.storage.secret_arns["saalr/app/fred"]
    DB_PASSWORD       = "${module.data.db_master_user_secret_arn}:password::"
  }
}

module "workers" {
  source                = "../../modules/workers"
  name_prefix           = "saalr-prod"
  private_subnet_ids    = module.network.private_subnet_ids
  app_security_group_id = module.compute.app_security_group_id
  cluster_arn           = module.compute.cluster_arn
  execution_role_arn    = module.compute.task_execution_role_arn
  execution_role_name   = module.compute.task_execution_role_name
  task_role_arn         = module.compute.task_role_arn
  db_secret_arn         = module.data.db_master_user_secret_arn
  log_group_name        = module.compute.log_group_name
  aws_region            = var.region

  environment = {
    AWS_REGION           = var.region
    REDIS_URL            = "redis://${module.data.redis_endpoint}:6379/0"
    TRANSCRIPT_S3_BUCKET = module.storage.transcripts_bucket
    DB_HOST              = module.data.db_endpoint
    DB_PORT              = tostring(module.data.db_port)
    DB_NAME              = module.data.db_name
    DB_USER              = "saalr_admin"
  }

  secrets = {
    OPENAI_API_KEY    = module.storage.secret_arns["saalr/app/openai"]
    ANTHROPIC_API_KEY = module.storage.secret_arns["saalr/app/anthropic"]
    MASSIVE_API_KEY   = module.storage.secret_arns["saalr/app/massive"]
    FRED_API_KEY      = module.storage.secret_arns["saalr/app/fred"]
    DB_PASSWORD       = "${module.data.db_master_user_secret_arn}:password::"
  }

  # Scheduled (EventBridge -> ecs RunTask): ingest daily, oms-reconcile 5-min, sentiment daily.
  scheduled_workers = {
    "ingest-worker" = {
      image               = "${module.compute.ecr_repository_urls["ingest-worker"]}:latest"
      command             = ["run"]
      schedule_expression = "cron(30 21 * * ? *)"
    }
    "oms-reconcile" = {
      image               = "${module.compute.ecr_repository_urls["oms-worker"]}:latest"
      command             = ["reconcile", "--once"]
      schedule_expression = "rate(5 minutes)"
    }
    "sentiment" = {
      image               = "${module.compute.ecr_repository_urls["ml-worker"]}:latest"
      command             = ["sentiment"]
      schedule_expression = "cron(0 22 * * ? *)"
    }
  }

  # Long-running queue consumers (Fargate services, no ALB).
  service_workers = {
    "backtest-worker" = {
      image         = "${module.compute.ecr_repository_urls["backtest-worker"]}:latest"
      command       = ["consume"]
      desired_count = 1
    }
    "research-agent" = {
      image         = "${module.compute.ecr_repository_urls["research-agent"]}:latest"
      command       = ["consume"]
      desired_count = 1
    }
  }
}

module "web" {
  source          = "../../modules/web"
  name_prefix     = "saalr-prod"
  bucket_prefix   = var.bucket_prefix
  alb_domain_name = module.api_service.alb_dns_name
  web_domain_name = var.web_domain_name
  route53_zone_id = var.web_domain_name != "" ? aws_route53_zone.primary[0].zone_id : ""
  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }
}

module "cicd" {
  source      = "../../modules/cicd"
  name_prefix = "saalr-prod"

  # The GitHub OIDC provider is account-global; the dev env already creates it.
  # Prod reuses it (a data lookup in the module) instead of re-creating it, which
  # would fail with EntityAlreadyExists.
  create_oidc_provider = false

  # Match the actual repo (remote is github.com/saalr-io/saalr-platform); the module
  # default owner is "spayyavula", which would make the prod deploy role reject the
  # real repo's OIDC token at deploy time.
  github_owner = "saalr-io"
  github_repo  = "saalr-platform"

  ecr_repository_arns         = values(module.compute.ecr_repository_arns)
  passable_role_arns          = [module.compute.task_execution_role_arn, module.compute.task_role_arn]
  web_bucket_arn              = module.web.bucket_arn
  cloudfront_distribution_arn = module.web.distribution_arn
}
