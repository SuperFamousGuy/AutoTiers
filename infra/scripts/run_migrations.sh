#!/usr/bin/env bash
# run_migrations.sh — run the one-off Alembic migration task on ECS and block
# until it succeeds.
#
# This is the single migration authority for the deployed environment. It is
# called from two places:
#   1. Terraform  (null_resource.run_migrations local-exec) on every apply that
#      changes the image tag or the migration files — see infra/migrations.tf.
#   2. The deploy workflow (.github/workflows/deploy.yml) on every release,
#      after the new image is pushed and BEFORE the backend/scheduler services
#      are force-redeployed.
#
# It runs the migrate task definition with `aws ecs run-task`, waits for the
# task to stop, and exits non-zero if the migration container's exit code is
# non-zero (or the task failed to start). That non-zero exit fails the calling
# `terraform apply` / deploy job, so a broken migration blocks the deploy
# instead of letting a half-migrated schema reach serving traffic.
#
# Network configuration (subnets + security group) can be supplied explicitly
# (Terraform knows them at apply time) or discovered from an existing ECS
# service (the deploy workflow reuses the backend service's awsvpc config so no
# extra GitHub variables are needed).
#
# Usage:
#   run_migrations.sh \
#     --cluster <name> --task-definition <family> --region <region> \
#     ( --subnets <a,b> --security-groups <sg> | --from-service <service-name> )
set -euo pipefail

CLUSTER=""
TASK_DEFINITION=""
REGION="${AWS_REGION:-us-east-1}"
SUBNETS=""
SECURITY_GROUPS=""
FROM_SERVICE=""
CONTAINER_NAME="migrate"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --cluster)          CLUSTER="$2"; shift 2 ;;
    --task-definition)  TASK_DEFINITION="$2"; shift 2 ;;
    --region)           REGION="$2"; shift 2 ;;
    --subnets)          SUBNETS="$2"; shift 2 ;;
    --security-groups)  SECURITY_GROUPS="$2"; shift 2 ;;
    --from-service)     FROM_SERVICE="$2"; shift 2 ;;
    --container-name)   CONTAINER_NAME="$2"; shift 2 ;;
    *) echo "[migrate] unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "${CLUSTER}" ] || [ -z "${TASK_DEFINITION}" ]; then
  echo "[migrate] ERROR: --cluster and --task-definition are required" >&2
  exit 2
fi

# Resolve subnets + security group from an existing service when not given.
if [ -z "${SUBNETS}" ] || [ -z "${SECURITY_GROUPS}" ]; then
  if [ -z "${FROM_SERVICE}" ]; then
    echo "[migrate] ERROR: provide --subnets and --security-groups, or --from-service" >&2
    exit 2
  fi
  echo "[migrate] discovering network config from service '${FROM_SERVICE}'..."
  SUBNETS=$(aws ecs describe-services \
    --cluster "${CLUSTER}" --services "${FROM_SERVICE}" --region "${REGION}" \
    --query 'services[0].networkConfiguration.awsvpcConfiguration.subnets' \
    --output text | tr '\t' ',')
  SECURITY_GROUPS=$(aws ecs describe-services \
    --cluster "${CLUSTER}" --services "${FROM_SERVICE}" --region "${REGION}" \
    --query 'services[0].networkConfiguration.awsvpcConfiguration.securityGroups' \
    --output text | tr '\t' ',')
fi

# `describe-services --output text` prints the literal string "None" (not an
# empty string) when the service is missing or has no awsvpc config, so guard
# against both empty and "None" before building the network config.
if [ -z "${SUBNETS}" ] || [ "${SUBNETS}" = "None" ] \
  || [ -z "${SECURITY_GROUPS}" ] || [ "${SECURITY_GROUPS}" = "None" ]; then
  echo "[migrate] ERROR: could not resolve subnets/security groups" >&2
  exit 2
fi

NETWORK_CONFIG="awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SECURITY_GROUPS}],assignPublicIp=DISABLED}"

# Preflight: confirm the task-definition family resolves to an ACTIVE revision
# before calling run-task. When the family was never registered, `aws ecs
# run-task` fails with an opaque "ClientException ... TaskDefinition not found"
# that gives no hint at the real cause: infra/migrations.tf has been merged to
# the repo but not yet `terraform apply`-ed to this account/region. That exact
# gap silently failed the deploy workflow's migrations step on every release
# from v3.8 through v3.11 until the task def was applied out-of-band. Catch it
# here and print the remediation instead of the bare AWS error.
echo "[migrate] verifying task definition '${TASK_DEFINITION}' is registered..."
if ! DESCRIBE_ERR=$(aws ecs describe-task-definition \
  --task-definition "${TASK_DEFINITION}" --region "${REGION}" \
  --query 'taskDefinition.taskDefinitionArn' --output text 2>&1); then
  # Surface the underlying AWS error so a non-"not found" failure (e.g. an IAM
  # AccessDenied or a throttle) isn't masked as a missing task definition.
  echo "[migrate] ERROR: could not resolve task definition '${TASK_DEFINITION}' in ${REGION}." >&2
  [ -n "${DESCRIBE_ERR}" ] && echo "[migrate]   aws said: ${DESCRIBE_ERR}" >&2
  echo "[migrate]   If this is 'TaskDefinition not found', the family is defined in" >&2
  echo "[migrate]   infra/migrations.tf but has not been applied to AWS. From the repo root:" >&2
  echo "[migrate]     (cd infra && terraform apply)" >&2
  echo "[migrate]   then confirm it resolves:" >&2
  echo "[migrate]     aws ecs describe-task-definition --task-definition ${TASK_DEFINITION} --region ${REGION}" >&2
  exit 1
fi

echo "[migrate] running task ${TASK_DEFINITION} on cluster ${CLUSTER} (${REGION})..."
# Capture the full response rather than projecting out taskArn with --query: the
# failures[] array (which explains why a task didn't start) lives alongside
# tasks[] and would otherwise be discarded, leaving nothing to diagnose with.
RUN_TASK_OUTPUT=$(aws ecs run-task \
  --cluster "${CLUSTER}" \
  --task-definition "${TASK_DEFINITION}" \
  --launch-type FARGATE \
  --region "${REGION}" \
  --network-configuration "${NETWORK_CONFIG}" \
  --started-by "migrate-bootstrap" \
  --output json)

TASK_ARN=$(printf '%s' "${RUN_TASK_OUTPUT}" \
  | python3 -c 'import json,sys; tasks=json.load(sys.stdin).get("tasks") or []; print(tasks[0]["taskArn"] if tasks else "")')

if [ -z "${TASK_ARN}" ] || [ "${TASK_ARN}" = "None" ]; then
  echo "[migrate] ERROR: run-task did not start a task. Full run-task response (including failures) below:" >&2
  printf '%s\n' "${RUN_TASK_OUTPUT}" >&2
  exit 1
fi
echo "[migrate] task started: ${TASK_ARN}"

echo "[migrate] waiting for task to stop..."
aws ecs wait tasks-stopped \
  --cluster "${CLUSTER}" --tasks "${TASK_ARN}" --region "${REGION}"

# A stopped task can still mean failure — inspect the migrate container's exit
# code and the stop reason rather than trusting "stopped" to mean "succeeded".
EXIT_CODE=$(aws ecs describe-tasks \
  --cluster "${CLUSTER}" --tasks "${TASK_ARN}" --region "${REGION}" \
  --query "tasks[0].containers[?name=='${CONTAINER_NAME}'].exitCode | [0]" \
  --output text)
STOP_REASON=$(aws ecs describe-tasks \
  --cluster "${CLUSTER}" --tasks "${TASK_ARN}" --region "${REGION}" \
  --query 'tasks[0].stoppedReason' \
  --output text)

echo "[migrate] task stopped (exitCode=${EXIT_CODE}, reason=${STOP_REASON})"

if [ "${EXIT_CODE}" != "0" ]; then
  echo "[migrate] ERROR: migration task failed — blocking deploy." >&2
  exit 1
fi

echo "[migrate] migrations applied successfully."
