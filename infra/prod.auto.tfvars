# Non-secret production infrastructure config (issue #452).
#
# Committed on purpose — like backend.hcl — so the CI plan/apply jobs and every
# operator running terraform locally use the SAME values. Terraform auto-loads
# any *.auto.tfvars file, so no -var-file flag is needed. An explicit exception
# in infra/.gitignore keeps this file tracked while other *.tfvars stay ignored.
#
# NOTHING SECRET GOES HERE. The secret VALUES (jwt/secret_key/admin/OAuth) come
# from GitHub secrets, injected as TF_VAR_* env vars in the workflow; Terraform
# then WRITES/overwrites them into AWS Secrets Manager secret versions (see
# secrets.tf). Secrets Manager is the deploy-time consumer, not the source — so
# "the value is in Secrets Manager" alone is NOT sufficient for a plan/apply.
#
# Before this file existed, CI planned with the variable defaults
# (manage_dns = false, acm_certificate_arn = ""), which made every plan propose
# to DESTROY the live Route 53 records, the HTTPS listener, and SES verification.

# Publish SES + apex/www/api records to the auto-tiers.com Route 53 zone.
manage_dns = true

# Apex domain. Used for the Route 53 RECORD NAMES (apex/www/api) in dns.tf.
# NOTE: the hosted ZONE itself is looked up via var.ses_route53_zone_name
# (ses.tf:29), not this variable — dns.tf just reuses that zone_id. They share
# the same value here, but keep both in sync if the zone name ever diverges.
domain_name = "auto-tiers.com"

# ACM cert fronting the ALB HTTPS listener (us-east-1). Not secret — an ARN.
acm_certificate_arn = "arn:aws:acm:us-east-1:400360841089:certificate/d275c22f-a27f-4970-9048-7e2f91ebf06b"
