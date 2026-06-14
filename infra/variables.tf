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
    condition     = var.secret_key != "REPLACE_ME" && length(var.secret_key) >= 32
    error_message = "secret_key must be a real Fernet key (base64-urlsafe, min 32 chars). Generate with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
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
  description = "Admin API key for protected admin endpoints."
  type        = string
  sensitive   = true
  default     = "REPLACE_ME"
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

###############################################################################
# SES — transactional auth email (see ses.tf)
###############################################################################
variable "ses_domain" {
  description = "Domain to verify as an SES sender identity (the apex sending domain)."
  type        = string
  default     = "auto-tiers.com"
}

variable "ses_route53_zone_name" {
  description = "Name of the Route 53 hosted zone that owns ses_domain. SES verification + DKIM records are published here."
  type        = string
  default     = "auto-tiers.com"
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
