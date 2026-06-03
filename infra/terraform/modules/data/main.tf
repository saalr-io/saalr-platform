locals {
  ingress_cidrs = length(var.ingress_cidr_blocks) > 0 ? var.ingress_cidr_blocks : [var.vpc_cidr]
}

# --- Postgres (RDS) ---
resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db"
  subnet_ids = var.private_subnet_ids
  tags       = merge(var.tags, { Name = "${var.name_prefix}-db-subnets" })
}

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds-sg"
  description = "Postgres access from within the VPC"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-rds-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "rds" {
  count             = length(local.ingress_cidrs)
  security_group_id = aws_security_group.rds.id
  cidr_ipv4         = local.ingress_cidrs[count.index]
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
  description       = "Postgres from VPC"
}

resource "aws_vpc_security_group_egress_rule" "rds" {
  security_group_id = aws_security_group.rds.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All egress"
}

resource "aws_db_instance" "this" {
  identifier                  = "${var.name_prefix}-pg"
  engine                      = "postgres"
  engine_version              = var.db_engine_version
  instance_class              = var.db_instance_class
  allocated_storage           = var.db_allocated_storage
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = var.db_name
  username                    = var.db_username
  manage_master_user_password = true
  multi_az                    = var.db_multi_az
  db_subnet_group_name        = aws_db_subnet_group.this.name
  vpc_security_group_ids      = [aws_security_group.rds.id]
  backup_retention_period     = var.db_backup_retention_days
  deletion_protection         = var.db_deletion_protection
  skip_final_snapshot         = var.db_skip_final_snapshot
  final_snapshot_identifier   = var.db_skip_final_snapshot ? null : "${var.name_prefix}-pg-final"
  apply_immediately           = true
  tags                        = merge(var.tags, { Name = "${var.name_prefix}-pg" })
}

# --- Redis (ElastiCache) ---
resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis"
  subnet_ids = var.private_subnet_ids
  tags       = merge(var.tags, { Name = "${var.name_prefix}-redis-subnets" })
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "Redis access from within the VPC"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-redis-sg" })
}

resource "aws_vpc_security_group_ingress_rule" "redis" {
  count             = length(local.ingress_cidrs)
  security_group_id = aws_security_group.redis.id
  cidr_ipv4         = local.ingress_cidrs[count.index]
  from_port         = 6379
  to_port           = 6379
  ip_protocol       = "tcp"
  description       = "Redis from VPC"
}

resource "aws_vpc_security_group_egress_rule" "redis" {
  security_group_id = aws_security_group.redis.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All egress"
}

resource "aws_elasticache_cluster" "this" {
  cluster_id         = "${var.name_prefix}-redis"
  engine             = "redis"
  engine_version     = var.redis_engine_version
  node_type          = var.redis_node_type
  num_cache_nodes    = 1
  port               = 6379
  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]
  tags               = merge(var.tags, { Name = "${var.name_prefix}-redis" })
}
