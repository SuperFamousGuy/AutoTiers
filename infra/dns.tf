###############################################################################
# Application DNS — apex / www / api records for auto-tiers.com
#
# These three ALIAS A records are what make the site resolve. They previously
# lived ONLY in the Route 53 console, unmanaged by Terraform. On 2026-06-14
# delegation was moved to the SES-purpose hosted zone (Z07939072J19KFQLTE2UB),
# which had SES records but none of these — the entire site went dark until
# they were re-added by hand. Codifying them here means a zone recreate (or a
# `terraform apply` against a fresh zone) self-heals instead of taking the
# site down.
#
# Gated on var.manage_dns to match the SES records in ses.tf: when the zone is
# in this account's Route 53, Terraform owns these records; when DNS is
# external, it stays out of the way. They reuse the same hosted-zone lookup
# (data.aws_route53_zone.ses) and reference the CloudFront / ALB resources
# directly so the targets can never drift from the live infrastructure.
#
# The pre-existing live records were adopted into state via `terraform import`
# (2026-06-14); a fresh zone simply has Terraform create them on apply.
###############################################################################

# Apex — auto-tiers.com → CloudFront (frontend SPA).
resource "aws_route53_record" "apex" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.ses[0].zone_id
  name    = var.ses_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

# www.auto-tiers.com → CloudFront (same frontend distribution).
resource "aws_route53_record" "www" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.ses[0].zone_id
  name    = "www.${var.ses_domain}"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

# api.auto-tiers.com → ALB (backend API).
resource "aws_route53_record" "api" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.ses[0].zone_id
  name    = "api.${var.ses_domain}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = false
  }
}
