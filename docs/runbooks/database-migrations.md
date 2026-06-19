# Runbook: database migrations (Alembic bootstrap)

How the deployed Aurora schema is created and kept current. Implements issue
#182 on top of the Aurora cluster from PR #179.

## TL;DR

Migrations are applied by a **single dedicated one-off ECS task** that runs
`alembic upgrade head` and exits. Nothing else in production migrates:

- The backend and scheduler services run with `RUN_MIGRATIONS=false`, so the
  shared container entrypoint skips its in-container migrate step. This avoids
  the autoscaled backend replicas and the scheduler racing to migrate the same
  database.
- `terraform apply` runs the migrate task automatically (and blocks the
  services on it), so a fresh environment comes up with a schema.
- The deploy workflow runs the migrate task before force-redeploying, so every
  release applies any new migrations before the new image serves traffic.

Local docker/podman compose is unchanged: there `RUN_MIGRATIONS` is unset, so it
defaults to `true` and the dev container migrates itself on boot.

## Moving parts

| Piece | Where | Role |
|---|---|---|
| `aws_ecs_task_definition.migrate` | `infra/migrations.tf` | One-off Fargate task, `command = alembic upgrade head`, `RUN_MIGRATIONS=false`. |
| `null_resource.run_migrations` | `infra/migrations.tf` | Runs the task on `terraform apply` when the image tag or any migration file changes. |
| `run_migrations.sh` | `infra/scripts/` | Runs the task via `aws ecs run-task`, waits, and exits non-zero if the migration container exits non-zero. |
| `RUN_MIGRATIONS` gate | `backend/scripts/entrypoint.sh` | Default `true` (local dev); set `false` on prod services so only the migrate task migrates. |
| `Run database migrations` step | `.github/workflows/deploy.yml` | Runs the migrate task on every release, before force-redeploy. |

## First provision (`terraform apply`)

1. Push a backend image to ECR first — the migrate task and the services all
   reference `:<backend_image_tag>` (default `latest`). On a brand-new account
   with an empty ECR repo, push an image before `apply` (or `apply` once to
   create the repo, push, then `apply` again).
2. `terraform apply`. The migrate task runs `alembic upgrade head`; the backend
   and scheduler services only come up after it succeeds.
3. If the migration fails, `apply` fails and the services are not created —
   fix forward and re-apply.

To run `apply` somewhere without AWS credentials or a live cluster (plan-only,
`terraform validate` in CI), set `run_migrations_on_apply = false`.

## Subsequent deploys (new migrations)

The deploy workflow (`.github/workflows/deploy.yml`, on `release: published`):

1. Build + push the new image to ECR.
2. **Run database migrations** — runs the migrate task and waits. A non-zero
   exit fails the job and the services are NOT redeployed (so a broken
   migration never reaches serving traffic).
3. Force-redeploy backend + scheduler onto the new image.

The migrate task family is `<ECS_CLUSTER>-migrate` (e.g. `autotiers-prod-migrate`).
The network config is discovered from the backend service, so no extra GitHub
Actions variables are needed.

## Running migrations manually

Use the `migrate_run_command` Terraform output, or directly:

```bash
./infra/scripts/run_migrations.sh \
  --cluster autotiers-prod \
  --task-definition autotiers-prod-migrate \
  --region us-east-1 \
  --from-service autotiers-prod-backend
```

Logs stream to the `/ecs/autotiers-prod/migrate` CloudWatch log group.

## Long-running migrations

`run_migrations.sh` uses `aws ecs wait tasks-stopped`, whose default waiter caps
out around 10 minutes (6s × 100 polls). A migration that legitimately runs
longer (e.g. a large backfill) makes the waiter — not the migration — error out,
so the runner exits non-zero and the deploy is blocked even though the migration
may still finish. This fails *safe* (no broken schema serves traffic), but for a
known long migration, run it manually outside the deploy window (e.g. with a
longer `--cli-read-timeout` or by polling `describe-tasks` yourself) before
cutting the release.

## Rollback

Alembic downgrades are not run automatically. To roll back a migration, run the
migrate task definition with an overridden command, e.g.:

```bash
aws ecs run-task --cluster autotiers-prod \
  --task-definition autotiers-prod-migrate --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={subnets=[...],securityGroups=[...],assignPublicIp=DISABLED}' \
  --overrides '{"containerOverrides":[{"name":"migrate","command":["alembic","downgrade","-1"]}]}'
```

Prefer fixing forward with a new migration where possible.
