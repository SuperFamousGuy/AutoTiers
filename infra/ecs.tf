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
# CloudWatch Log Group
###############################################################################
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.app_name}-${var.environment}/backend"
  retention_in_days = 30

  tags = {
    Name = "${var.app_name}-${var.environment}-backend-logs"
  }
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
          name  = "RUN_SCHEDULER"
          value = "true"
        },
        {
          # JSON array required by the backend's cors_origins setting
          name  = "CORS_ORIGINS"
          value = "[\"https://${aws_cloudfront_distribution.frontend.domain_name}\"]"
        },
        {
          name  = "FRONTEND_URL"
          value = "https://${aws_cloudfront_distribution.frontend.domain_name}"
        },
        {
          name  = "YAHOO_REDIRECT_URI"
          value = "http://${aws_lb.main.dns_name}/api/auth/yahoo/callback"
        },
        {
          name  = "GOOGLE_REDIRECT_URI"
          value = "http://${aws_lb.main.dns_name}/api/auth/google/callback"
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
          name      = "JWT_SECRET"
          valueFrom = aws_secretsmanager_secret.jwt_secret.arn
        },
        {
          name      = "SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.secret_key.arn
        },
        {
          name      = "YAHOO_CLIENT_ID"
          valueFrom = aws_secretsmanager_secret.yahoo_client_id.arn
        },
        {
          name      = "YAHOO_CLIENT_SECRET"
          valueFrom = aws_secretsmanager_secret.yahoo_client_secret.arn
        },
        {
          name      = "GOOGLE_CLIENT_ID"
          valueFrom = aws_secretsmanager_secret.google_client_id.arn
        },
        {
          name      = "GOOGLE_CLIENT_SECRET"
          valueFrom = aws_secretsmanager_secret.google_client_secret.arn
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
