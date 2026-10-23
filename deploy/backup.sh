#!/bin/sh
# Rooman Billing - scheduled backup job (runs inside the `backup` service of
# docker-compose.prod.yml, image postgres:16-alpine; rclone + curl are installed at
# container start).
#
# Each run:
#   1. pg_dump (custom format) of the application database
#   2. tar.gz of the uploads volume (logos, avatars, attachments) and of the private
#      uploads volume (expense receipts), both mounted read-only
#   3. local retention (BACKUP_RETENTION_DAYS)
#   4. optional offsite copy with rclone (OFFSITE_BACKUP_REMOTE) + offsite retention
#   5. on success: writes $BACKUP_DIR/last_success (the container healthcheck reads it)
#      on failure: POSTs to ALERT_WEBHOOK_URL (if set) and exits non-zero
#
# Environment (all passed explicitly by docker-compose.prod.yml - no env_file):
#   POSTGRES_SERVER POSTGRES_PORT POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB
#   BACKUP_DIR (default /var/backups/rooman)  UPLOADS_DIR (default /uploads)
#   PRIVATE_UPLOADS_DIR (default /private_uploads)
#   BACKUP_RETENTION_DAYS (default 30)
#   OFFSITE_BACKUP_REMOTE   rclone destination, e.g. "offsite:my-bucket/rooman-billing".
#                           The "offsite" remote is configured from RCLONE_CONFIG_OFFSITE_*
#                           variables (see .env.production.example). Empty = no offsite copy.
#   OFFSITE_RETENTION_DAYS  delete offsite files older than N days (empty/0 = keep forever;
#                           prefer bucket lifecycle rules / object lock where available)
#   OFFSITE_REQUIRED        "true" (default when OFFSITE_BACKUP_REMOTE is set): an offsite
#                           upload failure fails the job and alerts
#   ALERT_WEBHOOK_URL       optional; receives {"text": "..."} JSON (Slack/Teams/Discord-
#                           compatible "incoming webhook" shape)
set -eu

BACKUP_DIR="${BACKUP_DIR:-/var/backups/rooman}"
UPLOADS_DIR="${UPLOADS_DIR:-/uploads}"
PRIVATE_UPLOADS_DIR="${PRIVATE_UPLOADS_DIR:-/private_uploads}"
RETENTION="${BACKUP_RETENTION_DAYS:-30}"
HOST_LABEL="${BACKUP_HOST_LABEL:-$(hostname)}"

log() { echo "[$(date -Iseconds)] [backup] $*"; }

alert() {
    msg="$1"
    log "ALERT: $msg" >&2
    if [ -n "${ALERT_WEBHOOK_URL:-}" ] && command -v curl >/dev/null 2>&1; then
        # Minimal JSON escaping of the message (quotes and backslashes).
        esc=$(printf '%s' "$msg" | sed 's/\\/\\\\/g; s/"/\\"/g')
        curl -fsS -m 15 -X POST -H 'Content-Type: application/json' \
            -d "{\"text\": \"[rooman-billing backup @ ${HOST_LABEL}] ${esc}\"}" \
            "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 || log "WARNING: alert webhook POST failed" >&2
    fi
}

fail() {
    alert "$1"
    exit 1
}

for v in POSTGRES_USER POSTGRES_DB; do
    eval "val=\${$v:-}"
    [ -n "$val" ] || fail "$v is not set in the backup container environment"
done

mkdir -p "$BACKUP_DIR" || fail "cannot create $BACKUP_DIR"
DATE=$(date +%Y%m%d_%H%M%S)
DB_FILE="$BACKUP_DIR/rooman_${DATE}.dump"
UPLOADS_FILE="$BACKUP_DIR/uploads_${DATE}.tar.gz"
PRIVATE_UPLOADS_FILE="$BACKUP_DIR/private_uploads_${DATE}.tar.gz"

# ---- 1. database ------------------------------------------------------------------
log "Starting database backup to $DB_FILE"
export PGPASSWORD="${POSTGRES_PASSWORD:-}"
if ! pg_dump -h "${POSTGRES_SERVER:-db}" -p "${POSTGRES_PORT:-5432}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        --no-owner --format=custom -f "$DB_FILE.partial"; then
    rm -f "$DB_FILE.partial"
    fail "pg_dump failed for database ${POSTGRES_DB:-?}"
fi
# Sanity check: a custom-format dump must be listable.
if ! pg_restore --list "$DB_FILE.partial" >/dev/null 2>&1; then
    rm -f "$DB_FILE.partial"
    fail "pg_dump produced an unreadable archive"
fi
mv "$DB_FILE.partial" "$DB_FILE"
log "Database backup OK: $(ls -lh "$DB_FILE" | awk '{print $5}')"

# ---- 2. uploads -------------------------------------------------------------------
# archive_dir <dir> <tarball> <label>: prints the tarball path, or nothing when <dir> is
# not mounted (the caller then leaves it out of the offsite copy).
archive_dir() {
    if [ -d "$1" ]; then
        log "Archiving $3 from $1 to $2" >&2
        if ! tar -czf "$2.partial" -C "$1" .; then
            rm -f "$2.partial"
            fail "tar of $3 volume failed"
        fi
        mv "$2.partial" "$2"
        log "$3 backup OK: $(ls -lh "$2" | awk '{print $5}')" >&2
        printf '%s' "$2"
    else
        log "WARNING: $1 not mounted - skipping $3 archive" >&2
    fi
}
UPLOADS_FILE="$(archive_dir "$UPLOADS_DIR" "$UPLOADS_FILE" uploads)"
PRIVATE_UPLOADS_FILE="$(archive_dir "$PRIVATE_UPLOADS_DIR" "$PRIVATE_UPLOADS_FILE" "private uploads")"

# ---- 3. local retention -------------------------------------------------------------
find "$BACKUP_DIR" -maxdepth 1 \( -name 'rooman_*.dump' -o -name 'uploads_*.tar.gz' -o -name 'private_uploads_*.tar.gz' \) \
    -mtime +"$RETENTION" -delete
log "Local retention applied (${RETENTION} days)."

# ---- 4. offsite ------------------------------------------------------------------
if [ -n "${OFFSITE_BACKUP_REMOTE:-}" ]; then
    required="${OFFSITE_REQUIRED:-true}"
    if ! command -v rclone >/dev/null 2>&1; then
        msg="OFFSITE_BACKUP_REMOTE is set but rclone is not installed in the backup container"
        if [ "$required" = "true" ]; then fail "$msg"; else alert "$msg"; fi
    else
        remote="${OFFSITE_BACKUP_REMOTE%/}"
        offsite_ok=1
        for f in "$DB_FILE" $UPLOADS_FILE $PRIVATE_UPLOADS_FILE; do
            log "Uploading $(basename "$f") to $remote/"
            if ! rclone copy --retries 3 --low-level-retries 10 "$f" "$remote/"; then
                offsite_ok=0
            fi
        done
        if [ "$offsite_ok" -ne 1 ]; then
            msg="offsite upload to $remote failed (local copy kept in $BACKUP_DIR)"
            if [ "$required" = "true" ]; then fail "$msg"; else alert "$msg"; fi
        else
            log "Offsite upload OK."
            if [ -n "${OFFSITE_RETENTION_DAYS:-}" ] && [ "${OFFSITE_RETENTION_DAYS}" != "0" ]; then
                rclone delete --min-age "${OFFSITE_RETENTION_DAYS}d" \
                    --include 'rooman_*.dump' --include 'uploads_*.tar.gz' --include 'private_uploads_*.tar.gz' "$remote/" \
                    || alert "offsite retention cleanup on $remote failed (backups are still uploaded)"
            fi
        fi
    fi
else
    log "OFFSITE_BACKUP_REMOTE not set - backups exist ONLY on this host." >&2
fi

# ---- 5. success marker -----------------------------------------------------------
date -Iseconds > "$BACKUP_DIR/last_success"
log "Backup run complete."
