###############################################################################
# ECS Task Execution Role
# Used by the ECS agent / container runtime to:
#   - pull images from ECR
#   - write logs to CloudWatch
#   - fetch secret values from Secrets Manager at task start
###############################################################################
data "aws_iam_policy_document" "ecs_task_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${var.app_name}-${var.environment}-ecs-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json

  tags = {
    Name = "${var.app_name}-${var.environment}-ecs-exec-role"
  }
}

# Attach AWS-managed policy for ECR pull + CW logs
resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow reading every secret created for this app
data "aws_iam_policy_document" "secrets_read" {
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      aws_secretsmanager_secret.db_password.arn,
      aws_secretsmanager_secret.database_url.arn,
      aws_secretsmanager_secret.database_url_sync.arn,
      aws_secretsmanager_secret.admin_api_key.arn,
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name   = "${var.app_name}-${var.environment}-secrets-read"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.secrets_read.json
}

###############################################################################
# ECS Task Role
# Permissions available TO the running application code itself.
###############################################################################
resource "aws_iam_role" "ecs_task" {
  name               = "${var.app_name}-${var.environment}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json

  tags = {
    Name = "${var.app_name}-${var.environment}-ecs-task-role"
  }
}

# No inline policies: the backend app makes no AWS API calls of its own (SES
# sending was removed with the accounts/email teardown). The role still exists
# to satisfy the ECS task definition's task_role_arn requirement.

###############################################################################
# Scheduler Task Role
# The scheduler service gets its own bare task role (it never calls any AWS
# API directly either) rather than sharing the backend's, per least-privilege.
###############################################################################
resource "aws_iam_role" "ecs_scheduler_task" {
  name               = "${var.app_name}-${var.environment}-ecs-scheduler-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json

  tags = {
    Name = "${var.app_name}-${var.environment}-ecs-scheduler-task-role"
  }
}
