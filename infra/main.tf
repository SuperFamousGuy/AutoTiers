terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  # S3 remote state + DynamoDB locking (issue #452). Without remote state the
  # only copy of state lives on whoever last ran `terraform apply` locally, so
  # CI could never apply — and two people applying would corrupt each other's
  # state. Locking serializes concurrent applies.
  #
  # This is a PARTIAL backend: the concrete bucket/key/region/table live in
  # infra/backend.hcl (non-secret) and are supplied at init via
  # `terraform init -backend-config=backend.hcl`. Keeping the block empty lets
  # credential-free workflows (`terraform validate`, `terraform test`) run
  # `terraform init -backend=false` without touching S3 — see
  # docs/runbooks/terraform-ci-apply.md for the one-time bootstrap that creates
  # the bucket/table and migrates the existing local state.
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.app_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
