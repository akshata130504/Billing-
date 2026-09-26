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
echo "== payments (required before taking online payments)"
check optional RAZORPAY_KEY_ID RAZORPAY_KEY_SECRET RAZORPAY_WEBHOOK_SECRET
echo "== operations (strongly recommended)"
check optional ALERT_WEBHOOK_URL OFFSITE_BACKUP_REMOTE GITHUB_PAT
echo "== optional"
check optional SENTRY_DSN GEMINI_API_KEY APP_POSTGRES_USER APP_POSTGRES_PASSWORD ENCRYPTION_KEYS

if [ "$missing_required" -ne 0 ]; then
    echo "RESULT: a REQUIRED variable is missing - do not deploy until it is set."
    exit 1
fi
echo "RESULT: all required variables are set."
