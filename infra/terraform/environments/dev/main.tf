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
  source             = "../../modules/data"
  name_prefix        = "saalr-dev"
  vpc_id             = module.network.vpc_id
  vpc_cidr           = module.network.vpc_cidr
  private_subnet_ids = module.network.private_subnet_ids
}
