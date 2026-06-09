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
