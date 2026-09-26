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
# Journal lines are forwarded verbatim to a third-party chat service, so scrub anything
# secret-shaped first (key=value secrets, Authorization/Bearer, GitHub PATs, URL credentials).
last_log="$(journalctl -u "$unit" -n 5 --no-pager -o cat 2>/dev/null | tail -n 5 | tr '\n' ' ' \
    | sed -E \
        -e 's/((password|passwd|secret|token|api[_-]?key|pat|authorization)["'"'"']?[[:space:]]*[:=][[:space:]]*)[^[:space:],;]+/\1[redacted]/Ig' \
        -e 's/(bearer|basic|token) [A-Za-z0-9._~+\/=-]{8,}/\1 [redacted]/Ig' \
        -e 's/(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}/gh_[redacted]/g' \
        -e 's/github_pat_[A-Za-z0-9_]{20,}/github_pat_[redacted]/g' \
        -e 's#(://[^:/@[:space:]]+):[^@[:space:]]+@#\1:[redacted]@#g' \
    | cut -c1-600)"
msg="[rooman-billing @ $(hostname)] systemd unit $unit FAILED. Last log: ${last_log:-n/a}"
echo "$msg" >&2
[ -n "$url" ] || { echo "ALERT_WEBHOOK_URL not set - alert only logged" >&2; exit 0; }
esc=$(printf '%s' "$msg" | sed 's/\/\\/g; s/"/\\"/g')
curl -fsS -m 15 -X POST -H 'Content-Type: application/json' -d "{\"text\": \"${esc}\"}" "$url" >/dev/null
