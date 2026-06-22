# Runbook: guarded full `terraform apply`

How to run a deliberate, full `terraform apply` against the live AutoTiers
infrastructure without tripping the two known drift traps. Implements issue #396,
surfaced during the v3.8–v3.12 stuck-deploy incident.

## Why this needs a runbook

Day-to-day deploys roll the ECS services via the deploy workflow, **not** via
Terraform — the services carry `ignore_changes = [task_definition, ...]` so
Terraform never reverts a CI-pushed image. As a result, nobody runs a *full*
`terraform apply` routinely, and two pieces of Terraform-vs-AWS drift have
accumulated that will bite the next person who does:

1. An immutable-attribute trap on the **live ALB security group** that, applied
   naively, destroys-and-recreates the SG on the production api path.
2. Expected-but-noisy **task-definition revision drift** that produces a scary
   plan diff which must be read, not rubber-stamped.

This runbook makes that apply a deliberate act.

## Preconditions

- Run from a host with **AWS credentials + DNS reachability** to the account.
- Terraform state is the **local backend** (`infra/terraform.tfstate`), not S3 —
  the `backend "s3"` block in `infra/main.tf` is commented out. Whoever applies
  owns that state file; do not apply from two checkouts. Migrating to the S3
  backend (uncomment + `terraform init -migrate-state`) is worth pairing with
  this apply but is **out of scope** here — it is tracked separately.
- Pull `main` so you have the ALB SG `create_before_destroy` fix (issue #396);
  applying an older checkout reintroduces trap (1).

## (a) ALB security group — the immutable-description trap

`infra/security_groups.tf` `aws_security_group.alb` has description
**"Allow HTTP and HTTPS inbound to the ALB"**. A security-group `description` is
**immutable in AWS**: Terraform cannot update it in place. The live SG still
reads the older "Allow HTTP inbound..." wording, so a full apply wants to
**replace** the SG — and the default ordering is destroy-then-create, briefly
stripping the security group off the production ALB.

**The fix (already in `main`):** the SG now carries

```hcl
lifecycle {
  create_before_destroy = true
}
```

and uses `name_prefix` instead of a static `name`. The prefix is mandatory:
SG names are unique per VPC, so with a fixed `name` the create-before-destroy
new SG would collide with the still-present old one and fail the apply
mid-flight — falling back into exactly the destroy-before-create trap. With
`name_prefix`, AWS appends a unique suffix, the new SG is created and attached to
the ALB (and referenced by the ECS SG ingress rule) before the old SG is
detached and destroyed. The stable `Name` tag is preserved so the SG is still
recognisable in the console.

**What to verify in the plan:** the ALB SG shows as a replacement
(`+/-`, "create before destroy") — **not** a `-/+` destroy-before-create — and no
*other* live api-path resource (the ALB itself, the target group, the listeners,
the ECS service) shows a surprise replacement. The ALB's `security_groups` and
the ECS SG ingress rule should update **in place** to point at the new SG.

> Do **not** run a partial apply targeting only the SG. Targeting can defeat the
> graph ordering that makes create-before-destroy safe. Apply the whole config.

## (b) Task-definition revision drift

The local Terraform config is ahead of the deployed services on task-def
revisions:

| Service     | Registered in AWS | Service runs |
|-------------|-------------------|--------------|
| `backend`   | `:5`              | `:4`         |
| `scheduler` | `:4`              | `:1`         |

This is **expected steady-state**, not a bug: both services set
`ignore_changes` on `task_definition` (`aws_ecs_service.backend` also ignores
`desired_count`), because the deploy workflow — not Terraform — rolls the running
revision. Terraform will register a fresh task-def revision on apply and then
*not* repoint the service at it; the running revision is left to the next deploy.

**Reconcile intentionally — pick one and note which:**

- **Accept (default).** Let Terraform register the new revision; do not force the
  service onto it. The next normal deploy moves the service forward. This is the
  designed behaviour of `ignore_changes` and needs no extra action — just confirm
  the plan shows only a task-def *registration*, not a service `task_definition`
  change (the latter would mean `ignore_changes` regressed).
- **Force-align now.** If you want the services on the Terraform-registered
  revision immediately, run an ECS `update-service --force-new-deployment` (or
  trigger the deploy workflow) *after* the apply. Do not remove `ignore_changes`
  to achieve this — that would hand routine deploy ownership back to Terraform and
  re-create the drift loop.

Whichever you choose, record it in the apply notes / PR so the next operator
knows the revision numbers were a conscious decision.

## The guarded apply, step by step

```bash
cd infra
terraform init                 # local backend; re-run if providers changed
terraform validate
terraform plan -out=tfplan      # READ IT — see the checklist below
# ... human review ...
terraform apply tfplan
```

Plan-review checklist before you type `apply`:

- [ ] ALB SG is a **create-before-destroy** replacement, not destroy-before-create.
- [ ] No other live api-path resource (ALB, target group, listeners, ECS service,
      RDS) shows an unexpected replacement.
- [ ] The only task-def churn is **registration** of new revisions; no service
      shows a `task_definition` change (proves `ignore_changes` still holds).
- [ ] Total destroy count matches what you expect (ideally just the old ALB SG,
      and only *after* its replacement exists).

If anything in the plan is a surprise, stop and investigate — do not apply.

## Verification (`terraform test`)

`infra/tests/alb_sg_lifecycle.tftest.hcl` pins the `name_prefix` migration and the
stable `Name` tag so a future cleanup cannot silently revert the SG to a static
`name` and reopen trap (a). It uses `mock_provider`, so no AWS credentials are
needed:

```bash
cd infra && terraform test     # requires Terraform >= 1.7
```
