###############################################################################
# Scheduler health + data-freshness alarms (issue #401)
#
# The scheduler is a single desired_count=1 in-process APScheduler with no
# monitoring. It has silently stopped refreshing data TWICE — an OOM
# crash-loop (2026-06-09 → 2026-06-21, 12 days) and a --reload reload-loop
# (PR #340, ~8 days) — and BOTH outages were discovered by a user noticing the
# stale banner, not by an alarm. This wires the recurrence-prevention alarm.
#
# Two complementary detections, both routed to one SNS topic the team watches:
#
#   1. ECS RunningTaskCount < 1 on the scheduler service — catches the task
#      dying / crash-looping / failing to place (the exact 2nd-incident shape).
#      Pure CloudWatch metric, no app involvement, fires even if the container
#      never finishes booting.
#
#   2. (App-side, see backend /api/data/health) age of the oldest
#      last_attempted > threshold — catches a scheduler that is *running* but
#      not refreshing. That HTTP check is wired to alerting separately (an
#      uptime monitor / Route 53 health check on /api/data/health); this file
#      owns the infra-level RunningTaskCount alarm.
###############################################################################

# --- Ops alert topic ---------------------------------------------------------
# A dedicated topic for operational alarms (kept separate from the SES
# bounce/complaint topic so alerting subscriptions don't get mixed with email
# deliverability events). An email subscription is created only when
# var.ops_alert_email is set; it requires a one-time confirmation click.
resource "aws_sns_topic" "ops_alerts" {
  name = "${var.app_name}-${var.environment}-ops-alerts"

  tags = {
    Name = "${var.app_name}-${var.environment}-ops-alerts"
  }
}

# CloudWatch publishes alarm-state transitions as the cloudwatch.amazonaws.com
# service principal; without this the topic rejects those deliveries. Scoped to
# this account AND to alarms in our own naming prefix (mirrors the
# ses_notifications least-privilege pattern) so no other alarm in the account
# can publish here. The ArnLike wildcard still allows future ops alarms named
# `${var.app_name}-${var.environment}-*` to reuse this topic.
data "aws_iam_policy_document" "ops_alerts" {
  statement {
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.ops_alerts.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "AWS:SourceArn"
      values   = ["arn:aws:cloudwatch:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alarm:${var.app_name}-${var.environment}-*"]
    }
  }
}

resource "aws_sns_topic_policy" "ops_alerts" {
  arn    = aws_sns_topic.ops_alerts.arn
  policy = data.aws_iam_policy_document.ops_alerts.json
}

resource "aws_sns_topic_subscription" "ops_alert_email" {
  count     = var.ops_alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.ops_alerts.arn
  protocol  = "email"
  endpoint  = var.ops_alert_email
}

# --- Scheduler RunningTaskCount alarm ----------------------------------------
# RunningTaskCount is a Container Insights metric (containerInsights is enabled
# on the cluster, see ecs.tf). It is emitted once a minute per service. If the
# scheduler task dies and ECS cannot replace it (crash-loop / OOM kill /
# placement failure), the value drops to 0 — or the metric stops reporting
# entirely. `treat_missing_data = "breaching"` covers the "no data" case so a
# task that never publishes still trips the alarm rather than sitting in
# INSUFFICIENT_DATA.
resource "aws_cloudwatch_metric_alarm" "scheduler_no_running_tasks" {
  alarm_name        = "${var.app_name}-${var.environment}-scheduler-no-running-tasks"
  alarm_description = "Scheduler service has <1 running task — data refresh is likely frozen (issue #401). Check the scheduler ECS service and CloudWatch logs."

  namespace   = "ECS/ContainerInsights"
  metric_name = "RunningTaskCount"
  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.scheduler.name
  }

  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = var.scheduler_alarm_evaluation_periods
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"

  alarm_actions = [aws_sns_topic.ops_alerts.arn]
  ok_actions    = [aws_sns_topic.ops_alerts.arn]

  tags = {
    Name = "${var.app_name}-${var.environment}-scheduler-no-running-tasks"
  }
}
