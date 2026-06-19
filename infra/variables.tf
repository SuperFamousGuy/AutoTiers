variable "aws_region" {
  description = "AWS region to deploy all resources into."
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Short application name used as a prefix for resource names."
  type        = string
  default     = "autotiers"
}

variable "environment" {
  description = "Deployment environment (e.g. prod, staging)."
  type        = string
  default     = "prod"
}

variable "backend_image_tag" {
  description = "Docker image tag to deploy for the backend ECS task."
  type        = string
  default     = "latest"
}

variable "run_migrations_on_apply" {
  description = <<-EOT
    When true (default), `terraform apply` runs the one-off Alembic migration
    task (alembic upgrade head) via aws ecs run-task whenever the backend image
    tag or the migration files change, and blocks until it succeeds (see
    infra/migrations.tf). Requires the AWS CLI and live credentials on the
    machine running apply. Set to false for plan-only / `terraform validate`
    environments with no cluster or credentials.
  EOT
  type        = bool
  default     = true
}

variable "db_username" {
  description = "Master username for the Aurora cluster."
  type        = string
  default     = "autotiers"
}

variable "db_name" {
  description = "Initial database name created in the Aurora cluster."
  type        = string
  default     = "autotiers"
}

###############################################################################
# Aurora lifecycle / destroy-safety (issue #181)
#
# Two INDEPENDENT postures; do not conflate them:
#
#   Prod safety (block accidental destroy):
#     deletion_protection = true (and/or the prevent_destroy lifecycle block in
#     rds.tf). While this is on, `terraform destroy` is REJECTED outright, so
#     skip_final_snapshot has no effect.
#
#   Intentional teardown (capture a parting snapshot):
#     deletion_protection = false (to allow the destroy) AND
#     skip_final_snapshot = false with a final_snapshot_identifier, so the
#     destroy takes a final snapshot before dropping the cluster.
#
# Defaults below preserve fast dev teardown/recreate cycles.
###############################################################################
variable "skip_final_snapshot" {
  description = <<-EOT
    Whether to skip the final snapshot when the Aurora cluster is destroyed.
    Defaults to true for dev/teardown cycles. Set to false for production so a
    `terraform destroy` captures a final snapshot (requires
    final_snapshot_identifier to be set).
  EOT
  type        = bool
  default     = true
}

variable "final_snapshot_identifier" {
  description = <<-EOT
    Name of the final snapshot taken on destroy when skip_final_snapshot is
    false. Required (non-null, non-empty) whenever skip_final_snapshot = false;
    ignored when skip_final_snapshot = true.
  EOT
  type        = string
  default     = null

  validation {
    # Validate the AWS snapshot-name shape when an identifier is provided.
    # The "required when skip_final_snapshot = false" coupling is enforced as a
    # resource precondition in rds.tf (a variable validation cannot reference
    # another variable).
    condition = (
      var.final_snapshot_identifier == null ||
      can(regex("^[a-zA-Z][a-zA-Z0-9-]{0,254}$", var.final_snapshot_identifier))
    )
    error_message = "final_snapshot_identifier must start with a letter and contain only letters, numbers, and hyphens (max 255 chars), per AWS RDS snapshot naming rules."
  }
}

variable "deletion_protection" {
  description = <<-EOT
    Whether the Aurora cluster is protected from deletion. Defaults to true.
    Set to false ONLY when intentionally tearing down the environment. This is
    the variable-driven runtime guard; note that Terraform's lifecycle
    { prevent_destroy } block cannot reference a variable, so for the strongest
    plan-time guarantee on a true prod cluster, also uncomment the
    prevent_destroy lifecycle block in rds.tf before go-live.
  EOT
  type        = bool
  default     = true
}

variable "secret_recovery_window_in_days" {
  description = <<-EOT
    Recovery window (in days) before a deleted Secrets Manager secret name can
    be reused. AWS allows 0 (immediate deletion, no recovery) or 7-30. Defaults
    to 7. Set to 0 in dev where fast destroy/recreate cycles need the same
    secret names back immediately (issue #181 notes).
  EOT
  type        = number
  default     = 7

  validation {
    condition = (
      floor(var.secret_recovery_window_in_days) == var.secret_recovery_window_in_days &&
      (var.secret_recovery_window_in_days == 0 || (var.secret_recovery_window_in_days >= 7 && var.secret_recovery_window_in_days <= 30))
    )
    error_message = "secret_recovery_window_in_days must be a whole number: 0 (force-delete) or between 7 and 30, per AWS Secrets Manager limits."
  }
}

variable "backend_base_url" {
  description = <<-EOT
    Base URL of the backend API, used to construct OAuth redirect URIs.
    Defaults to the ALB HTTP URL (resolved at apply time); override with an
    HTTPS URL once an ACM cert and 443 listener are in place (issue #180).
    Example: "https://api.autotiers.com"
  EOT
  type        = string
  default     = ""
  # Empty default means Terraform falls back to the ALB DNS name in ecs.tf.
  # Set this variable when you have a stable custom domain.
}

###############################################################################
# Secret values — must be supplied via tfvars or TF_VAR_* env vars.
# Defaults are empty strings so `terraform validate` succeeds without real creds;
# the backend will fail to start if these are not replaced before deployment.
###############################################################################
variable "jwt_secret" {
  description = "JWT signing secret. Override in production — do not use the default."
  type        = string
  sensitive   = true
  default     = "REPLACE_ME"

  validation {
    condition     = var.jwt_secret != "REPLACE_ME" && length(var.jwt_secret) >= 32
    error_message = "jwt_secret must be set to a real secret (min 32 characters). Do not deploy with the default placeholder."
  }
}

variable "secret_key" {
  description = "Fernet encryption key (base64-urlsafe 32 bytes). Override in production."
  type        = string
  sensitive   = true
  default     = "REPLACE_ME"

  validation {
    # A Fernet key is exactly 32 bytes base64url-encoded -> 44 characters
    # (43 from the base64url alphabet + one '=' pad char). This rejects the
    # REPLACE_ME placeholder (10 chars) and any malformed key that would crash
    # the backend's Fernet() construction at startup rather than at deploy time.
    condition     = can(regex("^[A-Za-z0-9_-]{43}=$", var.secret_key))
    error_message = "secret_key must be a valid Fernet key: 44 chars, base64-urlsafe 32 bytes. Do not deploy with the default placeholder. Generate with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
  }
}

variable "yahoo_client_id" {
  description = "Yahoo OAuth application client ID."
  type        = string
  sensitive   = true
  default     = ""
}

variable "yahoo_client_secret" {
  description = "Yahoo OAuth application client secret."
  type        = string
  sensitive   = true
  default     = ""
}

variable "google_client_id" {
  description = "Google OAuth application client ID."
  type        = string
  sensitive   = true
  default     = ""
}

variable "google_client_secret" {
  description = "Google OAuth application client secret."
  type        = string
  sensitive   = true
  default     = ""
}

variable "admin_api_key" {
  description = "Admin API key for protected admin endpoints. Set empty to leave admin auth disabled (backend treats an empty key as 'no admin auth required'); otherwise supply a real key of at least 32 chars."
  type        = string
  sensitive   = true
  default     = "REPLACE_ME"

  validation {
    # Reject the REPLACE_ME placeholder so a guessable admin key never deploys.
    # An empty string is allowed: the backend (app/auth/admin.py) treats an
    # empty admin_api_key as "admin auth disabled", which is a deliberate
    # operator choice. A non-empty key must be at least 32 chars.
    condition     = var.admin_api_key != "REPLACE_ME" && (var.admin_api_key == "" || length(var.admin_api_key) >= 32)
    error_message = "admin_api_key must not be the default placeholder. Set it to either an empty string (admin auth disabled) or a real key of at least 32 characters."
  }
}

variable "acm_certificate_arn" {
  description = "ARN of the ACM certificate covering auto-tiers.com, www.auto-tiers.com, api.auto-tiers.com. Must be in us-east-1 (required by CloudFront)."
  type        = string
  default     = ""
}

variable "frontend_url" {
  description = "Public URL of the frontend. Defaults to CloudFront domain; override with custom domain once DNS is wired (e.g. https://auto-tiers.com)."
  type        = string
  default     = ""
}

variable "domain_name" {
  description = <<-EOT
    The application's root (apex) domain. Drives both the CloudFront aliases
    (cdn.tf) and the apex/www/api Route 53 records (dns.tf) so the two can
    never disagree. Must match the ACM certificate's covered names and the
    Route 53 hosted zone these records live in (var.ses_route53_zone_name).
  EOT
  type        = string
  default     = "auto-tiers.com"
}

###############################################################################
# SES — transactional auth email (see ses.tf)
###############################################################################
variable "ses_domain" {
  description = "Domain to verify as an SES sender identity (the apex sending domain)."
  type        = string
  default     = "auto-tiers.com"
}

variable "ses_route53_zone_name" {
  description = "Name of the Route 53 hosted zone that owns ses_domain (only used when manage_dns = true). SES verification, DKIM, and MAIL FROM (MX/SPF) records are published here."
  type        = string
  default     = "auto-tiers.com"
}

variable "manage_dns" {
  description = "When true, Terraform publishes SES verification/DKIM/MAIL-FROM records to Route 53 (zone must exist in this account) and waits for verification. When false (default), DNS is external — Terraform still creates the SES identity, DKIM, and MAIL FROM resources but not their DNS records, emitting them via the ses_dns_records_for_manual_entry output for you to add at your DNS provider."
  type        = bool
  default     = false
}

variable "ses_from_email" {
  description = "Bare from-address the app sends as. Must belong to ses_domain; also pinned in the IAM ses:FromAddress condition."
  type        = string
  default     = "noreply@auto-tiers.com"
}

variable "ses_from_display_name" {
  description = "Display name shown in the From header, e.g. 'AutoTiers <noreply@auto-tiers.com>'."
  type        = string
  default     = "AutoTiers"
}

variable "ses_mail_from_subdomain" {
  description = "Subdomain label used for the custom MAIL FROM domain (bounces). Combined with ses_domain, e.g. 'bounce' -> bounce.auto-tiers.com."
  type        = string
  default     = "bounce"
}

variable "enable_ses" {
  description = "When true the backend container runs with EMAIL_SENDER_BACKEND=ses (real sends). Keep false until the domain is verified AND the account is out of the SES sandbox; the app defaults to the in-process fake sender."
  type        = bool
  default     = false
}

variable "ses_ops_email" {
  description = "Optional email address subscribed to SES bounce/complaint notifications. Leave empty to skip; the SNS topic is still created. The subscription requires a manual confirmation click."
  type        = string
  default     = ""
}
