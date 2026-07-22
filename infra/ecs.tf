###############################################################################
# ECS Cluster
###############################################################################
resource "aws_ecs_cluster" "main" {
  name = "${var.app_name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.app_name}-${var.environment}-ecs-cluster"
  }
}

###############################################################################
# CloudWatch Log Groups
###############################################################################
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.app_name}-${var.environment}/backend"
  retention_in_days = 30

  tags = {
    Name = "${var.app_name}-${var.environment}-backend-logs"
  }
}

resource "aws_cloudwatch_log_group" "scheduler" {
  name              = "/ecs/${var.app_name}-${var.environment}/scheduler"
  retention_in_days = 30

  tags = {
    Name = "${var.app_name}-${var.environment}-scheduler-logs"
  }
}

###############################################################################
# Local: resolved frontend URL / CORS origins
###############################################################################
locals {
  frontend_url = var.frontend_url != "" ? var.frontend_url : "https://${aws_cloudfront_distribution.frontend.domain_name}"
  cors_origins = var.frontend_url != "" ? jsonencode([
    var.frontend_url,
    "https://www.${trimprefix(trimprefix(var.frontend_url, "https://"), "www.")}",
    "https://${aws_cloudfront_distribution.frontend.domain_name}"
  ]) : jsonencode(["https://${aws_cloudfront_distribution.frontend.domain_name}"])
}

###############################################################################
# ECS Task Definition
###############################################################################
resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.app_name}-${var.environment}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "backend"
      image = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      # Non-sensitive environment variables passed as plain env
      environment = [
        {
          name  = "DEBUG"
          value = "false"
        },
        {
          # Scheduler runs in its own single-task service (see aws_ecs_service.scheduler
          # below). Running it here would cause duplicate job executions when auto-scaling
          # brings this service to >1 task.
          name  = "RUN_SCHEDULER"
          value = "false"
        },
        {
          # Migrations are owned by the dedicated migrate task (migrations.tf),
          # run once per deploy before this service rolls. Letting the autoscaled
          # backend replicas migrate on boot would race them (and the scheduler)
          # against the same DB — alembic holds no lock across the DDL.
          name  = "RUN_MIGRATIONS"
          value = "false"
        },
        {
          # JSON array required by the backend's cors_origins setting
          name  = "CORS_ORIGINS"
          value = local.cors_origins
        },
        {
          name  = "FRONTEND_URL"
          value = local.frontend_url
        },
      ]

      # Sensitive values pulled from Secrets Manager at task start.
      # The ECS agent resolves these before the container starts; the value
      # of each secret is injected as the named environment variable.
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = aws_secretsmanager_secret.database_url.arn
        },
        {
          name      = "DATABASE_URL_SYNC"
          valueFrom = aws_secretsmanager_secret.database_url_sync.arn
        },
        {
          name      = "ADMIN_API_KEY"
          valueFrom = aws_secretsmanager_secret.admin_api_key.arn
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      essential = true
    }
  ])

  tags = {
    Name = "${var.app_name}-${var.environment}-backend-task"
  }
}

###############################################################################
# ECS Service
###############################################################################
resource "aws_ecs_service" "backend" {
  name            = "${var.app_name}-${var.environment}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  launch_type     = "FARGATE"
  desired_count   = 1

  network_configuration {
    subnets          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  # Allow rolling updates without a min_healthy_percent floor
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy_attachment.ecs_task_execution_managed,
    # Schema must exist before the API serves traffic (issue #182).
    null_resource.run_migrations,
  ]

  tags = {
    Name = "${var.app_name}-${var.environment}-backend-service"
  }

  lifecycle {
    # Allow external deployments (e.g. CI/CD image tag updates) without
    # Terraform reverting the task definition revision.
    ignore_changes = [task_definition, desired_count]
  }
}

###############################################################################
# Auto Scaling — scale ECS service between 1 and 3 tasks on CPU utilization
###############################################################################
resource "aws_appautoscaling_target" "backend" {
  max_capacity       = 3
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "${var.app_name}-${var.environment}-backend-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value       = 70
    scale_in_cooldown  = 300
    scale_out_cooldown = 60

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

###############################################################################
# Scheduler — separate single-task service (desired_count=1, no autoscaling)
#
# APScheduler is in-process. Running it in the main backend service would cause
# duplicate job executions (and duplicate DB writes) whenever auto-scaling brings
# that service to >1 task. This dedicated service is pinned to exactly one task.
###############################################################################
resource "aws_ecs_task_definition" "scheduler" {
  family                   = "${var.app_name}-${var.environment}-scheduler"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  # refresh_all loads nfl_data_py pandas frames + Sleeper + FantasyPros in one
  # pass; 512 MB OOM-killed the boot-fire refresh (exit 137) into a crash-loop
  # that froze data for 12 days. 512 cpu / 2048 memory is a valid Fargate combo.
  cpu    = 512
  memory = 2048

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_scheduler_task.arn

  container_definitions = jsonencode([
    {
      name  = "scheduler"
      image = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"

      # No port mappings — the scheduler does not serve HTTP traffic.

      environment = [
        { name = "DEBUG", value = "false" },
        { name = "RUN_SCHEDULER", value = "true" },
        # See backend task above — migrations are owned by the migrate task.
        { name = "RUN_MIGRATIONS", value = "false" },
        {
          name  = "CORS_ORIGINS"
          value = local.cors_origins
        },
        { name = "FRONTEND_URL", value = local.frontend_url },
      ]

      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
        { name = "DATABASE_URL_SYNC", valueFrom = aws_secretsmanager_secret.database_url_sync.arn },
        { name = "ADMIN_API_KEY", valueFrom = aws_secretsmanager_secret.admin_api_key.arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.scheduler.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      essential = true
    }
  ])

  tags = {
    Name = "${var.app_name}-${var.environment}-scheduler-task"
  }
}

resource "aws_ecs_service" "scheduler" {
  name            = "${var.app_name}-${var.environment}-scheduler"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.scheduler.arn
  launch_type     = "FARGATE"
  desired_count   = 1

  network_configuration {
    subnets          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  # No load balancer — this service is not internet-facing.

  depends_on = [
    aws_iam_role_policy_attachment.ecs_task_execution_managed,
    # Schema must exist before the scheduler runs jobs (issue #182).
    null_resource.run_migrations,
  ]

  tags = {
    Name = "${var.app_name}-${var.environment}-scheduler-service"
  }

  # The CI deploy (.github/workflows/deploy.yml) rolls this service with a bare
  # `update-service --force-new-deployment` (no --task-definition), which keeps
  # the current revision and just repulls the immutable `:latest` image. We
  # ignore task_definition here so Terraform does not fight that out-of-band
  # ownership of the running revision.
  #
  # CONSEQUENCE for task-definition changes (cpu/memory/env/secrets): a plain
  # `terraform apply` registers a NEW revision but does NOT move the service to
  # it, and a bare `--force-new-deployment` redeploys the OLD revision. To make
  # such a change take effect, point the service at the new revision explicitly
  # after apply:
  #   aws ecs update-service --cluster <cluster> --service <this-service> \
  #     --task-definition <family> --force-new-deployment
  # The family name selects the latest ACTIVE revision (the one apply just
  # registered). Safe because backend_image_tag defaults to `latest`, so the
  # new revision carries the same image already running — only cpu/memory
  # (etc.) change, no image rollback.
  lifecycle {
    ignore_changes = [task_definition]
  }
}
