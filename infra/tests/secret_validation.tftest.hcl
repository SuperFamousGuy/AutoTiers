# Validates the secret-variable validation blocks in variables.tf (issue #183).
#
# Goal: a `terraform plan` must FAIL fast when jwt_secret / secret_key /
# admin_api_key are left at their REPLACE_ME placeholder (or are otherwise
# malformed), and must PASS when supplied with real values — so an insecure
# default can never be applied to a deployment.
#
# Run with:  cd infra && terraform test
# Requires Terraform >= 1.7 (uses mock_provider so no AWS credentials are
# needed). Not yet wired into CI — see the follow-up issue referenced in the PR.

mock_provider "aws" {}
mock_provider "random" {}

# vpc.tf indexes the AZ name list ([0], [1]); the mocked provider returns an
# empty list, so supply concrete names for the plan to succeed.
override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d"]
  }
}

# IAM policy-document data sources render to a .json string consumed by
# aws_iam_role / aws_iam_role_policy resources, which validate it is real JSON.
# The mocked provider returns a random string, so supply valid (minimal) JSON.
override_data {
  target = data.aws_iam_policy_document.ecs_task_assume_role
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = data.aws_iam_policy_document.secrets_read
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = data.aws_iam_policy_document.ses_send
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

override_data {
  target = data.aws_iam_policy_document.ses_notifications
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

# A real Fernet key: 32 bytes base64url-encoded -> 44 chars ending in '='.
variables {
  jwt_secret    = "a-sufficiently-long-jwt-signing-secret-value"
  secret_key    = "dKkY-w0jHF6kBE_oTzx7JtAYxHB1yyaJYBNz3X1eYdY="
  admin_api_key = "a-sufficiently-long-admin-api-key-value-123"

  # Keep apply-time-only behaviour out of the plan-based test runs.
  run_migrations_on_apply = false
}

# --- Positive path: real secrets validate cleanly ---------------------------
run "valid_secrets_pass_validation" {
  command = plan
}

run "empty_admin_api_key_is_allowed" {
  command = plan
  variables {
    admin_api_key = ""
  }
}

# --- Negative path: REPLACE_ME placeholders are rejected ---------------------
run "default_jwt_secret_rejected" {
  command = plan
  variables {
    jwt_secret = "REPLACE_ME"
  }
  expect_failures = [var.jwt_secret]
}

run "short_jwt_secret_rejected" {
  command = plan
  variables {
    jwt_secret = "too-short"
  }
  expect_failures = [var.jwt_secret]
}

run "default_secret_key_rejected" {
  command = plan
  variables {
    secret_key = "REPLACE_ME"
  }
  expect_failures = [var.secret_key]
}

run "non_fernet_secret_key_rejected" {
  command = plan
  variables {
    # 32 chars but not a valid 44-char Fernet key.
    secret_key = "abcdefghijklmnopqrstuvwxyz123456"
  }
  expect_failures = [var.secret_key]
}

run "default_admin_api_key_rejected" {
  command = plan
  variables {
    admin_api_key = "REPLACE_ME"
  }
  expect_failures = [var.admin_api_key]
}

run "short_admin_api_key_rejected" {
  command = plan
  variables {
    admin_api_key = "too-short-admin-key"
  }
  expect_failures = [var.admin_api_key]
}
