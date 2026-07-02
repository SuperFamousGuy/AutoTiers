# Runbook: CI Terraform plan/apply + remote-state bootstrap

How the `infra` CI workflow keeps live AWS in sync with `infra/`, and the
**one-time bootstrap** that has to happen before it can run. Implements issue
#452, surfaced by the v3.8–v3.11 stuck-deploy incident where `infra/migrations.tf`
was merged to `main` but never `terraform apply`-ed, so the
`autotiers-prod-migrate` task family did not exist when the deploy workflow tried
to use it.

## What the workflow does (`.github/workflows/infra.yml`)

| Event | Job | Action |
|---|---|---|
| PR touching `infra/**` | `plan` | `terraform fmt -check` + `validate` + `terraform test` (offline, mock_provider) → `terraform plan` against live state → posts the plan as a sticky PR comment for review. |
| Push to `main` touching `infra/**` | `apply` | `terraform apply -auto-approve` against the live account, serialized by a concurrency group on top of the DynamoDB state lock. |

So the moment an infra change lands on `main`, AWS is reconciled to it — *before*
any release that references the new resource is cut.

## Remote state + locking (issue #452 AC4)

`infra/main.tf` declares a **partial** `backend "s3" {}`. The concrete,
non-secret values live in `infra/backend.hcl`:

```hcl
bucket         = "autotiers-prod-tfstate-400360841089"
key            = "autotiers/prod/terraform.tfstate"
region         = "us-east-1"
dynamodb_table = "autotiers-terraform-locks"
encrypt        = true
```

- **State** is one shared object in S3 — not a file on whoever last applied
  locally — so CI and every operator read/write the same authority.
- **Locking** uses the DynamoDB table; concurrent applies block on the lock
  instead of clobbering state. The workflow's `terraform-apply-production`
  concurrency group is a second guard so two merges queue rather than race.

### Why a partial backend

The block in `main.tf` is intentionally empty so credential-free runs work:

```bash
cd infra
terraform init -backend=false   # no S3, no credentials
terraform validate
terraform test                  # mock_provider — offline
```

CI (and a real plan/apply) wires the backend explicitly:

```bash
terraform init -backend-config=backend.hcl
```

## One-time bootstrap (do this BEFORE the first CI apply)

The state bucket, the lock table, and the migrated state do not exist yet. Until
they do, the `apply` job fails at `terraform init` — loudly, which is safe.

Run these once from a host that currently holds the local `infra/terraform.tfstate`
(see `docs/runbooks/terraform-guarded-apply.md` for who that is) with credentials
for account 400360841089:

```bash
# 1. State bucket (versioned + encrypted + private).
aws s3api create-bucket --bucket autotiers-prod-tfstate-400360841089 --region us-east-1
aws s3api put-bucket-versioning --bucket autotiers-prod-tfstate-400360841089 \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket autotiers-prod-tfstate-400360841089 \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket autotiers-prod-tfstate-400360841089 \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# 2. Lock table (PAY_PER_REQUEST; the key MUST be named LockID).
aws dynamodb create-table --table-name autotiers-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST --region us-east-1

# 3. Migrate the existing LOCAL state into S3. Run from infra/ on the host that
#    owns the current terraform.tfstate. Terraform detects the backend change and
#    offers to copy state up — answer "yes".
cd infra
terraform init -backend-config=backend.hcl -migrate-state
```

After migration, confirm a clean read and that nothing surprising is pending:

```bash
terraform plan   # (already inited above) read the plan — backend config was
                 # supplied to `init`; `terraform plan` takes no -backend-config
```

Mind the drift traps documented in `docs/runbooks/terraform-guarded-apply.md`
(ALB SG replacement — now create-before-destroy; task-def revision drift —
expected, `ignore_changes`) the first time a full apply runs.

### Required CI secrets/variables

Set these in **Settings → Secrets and variables** before enabling the workflow:

- Variable `AWS_REGION` = `us-east-1` (already set for deploy).
- Secrets `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — a principal that can
  apply the whole config. Reusing the `autotiers-admin` deploy user is the
  simplest correct choice; `infra/ci-apply-policy.json` documents a dedicated
  `autotiers-terraform` user as the scoped alternative.
- Secrets `TF_VAR_JWT_SECRET`, `TF_VAR_SECRET_KEY`, `TF_VAR_ADMIN_API_KEY` — the
  **live** prod values. They feed `aws_secretsmanager_secret_version`; if they do
  not match what is already in Secrets Manager, an apply rewrites those secret
  versions. The OAuth pairs (`TF_VAR_YAHOO_CLIENT_ID`/`_SECRET`,
  `TF_VAR_GOOGLE_CLIENT_ID`/`_SECRET`) are optional (variables default to `""`).

## Ordering vs. the deploy workflow (issue #452 AC3)

`deploy.yml` runs on **release published**, not on push, and deliberately does
**not** run `terraform apply` (services carry `ignore_changes = [task_definition]`
so Terraform never reverts a CI-pushed image — see `terraform-guarded-apply.md`).
The required ordering is therefore:

> **infra change → merge to `main` → `infra` apply job completes → cut the release.**

Because apply runs on merge, a release cut from already-merged `main` references
infra that is already applied. The one residual race is publishing a release in
the ~2 minutes between an infra merge and the apply finishing; avoid cutting a
release while the `infra` workflow is still running for that merge. A
plan-must-be-empty gate inside `deploy.yml` is **not** viable because task-def
revision drift makes a full plan non-empty at steady state (documented in
`terraform-guarded-apply.md`); the ordering above is the contract instead.
