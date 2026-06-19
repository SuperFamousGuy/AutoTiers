# Runbook: rolling back a backend deploy

How to recover when a release ships a broken backend image. Implements issue
#188 on top of the deploy workflow from PR #185.

## TL;DR

Every release pushes the backend image to ECR under **two** tags:

- `:latest` — the moving tag the ECS task definitions reference.
- `:<release-tag>` — an immutable versioned tag (e.g. `v1.2.3`) that always
  points at exactly that release's image.

Because each release is preserved under its own versioned tag, rolling back is
"point the service at the previous version's image" rather than "rebuild and
re-push the old code". (Manual `workflow_dispatch` runs have no release tag, so
they are tagged `manual-<short-sha>` instead — still uniquely recoverable.)

## Why two tags

The deploy workflow always force-redeploys onto `:latest`. With only `:latest`,
a failed deploy with a broken image has no easy recovery path — the operator
must check out the previous commit, rebuild, and re-push the old image, racing
the incident. With a versioned tag retained in ECR, the previous good image is
already sitting in the registry; rollback is an ECS operation, not a rebuild.

## Moving parts

| Piece | Where | Role |
|---|---|---|
| `Resolve image tags` step | `.github/workflows/deploy.yml` | Computes the versioned tag from the release name (or `manual-<sha>` on dispatch). |
| `Build Docker image` step | `.github/workflows/deploy.yml` | Builds with both `:latest` and `:<release-tag>`. |
| `Push image to ECR` step | `.github/workflows/deploy.yml` | Pushes both tags. |
| ECS task definition `image` | `infra/ecs.tf` | References `:<backend_image_tag>` (default `latest`). |

## Rolling back

There are two viable paths. Both assume the previous release's versioned image
is still in ECR (it is — versioned tags are never overwritten).

### Option A — re-point a new task definition revision at the prior image (recommended)

Roll forward to a *new* task definition revision whose image is pinned to the
last-known-good versioned tag, rather than `:latest`. This is the most durable
fix because the bad `:latest` image stays put but no longer serves traffic.

1. Identify the good version (the release before the bad one), e.g. `v1.2.2`.
2. Render the current backend task definition, swap the image tag, and register
   the result as a new revision:

   ```bash
   GOOD_TAG=v1.2.2
   CLUSTER=autotiers-prod
   SERVICE=autotiers-prod-backend

   TASKDEF_ARN=$(aws ecs describe-services \
     --cluster "$CLUSTER" --services "$SERVICE" \
     --query 'services[0].taskDefinition' --output text)

   aws ecs describe-task-definition --task-definition "$TASKDEF_ARN" \
     --query 'taskDefinition' --output json \
   | jq --arg img "$(aws ecs describe-task-definition --task-definition "$TASKDEF_ARN" \
         --query 'taskDefinition.containerDefinitions[0].image' --output text \
         | sed "s/:[^:]*$/:$GOOD_TAG/")" \
       '.containerDefinitions[0].image = $img
        | del(.taskDefinitionArn,.revision,.status,.requiresAttributes,.compatibilities,.registeredAt,.registeredBy)' \
   > /tmp/rollback-taskdef.json

   NEW_ARN=$(aws ecs register-task-definition \
     --cli-input-json file:///tmp/rollback-taskdef.json \
     --query 'taskDefinition.taskDefinitionArn' --output text)

   aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
     --task-definition "$NEW_ARN" --no-cli-pager
   ```

3. Repeat for the scheduler service (`autotiers-prod-scheduler`) if the bad
   image also rolled there.
4. Wait for steady state:

   ```bash
   aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE"
   ```

### Option B — roll back to a prior task definition revision

If the previous revision already pinned the good versioned tag (not `:latest`),
just force the service back onto that earlier revision:

```bash
CLUSTER=autotiers-prod
SERVICE=autotiers-prod-backend

# List recent revisions newest-first and pick the prior good one.
aws ecs list-task-definitions --family-prefix "$SERVICE" \
  --sort DESC --max-items 10 --no-cli-pager

aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
  --task-definition autotiers-prod-backend:<GOOD_REVISION> --no-cli-pager
```

Note: revisions that reference `:latest` will pull whatever `:latest` currently
is (the bad image), so this option is only a true rollback when the revision
pins a versioned tag. When in doubt, use Option A.

## Database considerations

A code rollback does **not** roll back migrations. If the bad release also
applied a forward migration the old image can't tolerate, you must also handle
the schema — see `docs/runbooks/database-migrations.md` ("Rollback"). Prefer
fixing forward where a migration is involved.

## Verifying the rollback

- `aws ecs describe-services --cluster autotiers-prod --services autotiers-prod-backend`
  shows the new deployment reaching `PRIMARY` / `runningCount == desiredCount`.
- Confirm the running tasks reference the expected image tag:
  `aws ecs describe-tasks ... --query 'tasks[].containers[].image'`.
- Hit the health endpoint and spot-check the behaviour the bad release broke.
