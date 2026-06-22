# Guards the ALB security-group replacement fix from issue #396.
#
# An SG `description` is immutable in AWS, so any wording change forces a REPLACE
# of aws_security_group.alb — which sits on the live api path. The fix routes
# that replacement through create_before_destroy so the new SG is attached before
# the old one is detached. create_before_destroy on an SG is only viable with
# name_prefix (a static `name` would collide on the unique-per-VPC name during the
# brief window both SGs exist, failing the apply). These assertions lock in the
# name_prefix migration so a future "tidy-up" cannot silently revert it to a fixed
# `name` and reopen the destroy-before-create trap.
#
# Note: the create_before_destroy meta-argument itself is not exposed as a
# queryable resource attribute, so name_prefix (its hard prerequisite) is the
# observable proxy the test pins.
#
# Run with:  cd infra && terraform test
# Requires Terraform >= 1.7 (uses mock_provider so no AWS credentials are needed).

mock_provider "aws" {}
mock_provider "random" {}

override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d"]
  }
}

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

variables {
  jwt_secret    = "a-sufficiently-long-jwt-signing-secret-value"
  secret_key    = "dKkY-w0jHF6kBE_oTzx7JtAYxHB1yyaJYBNz3X1eYdY="
  admin_api_key = "a-sufficiently-long-admin-api-key-value-123"

  run_migrations_on_apply = false
}

run "alb_sg_uses_name_prefix_not_static_name" {
  command = plan

  # name_prefix must be set so create_before_destroy can stand up a uniquely
  # named replacement SG before destroying the old one.
  assert {
    condition     = aws_security_group.alb.name_prefix == "${var.app_name}-${var.environment}-sg-alb-"
    error_message = "ALB SG must use name_prefix (not a static name) so create_before_destroy does not collide on the unique-per-VPC SG name."
  }

  # The human-facing Name tag must stay stable across the prefix migration so the
  # SG is still recognisable in the console / cost reports.
  assert {
    condition     = aws_security_group.alb.tags["Name"] == "${var.app_name}-${var.environment}-sg-alb"
    error_message = "ALB SG Name tag must remain the stable, un-suffixed app-env-sg-alb value."
  }

  # The description must keep matching the actual ingress rules (HTTP + HTTPS).
  assert {
    condition     = aws_security_group.alb.description == "Allow HTTP and HTTPS inbound to the ALB"
    error_message = "ALB SG description must describe both the HTTP (80) and HTTPS (443) ingress rules it carries."
  }
}
