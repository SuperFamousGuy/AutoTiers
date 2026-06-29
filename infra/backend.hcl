# Partial backend configuration for the S3 remote state + DynamoDB lock
# (issue #452). Supplied to Terraform with:
#
#   terraform init -backend-config=backend.hcl
#
# These values are NOT secret (no credentials, no tokens) — they are committed
# so every operator and the CI workflow initialise against the SAME state. The
# bucket and lock table must be created once before the first apply; see
# docs/runbooks/terraform-ci-apply.md for the bootstrap + state-migration steps.
#
# Account 400360841089, region us-east-1 (issue #452 notes). The account id is
# appended to the bucket name because S3 bucket names are globally unique.

bucket         = "autotiers-prod-tfstate-400360841089"
key            = "autotiers/prod/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "autotiers-terraform-locks"
encrypt        = true
