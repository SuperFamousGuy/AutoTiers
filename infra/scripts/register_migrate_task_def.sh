#!/usr/bin/env bash
# register_migrate_task_def.sh — register/update the one-off Alembic migrate
# ECS task definition from source committed in this repo, so a release NEVER
# depends on a human running `terraform apply` locally first (issue #395).
#
# Background: during v3.8-v3.11 every deploy died at "Run database migrations"
# because the `autotiers-prod-migrate` task definition only existed in Terraform
# (infra/migrations.tf) and the apply that would register it was never run. The
# deploy workflow owned the RUN half of migrations but not the REGISTER half.
# This script closes that gap: it (re-)registers the migrate task definition on
# every release, idempotently, before the migration is run.
#
# How it works:
#   1. Discover the backend service's CURRENT task definition (always present —
#      the backend is running) to borrow its execution role, secret ARNs, and
#      log configuration. No new GitHub variables, no dependency on the
#      dedicated migrate log group / role from migrations.tf existing.
#   2. Merge those account-specific values onto the committed migrate recipe
#      (infra/migrate-task-definition.json) via merge_migrate_task_def.py.
#   3. `aws ecs register-task-definition` the result, producing a fresh active
#      revision of the `<cluster>-migrate` family.
#   4. Emit the exact `family:revision` so the caller runs migrations against
#      the def THIS step just registered (not a pre-existing one).
#
# A deliberately-deleted migrate task def is therefore re-created by the next
# deploy: register-task-definition creates the family if it does not exist.
#
# Usage:
#   register_migrate_task_def.sh \
#     --cluster <name> --region <region> --from-service <backend-service> \
#     --image <ecr-repo>:<tag> [--family <family>] [--recipe <path>]
set -euo pipefail

CLUSTER=""
REGION="${AWS_REGION:-us-east-1}"
FROM_SERVICE=""
IMAGE=""
FAMILY=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECIPE="${SCRIPT_DIR}/../migrate-task-definition.json"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --cluster)      CLUSTER="$2"; shift 2 ;;
    --region)       REGION="$2"; shift 2 ;;
    --from-service) FROM_SERVICE="$2"; shift 2 ;;
    --image)        IMAGE="$2"; shift 2 ;;
    --family)       FAMILY="$2"; shift 2 ;;
    --recipe)       RECIPE="$2"; shift 2 ;;
    *) echo "[register-migrate] unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "${CLUSTER}" ] || [ -z "${FROM_SERVICE}" ] || [ -z "${IMAGE}" ]; then
  echo "[register-migrate] ERROR: --cluster, --from-service and --image are required" >&2
  exit 2
fi

# Default the family to the `<cluster>-migrate` convention the run step uses.
if [ -z "${FAMILY}" ]; then
  FAMILY="${CLUSTER}-migrate"
fi

echo "[register-migrate] resolving backend task definition from service '${FROM_SERVICE}'..."
BACKEND_TASK_DEF_ARN=$(aws ecs describe-services \
  --cluster "${CLUSTER}" --services "${FROM_SERVICE}" --region "${REGION}" \
  --query 'services[0].taskDefinition' --output text)

if [ -z "${BACKEND_TASK_DEF_ARN}" ] || [ "${BACKEND_TASK_DEF_ARN}" = "None" ]; then
  echo "[register-migrate] ERROR: could not resolve backend task definition from '${FROM_SERVICE}'" >&2
  exit 1
fi
echo "[register-migrate] backend task definition: ${BACKEND_TASK_DEF_ARN}"

# Build the register-task-definition input by merging the committed recipe with
# the live backend task def. The merge is a pure, unit-tested Python module.
REGISTER_INPUT=$(aws ecs describe-task-definition \
  --task-definition "${BACKEND_TASK_DEF_ARN}" --region "${REGION}" \
  --query 'taskDefinition' --output json \
  | python3 "${SCRIPT_DIR}/merge_migrate_task_def.py" \
      --recipe "${RECIPE}" \
      --family "${FAMILY}" \
      --image "${IMAGE}" \
      --backend-task-def -)

echo "[register-migrate] registering migrate task definition family '${FAMILY}' (image ${IMAGE})..."
REGISTERED_ARN=$(aws ecs register-task-definition \
  --cli-input-json "${REGISTER_INPUT}" \
  --region "${REGION}" \
  --query 'taskDefinition.taskDefinitionArn' --output text)

if [ -z "${REGISTERED_ARN}" ] || [ "${REGISTERED_ARN}" = "None" ]; then
  echo "[register-migrate] ERROR: register-task-definition returned no ARN" >&2
  exit 1
fi

# `family:revision` is the stable handle the run step targets, so it runs the
# exact revision we just registered rather than whatever was previously active.
REGISTERED_REF="${REGISTERED_ARN##*/}"
echo "[register-migrate] registered ${REGISTERED_ARN}"
echo "[register-migrate] task definition reference: ${REGISTERED_REF}"

# Expose the reference to later workflow steps when running under GitHub Actions.
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "task_definition=${REGISTERED_REF}" >> "${GITHUB_OUTPUT}"
fi
