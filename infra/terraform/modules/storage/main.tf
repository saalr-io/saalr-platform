# --- KMS ---
resource "aws_kms_key" "this" {
  description             = "${var.name_prefix} data encryption key"
  enable_key_rotation     = true
  deletion_window_in_days = var.kms_deletion_window_days
  tags                    = merge(var.tags, { Name = "${var.name_prefix}-kms" })
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.this.key_id
}

# --- S3 buckets ---
resource "aws_s3_bucket" "transcripts" {
  bucket = "${var.bucket_prefix}-transcripts"
  tags   = merge(var.tags, { Name = "${var.bucket_prefix}-transcripts" })
}

resource "aws_s3_bucket" "ml_models" {
  bucket = "${var.bucket_prefix}-ml-models"
  tags   = merge(var.tags, { Name = "${var.bucket_prefix}-ml-models" })
}

resource "aws_s3_bucket" "audit" {
  bucket              = "${var.bucket_prefix}-audit"
  object_lock_enabled = true
  tags                = merge(var.tags, { Name = "${var.bucket_prefix}-audit" })
}

locals {
  buckets = {
    transcripts = aws_s3_bucket.transcripts.id
    ml_models   = aws_s3_bucket.ml_models.id
    audit       = aws_s3_bucket.audit.id
  }
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = local.buckets
  bucket   = each.value
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets
  bucket   = each.value
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = local.buckets
  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    default_retention {
      mode = var.audit_object_lock_mode
      days = var.audit_retention_days
    }
  }
  depends_on = [aws_s3_bucket_versioning.this]
}

# --- Secrets Manager (containers only; values set out-of-band) ---
resource "aws_secretsmanager_secret" "this" {
  for_each                = toset(var.secret_names)
  name                    = each.value
  description             = "Managed by Terraform; value set out-of-band (never in state)."
  kms_key_id              = aws_kms_key.this.arn
  recovery_window_in_days = var.secret_recovery_window_days
  tags                    = merge(var.tags, { Name = each.value })
}
