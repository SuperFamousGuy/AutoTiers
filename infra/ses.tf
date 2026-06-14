###############################################################################
# AWS SES — transactional auth email (password reset + email verification)
#
# Provisions a verified apex-domain identity with Easy DKIM, a custom MAIL FROM
# subdomain (for SPF/DMARC-aligned bounces), and bounce/complaint notifications.
# DNS records are published to Route 53 automatically, so the identity self-
# verifies during `terraform apply`.
#
# The application sends via the ECS task role (see the SES policy in iam.tf)
# using the SES v1 SendEmail API (backend/app/email/ses_sender.py). The
# from-address and region reach the container as plain env vars (see ecs.tf).
#
# NOTE: a fresh SES account starts in the *sandbox* (can only send to verified
# recipients). Exiting the sandbox is a manual AWS support request — Terraform
# cannot perform it. See docs/runbooks/ses-email-provisioning.md.
###############################################################################

# The hosted zone for the sender domain. Confirmed to live in Route 53 in this
# same account, so Terraform can publish the verification + DKIM records itself.
data "aws_route53_zone" "ses" {
  name         = "${var.ses_route53_zone_name}."
  private_zone = false
}

locals {
  # Display form used as the SMTP From header, e.g. "AutoTiers <noreply@auto-tiers.com>".
  # The bare address (var.ses_from_email) is what the IAM ses:FromAddress
  # condition matches against — SES extracts it from this display form.
  ses_from_address     = "${var.ses_from_display_name} <${var.ses_from_email}>"
  ses_mail_from_domain = "${var.ses_mail_from_subdomain}.${var.ses_domain}"
}

# --- Domain identity + Easy DKIM ---------------------------------------------
resource "aws_ses_domain_identity" "main" {
  domain = var.ses_domain
}

resource "aws_ses_domain_dkim" "main" {
  domain = aws_ses_domain_identity.main.domain
}

# TXT record proving domain ownership to SES.
resource "aws_route53_record" "ses_verification" {
  zone_id = data.aws_route53_zone.ses.zone_id
  name    = "_amazonses.${var.ses_domain}"
  type    = "TXT"
  ttl     = 600
  records = [aws_ses_domain_identity.main.verification_token]
}

# Three CNAMEs enabling Easy DKIM signing of outbound mail.
resource "aws_route53_record" "ses_dkim" {
  count   = 3
  zone_id = data.aws_route53_zone.ses.zone_id
  name    = "${aws_ses_domain_dkim.main.dkim_tokens[count.index]}._domainkey.${var.ses_domain}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_ses_domain_dkim.main.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

# Blocks apply until SES confirms verification (the records above let it pass).
resource "aws_ses_domain_identity_verification" "main" {
  domain     = aws_ses_domain_identity.main.id
  depends_on = [aws_route53_record.ses_verification]
}

# --- Custom MAIL FROM (SPF/DMARC alignment for bounces) ----------------------
resource "aws_ses_domain_mail_from" "main" {
  domain           = aws_ses_domain_identity.main.domain
  mail_from_domain = local.ses_mail_from_domain
}

# MX routing bounces back to SES's regional feedback endpoint.
resource "aws_route53_record" "ses_mail_from_mx" {
  zone_id = data.aws_route53_zone.ses.zone_id
  name    = aws_ses_domain_mail_from.main.mail_from_domain
  type    = "MX"
  ttl     = 600
  records = ["10 feedback-smtp.${var.aws_region}.amazonses.com"]
}

# SPF authorizing SES to send for the MAIL FROM domain.
resource "aws_route53_record" "ses_mail_from_spf" {
  zone_id = data.aws_route53_zone.ses.zone_id
  name    = aws_ses_domain_mail_from.main.mail_from_domain
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com ~all"]
}

# --- Bounce / complaint notifications ----------------------------------------
# Surfaces hard bounces and complaints for monitoring/suppression. An email
# subscription is created only when var.ses_ops_email is set (it requires a
# manual confirmation click on the address).
resource "aws_sns_topic" "ses_notifications" {
  name = "${var.app_name}-${var.environment}-ses-notifications"

  tags = {
    Name = "${var.app_name}-${var.environment}-ses-notifications"
  }
}

resource "aws_ses_identity_notification_topic" "bounce" {
  identity                 = aws_ses_domain_identity.main.arn
  notification_type        = "Bounce"
  topic_arn                = aws_sns_topic.ses_notifications.arn
  include_original_headers = true
}

resource "aws_ses_identity_notification_topic" "complaint" {
  identity                 = aws_ses_domain_identity.main.arn
  notification_type        = "Complaint"
  topic_arn                = aws_sns_topic.ses_notifications.arn
  include_original_headers = true
}

resource "aws_sns_topic_subscription" "ses_ops_email" {
  count     = var.ses_ops_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.ses_notifications.arn
  protocol  = "email"
  endpoint  = var.ses_ops_email
}
