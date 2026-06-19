###############################################################################
# Alembic migration bootstrap (issue #182)
#
# PR #179 provisions the Aurora cluster but nothing runs `alembic upgrade head`,
# so the backend ECS service would start against an empty schema. This file adds
# a dedicated, single-authority migration runner:
#
#   - aws_ecs_task_definition.migrate — a one-off Fargate task that runs
#     `alembic upgrade head` and exits (RUN_MIGRATIONS=false so the shared
#     entrypoint does NOT also migrate; the command IS the migration).
#   - null_resource.run_migrations — runs that task via `aws ecs run-task` on
#     every apply whose image tag or migration files changed, and blocks until
#     it succeeds (see infra/scripts/run_migrations.sh).
#
# The backend and scheduler services depend_on null_resource.run_migrations
# (see ecs.tf) so on FIRST provision the schema is present before either service
# is created, and a failed migration fails `terraform apply` instead of rolling
# a broken service.
#
# Note on steady state: both services set ignore_changes = [task_definition,
# desired_count], so a later `terraform apply` that only re-runs migrations does
# NOT re-touch the converged services — depends_on is a no-op when the dependent
# has no planned change. That is fine: ROUTINE schema rollout on a release is
# owned by the deploy workflow's sequential steps (run migrations -> wait ->
# force-redeploy), not by `terraform apply`. Terraform's job here is first
# provision and any apply that changes the image tag / migrations.
###############################################################################

resource "aws_cloudwatch_log_group" "migrate" {
  name              = "/ecs/${var.app_name}-${var.environment}/migrate"
  retention_in_days = 30

  tags = {
    Name = "${var.app_name}-${var.environment}-migrate-logs"
  }
}

###############################################################################
# Migrate task role — the migration only talks to Postgres (over the network),
# never to the AWS API, so this role is intentionally bare (no inline policies).
# Image pull, log writes, and secret resolution all run under the shared
# execution role, exactly as the backend/scheduler tasks do.
###############################################################################
resource "aws_iam_role" "ecs_migrate_task" {
  name               = "${var.app_name}-${var.environment}-ecs-migrate-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json

  tags = {
    Name = "${var.app_name}-${var.environment}-ecs-migrate-task-role"
  }
}

###############################################################################
# Migrate task definition — same image as the backend, but its command is the
# migration itself. The entrypoint waits for Postgres, then (because
# RUN_MIGRATIONS=false) skips its own migrate step and exec's this command, so
# `alembic upgrade head` runs exactly once and the container exits with alembic's
# exit code.
###############################################################################
resource "aws_ecs_task_definition" "migrate" {
  # NOTE: the deploy workflow derives this family as `<ECS_CLUSTER>-migrate`
  # (.github/workflows/deploy.yml). Keep the GitHub `ECS_CLUSTER` variable equal
  # to `${app_name}-${environment}` (default `autotiers-prod`) or that step will
  # target a non-existent family and fail (loudly, which is the safe direction).
  family                   = "${var.app_name}-${var.environment}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_migrate_task.arn

  container_definitions = jsonencode([
    {
      name    = "migrate"
      image   = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"
      command = ["alembic", "upgrade", "head"]

      # No port mappings — this task serves no traffic.

      environment = [
        { name = "DEBUG", value = "false" },
        # The shared entrypoint must NOT also migrate; this task IS the
        # migration. Keeping the in-container migrate off everywhere in prod
        # means migrations only ever run from this single task.
        { name = "RUN_MIGRATIONS", value = "false" },
        { name = "SEED_DEV_DATA", value = "false" },
        { name = "RUN_SCHEDULER", value = "false" },
      ]

      # alembic/env.py resolves the URL from settings.database_url_sync, so the
      # sync URL secret is the one that matters; the async URL is included for
      # parity with the other task definitions / app config import.
      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
        { name = "DATABASE_URL_SYNC", valueFrom = aws_secretsmanager_secret.database_url_sync.arn },
        { name = "JWT_SECRET", valueFrom = aws_secretsmanager_secret.jwt_secret.arn },
        { name = "SECRET_KEY", valueFrom = aws_secretsmanager_secret.secret_key.arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.migrate.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      essential = true
    }
  ])

  tags = {
    Name = "${var.app_name}-${var.environment}-migrate-task"
  }
}

###############################################################################
# Run the migration on apply.
#
# triggers re-run the task whenever the deployed image tag changes or any
# migration file changes, so a `terraform apply` after a schema change applies
# it. run_migrations_on_apply can disable the local-exec for plan-only or
# CI-validate environments that have no AWS credentials / live cluster.
###############################################################################
resource "null_resource" "run_migrations" {
  count = var.run_migrations_on_apply ? 1 : 0

  triggers = {
    image_tag      = var.backend_image_tag
    task_def       = aws_ecs_task_definition.migrate.arn
    migrations_sha = sha1(join(",", [for f in fileset("${path.module}/../backend/alembic/versions", "*.py") : filesha1("${path.module}/../backend/alembic/versions/${f}")]))
  }

  provisioner "local-exec" {
    command = "${path.module}/scripts/run_migrations.sh --cluster ${aws_ecs_cluster.main.name} --task-definition ${aws_ecs_task_definition.migrate.family} --region ${var.aws_region} --subnets ${aws_subnet.private_a.id},${aws_subnet.private_b.id} --security-groups ${aws_security_group.ecs.id}"
  }

  depends_on = [
    aws_ecs_cluster.main,
    aws_ecs_task_definition.migrate,
    aws_rds_cluster.main,
  ]
}
