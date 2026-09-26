#!/bin/sh
# Posts a failure notice to ALERT_WEBHOOK_URL (from the environment or .env.production).
# Used by rooman-billing-alert@.service (OnFailure= of rooman-billing-poll.service):
#   alert.sh <failed-unit-name>
# The payload is {"text": "..."} - accepted by Slack / Mattermost / Teams (workflow) /
# Discord (append /slack to a Discord webhook URL) incoming webhooks.
set -u
cd "$(dirname "$0")/.." 2>/dev/null || true
unit="${1:-unknown-unit}"
url="${ALERT_WEBHOOK_URL:-$(grep -E '^ALERT_WEBHOOK_URL=' .env.production 2>/dev/null | head -n1 | cut -d '=' -f2- | sed -e 's/^"//' -e 's/"$//')}"
last_log="$(journalctl -u "$unit" -n 5 --no-pager -o cat 2>/dev/null | tail -n 5 | tr '\n' ' ' | cut -c1-600)"
msg="[rooman-billing @ $(hostname)] systemd unit $unit FAILED. Last log: ${last_log:-n/a}"
echo "$msg" >&2
[ -n "$url" ] || { echo "ALERT_WEBHOOK_URL not set - alert only logged" >&2; exit 0; }
esc=$(printf '%s' "$msg" | sed 's/\/\\/g; s/"/\\"/g')
curl -fsS -m 15 -X POST -H 'Content-Type: application/json' -d "{\"text\": \"${esc}\"}" "$url" >/dev/null
