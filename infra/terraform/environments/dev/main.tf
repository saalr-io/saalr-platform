terraform {
  backend "s3" {
    bucket         = "saalr-terraform-state" # set to the bootstrap bucket (your unique name)
    key            = "dev/stack.tfstate"
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
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

module "network" {
  source               = "../../modules/network"
  name_prefix          = "saalr-dev"
  vpc_cidr             = var.vpc_cidr
  azs                  = var.azs
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  single_nat_gateway   = var.single_nat_gateway
}

module "data" {
  source                = "../../modules/data"
  name_prefix           = "saalr-dev"
  vpc_id                = module.network.vpc_id
  vpc_cidr              = module.network.vpc_cidr
  private_subnet_ids    = module.network.private_subnet_ids
  enable_app_sg_ingress = true
  app_security_group_id = module.compute.app_security_group_id
}

module "storage" {
  source        = "../../modules/storage"
  name_prefix   = "saalr-dev"
  bucket_prefix = "saalr-dev" # globally-unique — set a unique suffix before apply
}

module "compute" {
  source      = "../../modules/compute"
  name_prefix = "saalr-dev"
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
  name_prefix           = "saalr-dev"
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  app_security_group_id = module.compute.app_security_group_id
  cluster_arn           = module.compute.cluster_arn
  execution_role_arn    = module.compute.task_execution_role_arn
  task_role_arn         = module.compute.task_role_arn
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
