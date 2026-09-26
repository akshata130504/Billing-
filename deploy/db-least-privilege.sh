#!/bin/sh
# One-time (re-runnable) setup of the least-privilege runtime DB role for the compose stack.
#
#   1. Add to .env.production:
#        APP_POSTGRES_USER=rooman_app
#        APP_POSTGRES_PASSWORD=<openssl rand -base64 24 | tr -d '/+='>
#   2. sh deploy/db-least-privilege.sh          # creates/updates the role + grants
#   3. docker compose --env-file .env.production -f docker-compose.prod.yml up -d backend scheduler
#
# Runs deploy/sql/least_privilege.sql inside the `db` container as POSTGRES_USER (the
# bootstrap superuser, which owns the schema and keeps running migrations). The password
# travels via the environment of `docker compose exec` (never on a command line) and is
# never printed. Idempotent: re-run after restoring a dump or to rotate the password.
# See docs/database-security.md.
set -eu
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

env_get() {
    eval "cur=\${$1:-}"
    if [ -n "$cur" ]; then
        printf '%s' "$cur"
        return
    fi
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -n1 | cut -d '=' -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

OWNER="$(env_get POSTGRES_USER)"
DB="$(env_get POSTGRES_DB)"
RB_APP_ROLE="$(env_get APP_POSTGRES_USER)"
RB_APP_PASSWORD="$(env_get APP_POSTGRES_PASSWORD)"

[ -n "$OWNER" ] && [ -n "$DB" ] || { echo "POSTGRES_USER / POSTGRES_DB missing in $ENV_FILE" >&2; exit 1; }
[ -n "$RB_APP_ROLE" ] || { echo "APP_POSTGRES_USER is not set in $ENV_FILE" >&2; exit 1; }
[ -n "$RB_APP_PASSWORD" ] || { echo "APP_POSTGRES_PASSWORD is not set in $ENV_FILE" >&2; exit 1; }
[ "$RB_APP_ROLE" != "$OWNER" ] || { echo "APP_POSTGRES_USER must differ from POSTGRES_USER" >&2; exit 1; }
[ "${#RB_APP_PASSWORD}" -ge 16 ] || { echo "APP_POSTGRES_PASSWORD must be at least 16 characters" >&2; exit 1; }
export RB_APP_ROLE RB_APP_PASSWORD

echo "[least-privilege] configuring role '$RB_APP_ROLE' in database '$DB' (owner '$OWNER')"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T \
    -e RB_APP_ROLE -e RB_APP_PASSWORD -e RB_OWNER_ROLE="$OWNER" \
    db psql -X -v ON_ERROR_STOP=1 -U "$OWNER" -d "$DB" -f - < deploy/sql/least_privilege.sql
echo "[least-privilege] done. Restart backend + scheduler so they connect as '$RB_APP_ROLE'."
