#!/bin/sh
# Rooman Billing API container entrypoint.
#
#   1. Wait until PostgreSQL accepts connections (psycopg, no extra tooling).
#   2. Apply Alembic migrations (skip with RUN_MIGRATIONS=false, e.g. on the
#      scheduler container so only one process migrates).
#   3. exec the container command (gunicorn by default, see Dockerfile CMD).
#
# gunicorn worker count comes from WEB_CONCURRENCY (default 2); -w is appended
# here so the value can be set from the environment while CMD stays overridable.
set -eu

cd /app

echo "[entrypoint] waiting for database (timeout ${DB_WAIT_TIMEOUT:-60}s)..."
python -c '
import os, sys, time
import psycopg
from backend.app.core.config import settings

url = settings.sync_database_url
if url.startswith("sqlite"):
    print("[entrypoint] SQLite configured - nothing to wait for")
    sys.exit(0)

# SQLAlchemy URL -> libpq URL (drop the "+psycopg" driver marker).
dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
deadline = time.monotonic() + float(os.environ.get("DB_WAIT_TIMEOUT", "60"))
attempt = 0
while True:
    attempt += 1
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        print("[entrypoint] database reachable after %d attempt(s)" % attempt)
        break
    except Exception as exc:
        if time.monotonic() >= deadline:
            print("[entrypoint] database not reachable: %s" % exc, file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
'

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] applying migrations: alembic -c backend/alembic.ini upgrade head"
  alembic -c backend/alembic.ini upgrade head
else
  echo "[entrypoint] RUN_MIGRATIONS=${RUN_MIGRATIONS} - skipping migrations"
fi

# Only gunicorn takes the worker flag; other commands (scheduler, one-off python)
# are exec'd untouched.
if [ "${1:-}" = "gunicorn" ]; then
  echo "[entrypoint] starting gunicorn: WEB_CONCURRENCY=${WEB_CONCURRENCY:-2} SCHEDULER_ENABLED=${SCHEDULER_ENABLED:-(default)}"
  exec "$@" -w "${WEB_CONCURRENCY:-2}"
fi

exec "$@"
