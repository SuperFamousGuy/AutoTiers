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

output "ses_domain_identity_arn" {
  description = "ARN of the SES domain identity used for transactional auth email."
  value       = aws_ses_domain_identity.main.arn
}

output "ses_notifications_topic_arn" {
  description = "SNS topic receiving SES bounce/complaint notifications. Subscribe ops/alerting here (or set var.ses_ops_email)."
  value       = aws_sns_topic.ses_notifications.arn
}

# When DNS is external (manage_dns = false), these are the records to add at
# your DNS provider so SES can verify the domain, sign with DKIM, and route
# bounces. null when manage_dns = true (Terraform publishes them itself).
output "ses_dns_records_for_manual_entry" {
  description = "Records to add at your external DNS provider (manage_dns = false). SES verifies asynchronously once they propagate."
  value = var.manage_dns ? null : {
    verification_txt = {
      name  = "_amazonses.${var.ses_domain}"
      type  = "TXT"
      value = aws_ses_domain_identity.main.verification_token
    }
    dkim_cnames = [
      for token in aws_ses_domain_dkim.main.dkim_tokens : {
        name  = "${token}._domainkey.${var.ses_domain}"
        type  = "CNAME"
        value = "${token}.dkim.amazonses.com"
      }
    ]
    mail_from_mx = {
      name  = local.ses_mail_from_domain
      type  = "MX"
      value = "10 feedback-smtp.${var.aws_region}.amazonses.com"
    }
    mail_from_spf_txt = {
      name  = local.ses_mail_from_domain
      type  = "TXT"
      value = "v=spf1 include:amazonses.com ~all"
    }
  }
}
