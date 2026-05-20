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
