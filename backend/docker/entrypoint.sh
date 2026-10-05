#!/bin/sh
# Rooman Billing API container entrypoint.
#
#   1. Wait until PostgreSQL accepts connections (psycopg, no extra tooling) with the
#      runtime credentials - and, when migrating, with the migration credentials too.
#      TLS options (POSTGRES_SSLMODE / SSLROOTCERT / SSLCERT / SSLKEY) apply to both.
#   2. Apply Alembic migrations (skip with RUN_MIGRATIONS=false, e.g. on the
#      scheduler container so only one process migrates). Alembic connects as the
#      owner role (MIGRATION_DATABASE_URL or MIGRATION_POSTGRES_USER/PASSWORD) when
#      set, else with the runtime credentials (docs/database-security.md).
#   3. Drop the migration credentials from the environment, then exec the container
#      command (gunicorn by default, see Dockerfile CMD) - the app never sees them.
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

from backend.app.core.redaction import redact_text

targets = [("runtime", settings.sync_database_url)]
if os.environ.get("RUN_MIGRATIONS", "true") == "true" and settings.migration_database_url != settings.sync_database_url:
    targets.append(("migration", settings.migration_database_url))
if targets[0][1].startswith("sqlite"):
    print("[entrypoint] SQLite configured - nothing to wait for")
    sys.exit(0)

deadline = time.monotonic() + float(os.environ.get("DB_WAIT_TIMEOUT", "60"))
for label, url in targets:
    # SQLAlchemy URL -> libpq URL (drop the "+psycopg" driver marker).
    dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
    attempt = 0
    while True:
        attempt += 1
        try:
            with psycopg.connect(dsn, connect_timeout=3, **settings.db_connect_args(url)) as conn:
                conn.execute("SELECT 1")
            print("[entrypoint] database reachable as %s role after %d attempt(s)" % (label, attempt))
            break
        except Exception as exc:
            if time.monotonic() >= deadline:
                print("[entrypoint] database not reachable as %s role: %s" % (label, redact_text(str(exc))), file=sys.stderr)
                sys.exit(1)
            time.sleep(2)
'

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] applying migrations: alembic -c backend/alembic.ini upgrade head"
  alembic -c backend/alembic.ini upgrade head
else
  echo "[entrypoint] RUN_MIGRATIONS=${RUN_MIGRATIONS} - skipping migrations"
fi

# The owner/migration credentials are only needed for the step above.
unset MIGRATION_DATABASE_URL MIGRATION_POSTGRES_USER MIGRATION_POSTGRES_PASSWORD
# With a separate runtime role, POSTGRES_PASSWORD is the owner's password - drop it too.
if [ -n "${APP_POSTGRES_USER:-}" ]; then
  unset POSTGRES_PASSWORD
fi

# Only gunicorn takes the worker flag; other commands (scheduler, one-off python)
# are exec'd untouched.
if [ "${1:-}" = "gunicorn" ]; then
  echo "[entrypoint] starting gunicorn: WEB_CONCURRENCY=${WEB_CONCURRENCY:-2} SCHEDULER_ENABLED=${SCHEDULER_ENABLED:-(default)}"
  exec "$@" -w "${WEB_CONCURRENCY:-2}"
fi

exec "$@"
