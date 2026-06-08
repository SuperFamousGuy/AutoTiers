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
}

variable "secret_key" {
  description = "Fernet encryption key (base64-urlsafe 32 bytes). Override in production."
  type        = string
  sensitive   = true
  default     = "REPLACE_ME"
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
