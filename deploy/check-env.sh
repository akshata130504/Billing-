#!/bin/sh
# Pre-deploy check: reports which production settings are SET / MISSING in .env.production.
# Prints variable NAMES only - never values. Exit code 1 if a required variable is missing.
#
#   sh deploy/check-env.sh                 # checks ./.env.production
#   sh deploy/check-env.sh /path/to/.env.production
#
# Run it on the server BEFORE deploying a release that removed hardcoded fallbacks (e.g. the
# SMTP defaults added by b858418): email only keeps working if SMTP_* is set here.
set -eu
ENV_FILE="${1:-.env.production}"
[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found"; exit 1; }

value_set() {
    # true when KEY=<non-empty> exists (ignores comments and surrounding quotes/spaces)
    line=$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$ENV_FILE" | tail -n 1 || true)
    val=$(printf '%s' "${line#*=}" | sed -e 's/^[[:space:]"'"'"']*//' -e 's/[[:space:]"'"'"']*$//')
    [ -n "$line" ] && [ -n "$val" ]
}

missing_required=0
raw() {  # value of KEY without surrounding quotes/spaces - used for format checks only, never printed
    line=$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$ENV_FILE" | tail -n 1 || true)
    printf '%s' "${line#*=}" | sed -e 's/^[[:space:]"'"'"']*//' -e 's/[[:space:]"'"'"']*$//'
}
rule() {  # rule <REQUIRED|optional> <description> <shell test...>
    level=$1; desc=$2; shift 2
    if "$@"; then
        printf '  %-50s PASS\n' "$desc"
    else
        printf '  %-50s FAIL (%s)\n' "$desc" "$level"
        if [ "$level" = "REQUIRED" ]; then missing_required=1; fi
    fi
}
check() {  # check <REQUIRED|optional> KEY...
    level=$1; shift
    for key in "$@"; do
        if value_set "$key"; then
            printf '  %-32s SET\n' "$key"
        else
            printf '  %-32s MISSING (%s)\n' "$key" "$level"
            if [ "$level" = "REQUIRED" ]; then missing_required=1; fi
        fi
    done
}

echo "== core (REQUIRED)"
check REQUIRED SECRET_KEY FRONTEND_URL ALLOWED_ORIGINS POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB
echo "== email - signup codes, invitations, password resets (REQUIRED)"
check REQUIRED SMTP_HOST SMTP_PORT SMTP_USERNAME SMTP_PASSWORD EMAIL_FROM_ADDRESS
echo "== format checks (values are inspected, never printed)"
rule REQUIRED "FRONTEND_URL is https://" sh -c 'case "$1" in https://*) exit 0;; *) exit 1;; esac' _ "$(raw FRONTEND_URL)"
rule REQUIRED "ALLOWED_ORIGINS https-only, no localhost, no *" sh -c \
    'o="$1"; [ -n "$o" ] || exit 1; case "$o" in *localhost*|*127.0.0.1*|*"*"*|*http://*) exit 1;; esac' _ "$(raw ALLOWED_ORIGINS)"
rule REQUIRED "POSTGRES_PASSWORD is not the default" sh -c '[ -n "$1" ] && [ "$1" != "postgres" ]' _ "$(raw POSTGRES_PASSWORD)"
rule REQUIRED "SECRET_KEY is at least 32 characters" sh -c '[ "${#1}" -ge 32 ]' _ "$(raw SECRET_KEY)"
rule REQUIRED "DEBUG is not true" sh -c 'case "$1" in [Tt]rue|1|[Yy]es) exit 1;; *) exit 0;; esac' _ "$(raw DEBUG)"
echo "== payments (required before taking online payments)"
check optional RAZORPAY_KEY_ID RAZORPAY_KEY_SECRET RAZORPAY_WEBHOOK_SECRET
if value_set RAZORPAY_KEY_ID; then
    rule optional "Razorpay webhook secret set with the API keys" value_set RAZORPAY_WEBHOOK_SECRET
    rule optional "Razorpay key is LIVE mode (rzp_live_)" sh -c 'case "$1" in rzp_live_*) exit 0;; *) exit 1;; esac' _ "$(raw RAZORPAY_KEY_ID)"
fi
echo "== operations (strongly recommended)"
check optional ALERT_WEBHOOK_URL GITHUB_PAT
echo "== backups (offsite copy)"
check optional OFFSITE_BACKUP_REMOTE
if value_set OFFSITE_BACKUP_REMOTE; then
    # an offsite remote without credentials makes every nightly backup fail (OFFSITE_REQUIRED=true)
    check REQUIRED OFFSITE_S3_ACCESS_KEY_ID OFFSITE_S3_SECRET_ACCESS_KEY
    check optional OFFSITE_S3_PROVIDER OFFSITE_S3_REGION OFFSITE_S3_ENDPOINT OFFSITE_RETENTION_DAYS
fi
echo "== optional"
check optional SENTRY_DSN GEMINI_API_KEY APP_POSTGRES_USER APP_POSTGRES_PASSWORD ENCRYPTION_KEYS POSTGRES_SSLMODE ALLOWED_HOSTS
echo "== not checkable here"
echo "  Support email on the Help page = GitHub repository variable SUPPORT_EMAIL (baked into the web image)."

if [ "$missing_required" -ne 0 ]; then
    echo "RESULT: FAIL - a REQUIRED setting is missing or invalid; do not deploy until it is fixed."
    exit 1
fi
echo "RESULT: PASS - all required settings are present and valid."
