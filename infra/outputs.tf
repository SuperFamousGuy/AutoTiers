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

output "ses_domain_identity_arn" {
  description = "ARN of the SES domain identity used for transactional auth email."
  value       = aws_ses_domain_identity.main.arn
}

output "ses_notifications_topic_arn" {
  description = "SNS topic receiving SES bounce/complaint notifications. Subscribe ops/alerting here (or set var.ses_ops_email)."
  value       = aws_sns_topic.ses_notifications.arn
}
