###############################################################################
# AWS SES — transactional auth email (password reset + email verification)
#
# Provisions a verified apex-domain identity with Easy DKIM, a custom MAIL FROM
# subdomain (for SPF/DMARC-aligned bounces), and bounce/complaint notifications.
#
# DNS modes (var.manage_dns):
#   true  — the sender domain's zone lives in Route 53 in THIS account, so
#           Terraform publishes the verification + DKIM + MAIL FROM records and
#           the identity self-verifies during apply.
#   false — DNS is managed externally (registrar/Cloudflare/another account).
#           Terraform creates the identity but cannot publish records; add the
#           ones emitted by the `ses_dns_records_for_manual_entry` output to your
#           DNS provider, then SES verifies asynchronously. (Default — the
#           auto-tiers.com zone is NOT in this account's Route 53.)
#
# The application sends via the ECS task role (see the SES policy in iam.tf)
# using the SES v1 SendEmail API (backend/app/email/ses_sender.py). The
# from-address and region reach the container as plain env vars (see ecs.tf).
#
# NOTE: a fresh SES account starts in the *sandbox* (can only send to verified
# recipients). Exiting the sandbox is a manual AWS support request — Terraform
# cannot perform it. See docs/runbooks/ses-email-provisioning.md.
###############################################################################

# Hosted-zone lookup only when Terraform manages DNS (Route 53, this account).
data "aws_route53_zone" "ses" {
  count        = var.manage_dns ? 1 : 0
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

# --- Domain identity + Easy DKIM (always created) ----------------------------
resource "aws_ses_domain_identity" "main" {
  domain = var.ses_domain
}

resource "aws_ses_domain_dkim" "main" {
  domain = aws_ses_domain_identity.main.domain
}

# --- Custom MAIL FROM (SPF/DMARC alignment for bounces; always created) ------
resource "aws_ses_domain_mail_from" "main" {
  domain           = aws_ses_domain_identity.main.domain
  mail_from_domain = local.ses_mail_from_domain
}

# --- DNS records: published by Terraform only when manage_dns = true ---------
# When manage_dns = false, the equivalent records are emitted by the
# `ses_dns_records_for_manual_entry` output for manual entry at your DNS host.

# TXT record proving domain ownership to SES.
resource "aws_route53_record" "ses_verification" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.ses[0].zone_id
  name    = "_amazonses.${var.ses_domain}"
  type    = "TXT"
  ttl     = 600
  records = [aws_ses_domain_identity.main.verification_token]
}

# Three CNAMEs enabling Easy DKIM signing of outbound mail.
resource "aws_route53_record" "ses_dkim" {
  count   = var.manage_dns ? 3 : 0
  zone_id = data.aws_route53_zone.ses[0].zone_id
  name    = "${aws_ses_domain_dkim.main.dkim_tokens[count.index]}._domainkey.${var.ses_domain}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_ses_domain_dkim.main.dkim_tokens[count.index]}.dkim.amazonses.com"]
}

# MX routing bounces back to SES's regional feedback endpoint.
resource "aws_route53_record" "ses_mail_from_mx" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.ses[0].zone_id
  name    = aws_ses_domain_mail_from.main.mail_from_domain
  type    = "MX"
  ttl     = 600
  records = ["10 feedback-smtp.${var.aws_region}.amazonses.com"]
}

# SPF authorizing SES to send for the MAIL FROM domain.
resource "aws_route53_record" "ses_mail_from_spf" {
  count   = var.manage_dns ? 1 : 0
  zone_id = data.aws_route53_zone.ses[0].zone_id
  name    = aws_ses_domain_mail_from.main.mail_from_domain
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com ~all"]
}

# Block apply until SES confirms verification — only meaningful when Terraform
# published the records above. With external DNS, verification is async after
# you add the records manually, so this wait is skipped.
resource "aws_ses_domain_identity_verification" "main" {
  count      = var.manage_dns ? 1 : 0
  domain     = aws_ses_domain_identity.main.id
  depends_on = [aws_route53_record.ses_verification]
}

# --- Bounce / complaint notifications (always created) -----------------------
# Surfaces hard bounces and complaints for monitoring/suppression. An email
# subscription is created only when var.ses_ops_email is set (it requires a
# manual confirmation click on the address).
resource "aws_sns_topic" "ses_notifications" {
  name = "${var.app_name}-${var.environment}-ses-notifications"

  tags = {
    Name = "${var.app_name}-${var.environment}-ses-notifications"
  }
}

# SES publishes bounce/complaint events as the ses.amazonaws.com service
# principal; without this the topic rejects those deliveries. Scoped to this
# account + our own identity so no other source can publish.
data "aws_iam_policy_document" "ses_notifications" {
  statement {
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.ses_notifications.arn]

    principals {
      type        = "Service"
      identifiers = ["ses.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_ses_domain_identity.main.arn]
    }
  }
}

resource "aws_sns_topic_policy" "ses_notifications" {
  arn    = aws_sns_topic.ses_notifications.arn
  policy = data.aws_iam_policy_document.ses_notifications.json
}

resource "aws_ses_identity_notification_topic" "bounce" {
  identity                 = aws_ses_domain_identity.main.domain
  notification_type        = "Bounce"
  topic_arn                = aws_sns_topic.ses_notifications.arn
  include_original_headers = true
}

resource "aws_ses_identity_notification_topic" "complaint" {
  identity                 = aws_ses_domain_identity.main.domain
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
