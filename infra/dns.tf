###############################################################################
# Application DNS — apex / www / api records for the app's root domain
#
# These ALIAS records are what make the site resolve. They previously lived
# ONLY in the Route 53 console, unmanaged by Terraform. On 2026-06-14
# delegation was moved to a Terraform-managed hosted zone (Z07939072J19KFQLTE2UB)
# that (at the time) also carried SES records — that zone had none of these
# apex/www/api records, and the entire site went dark until they were re-added
# by hand. Codifying them here means a zone recreate (or a `terraform apply`
# against a fresh zone) self-heals instead of taking the site down.
# (The SES records that used to live in this same zone were removed once
# accounts/email were torn down; this data source is app-DNS-only now.)
#
# Gated on var.manage_dns: when the zone is in this account's Route 53,
# Terraform owns these records; when DNS is external, it stays out of the way.
# They reference the CloudFront / ALB resources directly so the targets can
# never drift from the live infrastructure.
#
# Record names use var.domain_name — the same variable that drives the
# CloudFront aliases in cdn.tf — so the alias set and these records can never
# disagree about what the app's apex is.
#
# The pre-existing live A records were adopted into state via `terraform import`
# (2026-06-14); a fresh zone simply has Terraform create them on apply. The
# AAAA records are new (the zone had none), giving IPv6 clients a path to the
# CloudFront-fronted apex/www, which is IPv6-enabled (see cdn.tf). The ALB is
# IPv4-only (ip_address_type = "ipv4"), so api gets no AAAA record.
###############################################################################

# Hosted-zone lookup only when Terraform manages DNS (Route 53, this account).
data "aws_route53_zone" "app" {
  count        = var.manage_dns ? 1 : 0
  name         = "${var.route53_zone_name}."
  private_zone = false
}

# --- Apex (auto-tiers.com) → CloudFront (frontend SPA) -----------------------
resource "aws_route53_record" "apex" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.app[0].zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "apex_v6" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.app[0].zone_id
  name    = var.domain_name
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

# --- www → CloudFront (same frontend distribution) ---------------------------
resource "aws_route53_record" "www" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.app[0].zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "www_v6" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.app[0].zone_id
  name    = "www.${var.domain_name}"
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

# --- api → ALB (backend API) -------------------------------------------------
# IPv4 only: the ALB is provisioned with ip_address_type = "ipv4", so no AAAA.
resource "aws_route53_record" "api" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.app[0].zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = false
  }
}
