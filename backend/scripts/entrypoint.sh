#!/usr/bin/env bash
# Container entrypoint: wait for DB, run migrations, optionally seed, then exec the CMD.
#
# Robust against compose-level dependency ordering differences — docker compose's
# depends_on.condition: service_healthy is well-supported, but podman-compose
# historically ignores the condition. The wait loop below makes this entrypoint
# behave identically across Docker, podman compose, and podman-compose.
set -euo pipefail

# Parse host/port out of DATABASE_URL_SYNC (postgresql+psycopg2://user:pass@host:port/db)
DB_HOST=$(python -c "from urllib.parse import urlparse; u=urlparse('${DATABASE_URL_SYNC}'.replace('postgresql+psycopg2','postgresql')); print(u.hostname or 'db')")
DB_PORT=$(python -c "from urllib.parse import urlparse; u=urlparse('${DATABASE_URL_SYNC}'.replace('postgresql+psycopg2','postgresql')); print(u.port or 5432)")

echo "[entrypoint] waiting for postgres at ${DB_HOST}:${DB_PORT}..."
for i in $(seq 1 60); do
  if pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -q; then
    echo "[entrypoint] postgres is ready (after ${i}s)"
    break
  fi
  if [ "${i}" -eq 60 ]; then
    echo "[entrypoint] ERROR: postgres not ready after 60s — giving up"
    exit 1
  fi
  sleep 1
done

# Schema migrations.
#
# RUN_MIGRATIONS gates whether THIS container applies migrations on boot:
#   true  (default) — local docker/podman compose and any single-instance run:
#                     the container migrates itself before serving, so a fresh
#                     dev DB just works.
#   false           — production ECS services (backend + scheduler). There,
#                     migrations are owned by a single dedicated one-off task
#                     (alembic upgrade head) provisioned in Terraform, run once
#                     per deploy BEFORE the services roll. This avoids the
#                     autoscaled backend replicas and the scheduler racing to
#                     run `alembic upgrade head` against the same database, which
#                     can deadlock or error ("relation already exists") because
#                     alembic does not hold a lock across the DDL.
#
# Either way `set -euo pipefail` is in force: if `alembic upgrade head` fails,
# this script exits non-zero and the CMD is never exec'd — a broken migration
# can never partially start a serving container.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] running alembic migrations..."
  alembic upgrade head
else
  echo "[entrypoint] RUN_MIGRATIONS=false — skipping in-container migrations (owned by the dedicated migrate task)."
fi

if [ "${SEED_DEV_DATA:-false}" = "true" ]; then
  echo "[entrypoint] seeding dev data (idempotent)..."
  python -m scripts.seed_dev
else
  echo "[entrypoint] SEED_DEV_DATA=false — skipping seed."
fi

echo "[entrypoint] starting: $*"
exec "$@"
