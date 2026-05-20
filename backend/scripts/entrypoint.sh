#!/usr/bin/env bash
# Container entrypoint: wait for DB, run migrations, optionally seed, then exec the CMD.
set -euo pipefail

echo "[entrypoint] running alembic migrations..."
alembic upgrade head

if [ "${SEED_DEV_DATA:-false}" = "true" ]; then
  echo "[entrypoint] seeding dev data (idempotent)..."
  python -m scripts.seed_dev
else
  echo "[entrypoint] SEED_DEV_DATA=false — skipping seed."
fi

echo "[entrypoint] starting: $*"
exec "$@"
