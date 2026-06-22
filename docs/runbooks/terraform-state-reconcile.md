# Runbook: reconciling Terraform state drift (prod)

How to bring the deployed prod infra back in line with committed `infra/` when
`terraform plan` wants to do far more than any intended change. Implements issue
#411.

This is a **deliberate, maintenance-window** procedure — not a hotfix. The whole
point is to avoid the two dangerous things a naive `terraform apply` would do:
recreate the internet-facing ALB security group (dropping prod traffic) and
re-run Alembic migrations against the prod DB.

## TL;DR

The drift seen on 2026-06-22 was:

```
Plan: 4 to add, 2 to change, 4 to destroy.

  # aws_ecs_task_definition.backend       must be replaced
  # aws_ecs_task_definition.scheduler     must be replaced
  # aws_lb.main                           will be updated in-place
  # aws_security_group.alb                must be replaced   <-- destroy + recreate
  # aws_security_group.ecs                will be updated in-place (cascade)
  # null_resource.run_migrations[0]       is tainted, so must be replaced
```

Three classes of change, each handled differently:

| Resource | Real nature | Action |
|---|---|---|
| `aws_security_group.alb` replacement | Internet-facing SG; destroy-before-create = downtime | Make the replacement **create-before-destroy** (code fix landed) before applying |
| `null_resource.run_migrations` tainted | A prior `apply`'s `local-exec` failed/was interrupted, tainting it | `alembic upgrade head` is idempotent → either `untaint` to skip, or let it re-run (safe) |
| `aws_ecs_task_definition.{backend,scheduler}` replacement | Task defs are immutable; "replace" == register a new revision | Harmless — services `ignore_changes = [task_definition]`, so apply only registers a revision |

## Why each resource drifted

### `aws_security_group.alb` — destroy + recreate

A security group replacement plus the default **destroy-before-create** lifecycle
is the dangerous one. The ALB SG is referenced by:

- `aws_lb.main` (`security_groups = [aws_security_group.alb.id]`), and
- `aws_security_group.ecs`'s ingress rule (`security_groups = [aws_security_group.alb.id]`),

so its replacement cascades — the ECS ingress rule shows
`security_groups = (known after apply)` — and a destroy-before-create swap means
the ALB is briefly without an attached SG and the new SG's ID has to propagate to
the ECS ingress before backend traffic is restored.

Root cause of the replacement itself is a `name`/lifecycle-level diff (e.g. a
`name` → `name_prefix` change, or provider-version behaviour change in how the
inline rules hash). Regardless of the exact trigger, the **fix is to make any
replacement safe** rather than to chase the precise byte that differs:

`infra/security_groups.tf` now sets, on `aws_security_group.alb`:

```hcl
name_prefix = "${var.app_name}-${var.environment}-sg-alb-"   # was: name = "...-sg-alb"
lifecycle {
  create_before_destroy = true
}
```

`create_before_destroy` and `name_prefix` are **coupled** — `create_before_destroy`
cannot work with a fixed `name` because AWS rejects the second SG with
`InvalidGroup.Duplicate` before the old one is destroyed. `name_prefix` lets AWS
mint a unique `GroupName` for the replacement so old and new coexist during the
swap. The stable, human-readable identifier stays in the `Name` **tag**
(unchanged), so console / tag-based lookups are unaffected.

### `null_resource.run_migrations[0]` — tainted

A `null_resource` is marked **tainted** when its `local-exec` provisioner fails or
is interrupted on a prior `apply`. Here `run_migrations.sh` (which runs
`alembic upgrade head` via `aws ecs run-task` and blocks on it) did not complete
cleanly on some earlier run, so Terraform flagged the resource for replacement —
which would re-run the migration task on the next apply.

`alembic upgrade head` is **idempotent**: it only applies migrations not yet at
`head` and is a no-op when the schema is already current. So a re-run is *safe*.
The decision is therefore about noise, not danger:

- **Preferred (skip the re-run):** `terraform untaint 'null_resource.run_migrations[0]'`
  so the reconcile apply does not touch it.
- **Acceptable (let it re-run):** leave it tainted; the migrate task runs, finds
  the schema at head, and exits 0.

Either way, confirm the schema is at head first (see
`docs/runbooks/database-migrations.md`). Related: #405 (scheduler runs
`alembic upgrade head` despite `RUN_MIGRATIONS=false`) is a separate
migration-ownership concern — handle it on its own, not in this window.

### `aws_ecs_task_definition.{backend,scheduler}` — replace

ECS task definitions are **immutable**; *any* change registers a new revision, and
Terraform models "new revision" as "must be replaced" because the ARN changes.
Both services set `lifecycle { ignore_changes = [task_definition] }`, so an apply
that registers a new revision does **not** move the running service onto it — the
service keeps serving its current revision. These replacements are therefore
harmless bookkeeping.

> Note: the scheduler is currently running a **CLI-registered** revision (the
> PR #400 OOM bump applied out-of-band via `aws ecs update-service`). Because of
> `ignore_changes = [task_definition]`, Terraform will not fight that running
> revision. The reconcile only re-aligns the *committed* task-def definition in
> state; to actually move the service onto a Terraform-registered revision, follow
> the task-def-redeploy note in `infra/ecs.tf` (`update-service --task-definition`).

## The reconcile (maintenance window)

Pre-req: this branch / PR is merged to `main`, so the `create_before_destroy` +
`name_prefix` fix is in the working tree you plan from.

1. **Announce the window.** Brief traffic disruption is possible during the ALB SG
   swap even with create-before-destroy (ALB SG re-attach + ECS ingress
   propagation). Pick a low-traffic window.

2. **Confirm the schema is already at head** so the migration question is purely
   cosmetic:

   ```bash
   ./infra/scripts/run_migrations.sh \
     --cluster autotiers-prod --task-definition autotiers-prod-migrate \
     --region us-east-1 --from-service autotiers-prod-backend
   ```

   (Idempotent — a no-op if already at head. Or inspect `alembic current` against
   the DB.)

3. **Untaint the migration runner** so the apply does not re-run it:

   ```bash
   cd infra && terraform untaint 'null_resource.run_migrations[0]'
   ```

4. **Plan and read every line.** Confirm the ALB SG now shows a
   create-before-destroy replacement (the new SG is created first), the ECS SG is
   updated in-place, the task-def replacements are revision-only, and
   `run_migrations` is gone from the plan:

   ```bash
   terraform plan -out=reconcile.tfplan
   ```

5. **Apply the saved plan** in the window:

   ```bash
   terraform apply reconcile.tfplan
   ```

   Watch the ALB SG: Terraform creates `...-sg-alb-<suffix>`, repoints
   `aws_lb.main` and the ECS ingress at it, then destroys the old SG.

6. **Verify traffic** end-to-end (health endpoint + a real request) before closing
   the window:

   ```bash
   curl -fsS https://api.auto-tiers.com/health
   ```

7. **Confirm `terraform plan` is clean (empty)** — Terraform is the source of
   truth again:

   ```bash
   terraform plan   # expect: No changes. Your infrastructure matches the configuration.
   ```

## If a clean plan is *not* reached

If step 7 still shows drift, do **not** brute-force an apply. Common cases:

- **An attribute that should be imported, not recreated** — use
  `terraform import` / `terraform state` surgery to adopt the live resource into
  state rather than replacing it.
- **A still-tainted resource** — `terraform untaint <addr>` once you've confirmed
  it is healthy.
- **Out-of-band drift the code doesn't model** (e.g. the CLI-registered scheduler
  revision) — that is expected and intentionally ignored via
  `ignore_changes`; it should not appear in the plan.

Capture whatever remains as a fresh issue rather than forcing it through.

## Preventing recurrence

- The ALB SG fix removes the *downtime* hazard for that SG permanently — any
  future replacement is create-before-destroy.
- The same `create_before_destroy` + `name_prefix` hygiene is **not yet** applied
  to `aws_security_group.ecs` / `.rds` (they currently only update in-place); a
  follow-up issue tracks extending it so they are equally safe if ever replaced.
- Avoid landing infra changes out-of-band via the AWS CLI where possible — each
  one widens the gap between state and reality. When unavoidable (as with PR
  #400), file the divergence so the next reconcile knows about it.
