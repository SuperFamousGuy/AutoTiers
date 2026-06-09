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
