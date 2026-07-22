###############################################################################
# Random values
###############################################################################
resource "random_password" "db" {
  length  = 32
  special = true
  # Only RFC 3986 userinfo-safe specials: unreserved + a subset of sub-delims.
  # Excluded: @ / : # % ? & ^ [ ] { } | < > — all break URI parsing or percent-encoding.
  override_special = "!$*()-_=+,."
}

###############################################################################
# DB password — stored standalone so Aurora can reference it directly
###############################################################################
resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${var.app_name}/${var.environment}/db-password"
  description             = "Aurora master password for ${var.app_name} ${var.environment}"
  recovery_window_in_days = var.secret_recovery_window_in_days

  tags = {
    Name = "${var.app_name}-${var.environment}-db-password"
  }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}

###############################################################################
# DATABASE_URL — full async connection string for SQLAlchemy / asyncpg
###############################################################################
resource "aws_secretsmanager_secret" "database_url" {
  name                    = "${var.app_name}/${var.environment}/database-url"
  description             = "Full asyncpg DATABASE_URL for the ${var.app_name} backend"
  recovery_window_in_days = var.secret_recovery_window_in_days

  tags = {
    Name = "${var.app_name}-${var.environment}-database-url"
  }
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql+asyncpg://${var.db_username}:${random_password.db.result}@${aws_rds_cluster.main.endpoint}:5432/${var.db_name}"
}

###############################################################################
# DATABASE_URL_SYNC — psycopg2 connection string (used by Alembic / sync ops)
###############################################################################
resource "aws_secretsmanager_secret" "database_url_sync" {
  name                    = "${var.app_name}/${var.environment}/database-url-sync"
  description             = "Full psycopg2 DATABASE_URL_SYNC for the ${var.app_name} backend"
  recovery_window_in_days = var.secret_recovery_window_in_days

  tags = {
    Name = "${var.app_name}-${var.environment}-database-url-sync"
  }
}

resource "aws_secretsmanager_secret_version" "database_url_sync" {
  secret_id     = aws_secretsmanager_secret.database_url_sync.id
  secret_string = "postgresql+psycopg2://${var.db_username}:${random_password.db.result}@${aws_rds_cluster.main.endpoint}:5432/${var.db_name}"
}

###############################################################################
# Application secrets — values supplied externally (no default; must be set
# via tfvars, environment variable TF_VAR_*, or Secrets Manager console after
# initial apply).  We store an explicit placeholder so the secret ARN exists
# and the ECS task can reference it; operators MUST replace the placeholder
# value before starting the service.
###############################################################################

# ADMIN_API_KEY
resource "aws_secretsmanager_secret" "admin_api_key" {
  name                    = "${var.app_name}/${var.environment}/admin-api-key"
  description             = "Admin API key for ${var.app_name} ${var.environment}"
  recovery_window_in_days = var.secret_recovery_window_in_days

  tags = {
    Name = "${var.app_name}-${var.environment}-admin-api-key"
  }
}

resource "aws_secretsmanager_secret_version" "admin_api_key" {
  secret_id     = aws_secretsmanager_secret.admin_api_key.id
  secret_string = var.admin_api_key
}
