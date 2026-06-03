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
