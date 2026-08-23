###############################################################################
# S3 Bucket — private bucket for the compiled React/Vite frontend
###############################################################################
resource "random_string" "bucket_suffix" {
  length  = 8
  upper   = false
  special = false
}

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.app_name}-${var.environment}-frontend-${random_string.bucket_suffix.result}"

  tags = {
    Name = "${var.app_name}-${var.environment}-frontend"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

###############################################################################
# Origin Access Control (OAC) — replaces legacy OAI for S3 origins
###############################################################################
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.app_name}-${var.environment}-oac"
  description                       = "OAC for ${var.app_name} ${var.environment} frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

###############################################################################
# S3 Bucket Policy — allow CloudFront (via OAC) to GetObject
###############################################################################
data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAC"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
          }
        }
      }
    ]
  })
}

###############################################################################
# CloudFront Function (viewer-request) — SPA route allowlist
#
# CloudFront + a private S3 origin returns 403/404 for any object that is not in
# the bucket. The old config mapped BOTH of those to `200 /index.html` for every
# path, so `https://auto-tiers.com/anything-at-all` served the app shell with a
# 200 — a soft 404 across the whole URL space that Google penalizes as thin
# content (issue #1251).
#
# We still want client-side (SPA) routes to serve index.html once React routing
# is added, but a genuinely unknown path must return a real 404. A file-extension
# heuristic cannot tell them apart (an unknown `/foo` and a future route `/draft`
# are both extension-less), so we distinguish with an EXPLICIT allowlist: only a
# URI listed here is rewritten to /index.html; everything else falls through to
# S3 and, if absent, returns a real 404 (see custom_error_response below).
#
# To add a client-side route, add its exact path to `spaRoutes` here.
###############################################################################
resource "aws_cloudfront_function" "spa_router" {
  name    = "${var.app_name}-${var.environment}-spa-router"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrite allowlisted SPA routes to /index.html; everything else 404s (issue #1251)"
  publish = true

  code = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

      // Explicit allowlist of client-side (SPA) routes that must serve the app
      // shell (index.html). A path that is NOT listed here is left untouched, so
      // it falls through to S3 and a genuinely unknown path returns a real 404
      // instead of a soft 404 (issue #1251). Add a route's exact path here when
      // React client-side routing introduces it.
      var spaRoutes = {
        "/": true
      };

      if (spaRoutes[uri] === true) {
        request.uri = "/index.html";
      }

      return request;
    }
  EOT
}

###############################################################################
# CloudFront Distribution
###############################################################################
resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = "${var.app_name} ${var.environment} frontend"
  price_class         = "PriceClass_100" # US, Canada, Europe — cheapest

  aliases = var.acm_certificate_arn != "" ? [var.domain_name, "www.${var.domain_name}"] : []

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.frontend.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-${aws_s3_bucket.frontend.id}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # Rewrite allowlisted client-side routes to /index.html; leave every other
    # path alone so unknown URLs surface as real 404s (issue #1251).
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_router.arn
    }

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  # Real 404s for unknown paths (issue #1251). A private S3 origin behind OAC
  # returns 403 (AccessDenied) for a missing object — it lacks s3:ListBucket, so
  # it cannot reveal whether the key exists — and 404 when the key is genuinely
  # absent. For a static site both mean "not found", so map each to a real 404
  # served from /404.html rather than a soft 200. Allowlisted SPA routes never
  # reach this path: the viewer-request function above rewrote them to
  # /index.html, which exists and returns 200.
  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.acm_certificate_arn == ""
    acm_certificate_arn            = var.acm_certificate_arn != "" ? var.acm_certificate_arn : null
    ssl_support_method             = var.acm_certificate_arn != "" ? "sni-only" : null
    minimum_protocol_version       = var.acm_certificate_arn != "" ? "TLSv1.2_2021" : null
  }

  tags = {
    Name = "${var.app_name}-${var.environment}-cloudfront"
  }
}
