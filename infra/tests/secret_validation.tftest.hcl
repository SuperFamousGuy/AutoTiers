# Validates the secret-variable validation blocks in variables.tf (issue #183).
#
# Goal: a `terraform plan` must FAIL fast when admin_api_key is left at its
# REPLACE_ME placeholder (or is otherwise malformed), and must PASS when
# supplied with a real value — so an insecure default can never be applied to a
# deployment. (jwt_secret / secret_key / OAuth secrets were removed with the
# accounts+SES teardown, so their validation tests are gone.)
#
# Run with:  cd infra && terraform init -backend=false && terraform test
# Requires Terraform >= 1.7 (uses mock_provider so no AWS credentials are
# needed). -backend=false is required because infra/main.tf now declares an S3
# backend (issue #452); it skips reaching S3 so these mock tests stay offline.
# Wired into CI by the `infra` workflow's plan job (.github/workflows/infra.yml).

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
  target = data.aws_iam_policy_document.ops_alerts
  values = {
    json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }
}

variables {
  admin_api_key = "a-sufficiently-long-admin-api-key-value-123"

  # Keep apply-time-only behaviour out of the plan-based test runs.
  run_migrations_on_apply = false
}

# --- Positive path: a real admin key validates cleanly ----------------------
run "valid_secrets_pass_validation" {
  command = plan
}

run "empty_admin_api_key_is_allowed" {
  command = plan
  variables {
    admin_api_key = ""
  }
}

# --- Negative path: REPLACE_ME placeholder / too-short is rejected -----------
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
