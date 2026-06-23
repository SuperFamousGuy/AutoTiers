# Validates the scheduler-health / data-freshness alarm wiring (issue #401).
#
# Goal: a `terraform plan` must provision the ops-alerts SNS topic and the
# scheduler RunningTaskCount alarm with the right thresholds, only create the
# email subscription when an address is supplied, and reject a non-positive
# evaluation-period count.
#
# Run with:  cd infra && terraform test
# Only `terraform test` requires Terraform >= 1.7 (this file uses mock_provider,
# introduced in 1.7, so no AWS credentials are needed). The module itself still
# targets >= 1.6 (see infra/main.tf required_version) — the higher floor applies
# to running these tests, not to applying the module.

mock_provider "aws" {}
mock_provider "random" {}

override_data {
  target = data.aws_availability_zones.available
  values = {
    names = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d"]
  }
}

# Policy-document data sources render to JSON consumed by resources that
# validate it; the mocked provider returns a random string, so supply minimal
# valid JSON.
override_data {
  target = data.aws_iam_policy_document.ecs_task_assume_role
  values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
}
override_data {
  target = data.aws_iam_policy_document.secrets_read
  values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
}
override_data {
  target = data.aws_iam_policy_document.ses_send
  values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
}
override_data {
  target = data.aws_iam_policy_document.ses_notifications
  values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
}
override_data {
  target = data.aws_iam_policy_document.ops_alerts
  values = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
}

variables {
  jwt_secret              = "a-sufficiently-long-jwt-signing-secret-value"
  secret_key              = "dKkY-w0jHF6kBE_oTzx7JtAYxHB1yyaJYBNz3X1eYdY="
  admin_api_key           = "a-sufficiently-long-admin-api-key-value-123"
  run_migrations_on_apply = false
}

# --- The alarm is wired with the right metric/threshold/action --------------
run "scheduler_alarm_configured" {
  command = plan

  assert {
    condition     = aws_cloudwatch_metric_alarm.scheduler_no_running_tasks.metric_name == "RunningTaskCount"
    error_message = "Scheduler alarm must watch the RunningTaskCount metric."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.scheduler_no_running_tasks.namespace == "ECS/ContainerInsights"
    error_message = "RunningTaskCount lives in the ECS/ContainerInsights namespace."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.scheduler_no_running_tasks.comparison_operator == "LessThanThreshold"
    error_message = "Alarm must fire when running tasks fall BELOW the threshold."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.scheduler_no_running_tasks.threshold == 1
    error_message = "Alarm threshold must be 1 running task."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.scheduler_no_running_tasks.treat_missing_data == "breaching"
    error_message = "Missing data (a task that never reports) must be treated as breaching."
  }
  assert {
    condition     = contains(aws_cloudwatch_metric_alarm.scheduler_no_running_tasks.alarm_actions, aws_sns_topic.ops_alerts.arn)
    error_message = "Alarm must notify the ops-alerts SNS topic."
  }
}

# --- No email var => topic exists, but no subscription ----------------------
run "no_subscription_without_email" {
  command = plan

  assert {
    condition     = length(aws_sns_topic_subscription.ops_alert_email) == 0
    error_message = "No email subscription should be created when ops_alert_email is empty."
  }
}

# --- Email var => one subscription on the ops topic -------------------------
run "subscription_created_with_email" {
  command = plan
  variables {
    ops_alert_email = "ops@example.com"
  }

  assert {
    condition     = length(aws_sns_topic_subscription.ops_alert_email) == 1
    error_message = "Setting ops_alert_email must create exactly one subscription."
  }
  assert {
    condition     = aws_sns_topic_subscription.ops_alert_email[0].protocol == "email"
    error_message = "The ops-alert subscription must use the email protocol."
  }
}

# --- A non-positive evaluation-period count is rejected ---------------------
run "zero_evaluation_periods_rejected" {
  command = plan
  variables {
    scheduler_alarm_evaluation_periods = 0
  }
  expect_failures = [var.scheduler_alarm_evaluation_periods]
}
