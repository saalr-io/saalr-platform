locals {
  use_custom_domain = var.web_domain_name != ""
}

# --- Private S3 bucket for the static site ---
resource "aws_s3_bucket" "web" {
  bucket = "${var.bucket_prefix}-web"
  tags   = merge(var.tags, { Name = "${var.bucket_prefix}-web" })
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- Origin Access Control (CloudFront reads the private bucket via sigv4) ---
resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "${var.name_prefix}-web-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# --- CloudFront Functions ---
resource "aws_cloudfront_function" "rewrite" {
  name    = "${var.name_prefix}-web-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Directory-index + SPA fallback for /app/*."
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;
      if (uri === '/app' || uri.indexOf('/app/') === 0) {
        if (uri.indexOf('.') === -1) { request.uri = '/app/index.html'; }
        return request;
      }
      if (uri.endsWith('/')) { request.uri = uri + 'index.html'; }
      else if (uri.indexOf('.') === -1) { request.uri = uri + '/index.html'; }
      return request;
    }
  EOT
}

resource "aws_cloudfront_function" "api_strip" {
  name    = "${var.name_prefix}-web-api-strip"
  runtime = "cloudfront-js-2.0"
  comment = "Strip the /api prefix before forwarding to the API ALB."
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      request.uri = request.uri.replace(/^\/api/, '');
      if (request.uri === '') { request.uri = '/'; }
      return request;
    }
  EOT
}

# --- AWS-managed cache/origin-request policies ---
data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}
data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}
data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

# --- ACM cert (us-east-1) + Route53 validation, only with a custom domain ---
resource "aws_acm_certificate" "web" {
  count                     = local.use_custom_domain ? 1 : 0
  provider                  = aws.us_east_1
  domain_name               = var.web_domain_name
  subject_alternative_names = var.include_www ? ["www.${var.web_domain_name}"] : []
  validation_method         = "DNS"
  tags                      = merge(var.tags, { Name = "${var.name_prefix}-web-cert" })
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = local.use_custom_domain ? {
    for dvo in aws_acm_certificate.web[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  } : {}
  zone_id = var.route53_zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "web" {
  count                   = local.use_custom_domain ? 1 : 0
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.web[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# --- CloudFront distribution ---
resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = var.price_class
  comment             = "${var.name_prefix} web"
  aliases             = local.use_custom_domain ? (var.include_www ? [var.web_domain_name, "www.${var.web_domain_name}"] : [var.web_domain_name]) : []
  tags                = merge(var.tags, { Name = "${var.name_prefix}-web" })

  origin {
    origin_id                = "s3"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  origin {
    origin_id   = "api"
    domain_name = var.alb_domain_name
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.rewrite.arn
    }
  }

  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.api_strip.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = local.use_custom_domain ? false : true
    acm_certificate_arn            = local.use_custom_domain ? aws_acm_certificate_validation.web[0].certificate_arn : null
    ssl_support_method             = local.use_custom_domain ? "sni-only" : null
    minimum_protocol_version       = local.use_custom_domain ? "TLSv1.2_2021" : null
  }
}

# --- Bucket policy: only this distribution may read ---
data "aws_iam_policy_document" "web_bucket" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.web.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.web.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "web" {
  bucket = aws_s3_bucket.web.id
  policy = data.aws_iam_policy_document.web_bucket.json
}

# --- Route53 records to the distribution ---
# allow_overwrite so the apex/www can take over records that already exist in the
# zone (e.g. a prior Netlify pointer) in-place, without a destroy/create race.
resource "aws_route53_record" "web_alias" {
  count           = local.use_custom_domain ? 1 : 0
  zone_id         = var.route53_zone_id
  name            = var.web_domain_name
  type            = "A"
  allow_overwrite = true
  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

# www as a CNAME to the distribution (same record type as a typical existing www
# pointer, so allow_overwrite UPSERTs it cleanly).
resource "aws_route53_record" "www_alias" {
  count           = local.use_custom_domain && var.include_www ? 1 : 0
  zone_id         = var.route53_zone_id
  name            = "www.${var.web_domain_name}"
  type            = "CNAME"
  ttl             = 300
  records         = [aws_cloudfront_distribution.web.domain_name]
  allow_overwrite = true
}
