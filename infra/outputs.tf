output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer. Use this to reach the backend API."
  value       = aws_lb.main.dns_name
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name serving the frontend SPA."
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "ecr_repository_url" {
  description = "ECR repository URL. Push backend images here before deploying."
  value       = aws_ecr_repository.backend.repository_url
}

output "aurora_endpoint" {
  description = "Aurora cluster writer endpoint (used in DATABASE_URL)."
  value       = aws_rds_cluster.main.endpoint
  sensitive   = true
}

output "migrate_task_family" {
  description = "Family of the one-off Alembic migration task definition (alembic upgrade head). Run it manually with the migrate_run_command output."
  value       = aws_ecs_task_definition.migrate.family
}

output "migrate_run_command" {
  description = "Ready-to-run command that applies pending migrations as a one-off ECS task (used by Terraform on apply and the deploy workflow on release)."
  value = join(" ", [
    "${path.module}/scripts/run_migrations.sh",
    "--cluster ${aws_ecs_cluster.main.name}",
    "--task-definition ${aws_ecs_task_definition.migrate.family}",
    "--region ${var.aws_region}",
    "--from-service ${aws_ecs_service.backend.name}",
  ])
}

output "ops_alerts_topic_arn" {
  description = "SNS topic receiving operational alarms (scheduler RunningTaskCount, data freshness — issue #401). Subscribe the team's pager/chat here (or set var.ops_alert_email)."
  value       = aws_sns_topic.ops_alerts.arn
}
