# Non-secret production infrastructure config (issue #452).
#
# Committed on purpose — like backend.hcl — so the CI plan/apply jobs and every
# operator running terraform locally use the SAME values. Terraform auto-loads
# any *.auto.tfvars file, so no -var-file flag is needed. An explicit exception
# in infra/.gitignore keeps this file tracked while other *.tfvars stay ignored.
#
# NOTHING SECRET GOES HERE. Secrets (jwt/secret_key/admin/OAuth) live in AWS
# Secrets Manager and reach Terraform via TF_VAR_* env vars in the workflow.
#
# Before this file existed, CI planned with the variable defaults
# (manage_dns = false, acm_certificate_arn = ""), which made every plan propose
# to DESTROY the live Route 53 records, the HTTPS listener, and SES verification.

# Publish SES + apex/www/api records to the auto-tiers.com Route 53 zone.
manage_dns = true

# Apex domain; the SES/Route53 data sources derive the hosted zone from it.
domain_name = "auto-tiers.com"

# ACM cert fronting the ALB HTTPS listener (us-east-1). Not secret — an ARN.
acm_certificate_arn = "arn:aws:acm:us-east-1:400360841089:certificate/d275c22f-a27f-4970-9048-7e2f91ebf06b"
