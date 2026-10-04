#!/bin/sh
# Polls GHCR for a newer production release and rolls it out, with a pre-deploy
# database backup and automatic rollback when the new release does not become ready.
#
# This runs ON the production server itself (see rooman-billing-poll.timer), pulling
# images that .github/workflows/deploy.yml built and pushed to GHCR after CI passed on
# main. The server is behind a private/LAN network with no inbound path from GitHub's
# hosted runners, so it pulls on its own schedule instead of GitHub pushing into it.
#
# How a release is identified
#   deploy.yml pushes <image>:<git-sha> and moves <image>:latest to it, and stamps the
#   image with the label org.opencontainers.image.revision=<git-sha>. This script pulls
#   api:latest only to READ that label, then deploys the immutable tag IMAGE_TAG=<sha>
#   and fetches docker-compose.prod.yml / deploy/backup.sh / this script from the repo
#   AT THAT SAME SHA - never from the tip of main, which may not have passed CI.
#
# Flow per run (nothing happens when the release SHA equals .deploy/deployed_sha):
#   1. resolve target SHA from api:latest's revision label
#   2. save current compose file + tag the running images as :previous
#   3. sync orchestration files at the target SHA (needs GITHUB_PAT)
#   3b. preflight: deploy/check-env.sh on .env.production (names only, never values). A missing
#      REQUIRED setting aborts BEFORE anything is pulled or restarted (current release keeps running).
#   4. pull backend + frontend images at IMAGE_TAG=<sha> (frontend = the one website: tenant app
#      at /admin and platform / Super Admin console at /superadmin)
#   5. pg_dump pre-deploy backup to ./backups/predeploy/ (abort deploy if it fails)
#   6. docker compose up -d with IMAGE_TAG=<sha>; poll READINESS_URL (backend, runs migrations)
#   7. ready -> record .deploy/deployed_sha.  not ready -> redeploy :previous with the
#      previous compose file, record .deploy/failed_sha (so it is not retried every
#      2 minutes), alert ALERT_WEBHOOK_URL, exit 1.
#
# Migrations are forward-only: the new backend container runs `alembic upgrade head`
# on start, and the rollback only swaps the application image back. That is safe as
# long as migrations are backward compatible (expand/contract). If a migration broke
# the old code, restore the pre-deploy dump - see docs/operations.md "Rollback".
#
# One-time setup on this server, before the first run:
#   docker login ghcr.io -u <your-github-username>
#   (password: a GitHub PAT with the `read:packages` scope)
# Recommended: GITHUB_PAT=<fine-grained PAT, this repo, Contents: Read-only> in
# .env.production so orchestration files follow the release. Without it only images
# are updated and a warning is logged.
#
# Settings (read from the environment first, then .env.production):
#   READINESS_URL      default derived from FRONTEND_BIND, e.g. http://127.0.0.1:80/api/v1/health/ready
#   ALERT_WEBHOOK_URL  optional; receives {"text": "..."} on rollback / failure
#   READINESS_TIMEOUT  seconds to wait for readiness (default 180)
#   PREDEPLOY_BACKUP_KEEP  number of pre-deploy dumps kept (default 10)
#   GITHUB_REPO        default rooman-itsd/Rooman-Billing
#   API_IMAGE / WEB_IMAGE  default ghcr.io/rooman-itsd/rooman-billing-{api,web}
#
# Expected to run with its working directory set to the directory that holds
# docker-compose.prod.yml and .env.production (normally /opt/rooman-billing).
set -eu

ENV_FILE=".env.production"
COMPOSE_FILE="docker-compose.prod.yml"
STATE_DIR=".deploy"
LOG_PREFIX="[deploy-poll $(date -Iseconds)]"

log() { echo "$LOG_PREFIX $*"; }
err() { echo "$LOG_PREFIX $*" >&2; }

# Value from the environment, else from .env.production (first match, quotes stripped).
env_get() {
    eval "cur=\${$1:-}"
    if [ -n "$cur" ]; then
        printf '%s' "$cur"
        return
    fi
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -n1 | cut -d '=' -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

GITHUB_PAT="$(env_get GITHUB_PAT)"
GITHUB_REPO="$(env_get GITHUB_REPO)"; GITHUB_REPO="${GITHUB_REPO:-rooman-itsd/Rooman-Billing}"
API_IMAGE="$(env_get API_IMAGE)"; API_IMAGE="${API_IMAGE:-ghcr.io/rooman-itsd/rooman-billing-api}"
WEB_IMAGE="$(env_get WEB_IMAGE)"; WEB_IMAGE="${WEB_IMAGE:-ghcr.io/rooman-itsd/rooman-billing-web}"
ALERT_WEBHOOK_URL="$(env_get ALERT_WEBHOOK_URL)"
READINESS_TIMEOUT="$(env_get READINESS_TIMEOUT)"; READINESS_TIMEOUT="${READINESS_TIMEOUT:-180}"
PREDEPLOY_BACKUP_KEEP="$(env_get PREDEPLOY_BACKUP_KEEP)"; PREDEPLOY_BACKUP_KEEP="${PREDEPLOY_BACKUP_KEEP:-10}"
READINESS_URL="$(env_get READINESS_URL)"
if [ -z "$READINESS_URL" ]; then
    bind="$(env_get FRONTEND_BIND)"; bind="${bind:-80}"
    case "$bind" in
        *:*) READINESS_URL="http://${bind}/api/v1/health/ready" ;;
        *)   READINESS_URL="http://127.0.0.1:${bind}/api/v1/health/ready" ;;
    esac
fi

alert() {
    err "ALERT: $1"
    [ -n "$ALERT_WEBHOOK_URL" ] || return 0
    esc=$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')
    curl -fsS -m 15 -X POST -H 'Content-Type: application/json' \
        -d "{\"text\": \"[rooman-billing deploy @ $(hostname)] ${esc}\"}" \
        "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 || err "WARNING: alert webhook POST failed"
}

# compose with an explicit image tag and (optionally) a different compose file
compose_tag() {
    tag="$1"; file="$2"; shift 2
    IMAGE_TAG="$tag" docker compose --env-file "$ENV_FILE" -f "$file" "$@"
}

mkdir -p "$STATE_DIR"

# --- 1. Resolve the release to deploy -------------------------------------------------
log "Checking $API_IMAGE:latest for a new release..."
if ! docker pull -q "$API_IMAGE:latest" >/dev/null; then
    err "ERROR: could not pull $API_IMAGE:latest (registry login expired? network?)"
    exit 1
fi
TARGET_SHA="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$API_IMAGE:latest" 2>/dev/null || true)"
case "$TARGET_SHA" in
    ''|'<no value>')
        err "ERROR: $API_IMAGE:latest has no org.opencontainers.image.revision label; refusing to deploy an unidentified image."
        exit 1 ;;
esac

DEPLOYED_SHA="$(cat "$STATE_DIR/deployed_sha" 2>/dev/null || true)"
FAILED_SHA="$(cat "$STATE_DIR/failed_sha" 2>/dev/null || true)"

if [ "$TARGET_SHA" = "$DEPLOYED_SHA" ]; then
    # Keep containers converged (e.g. after a manual stop) without a new release.
    compose_tag "$TARGET_SHA" "$COMPOSE_FILE" up -d --remove-orphans --no-build >/dev/null 2>&1 || true
    log "Up to date at $TARGET_SHA."
    exit 0
fi
if [ "$TARGET_SHA" = "$FAILED_SHA" ]; then
    log "Release $TARGET_SHA previously failed readiness and was rolled back - skipping. Delete $STATE_DIR/failed_sha to retry."
    exit 0
fi

log "New release $TARGET_SHA (currently deployed: ${DEPLOYED_SHA:-unknown})."

# --- 2. Remember what is running now, for rollback ----------------------------------------
PREV_AVAILABLE=0
backend_cid="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps -q backend 2>/dev/null || true)"
frontend_cid="$(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps -q frontend 2>/dev/null || true)"
if [ -n "$backend_cid" ] && [ -n "$frontend_cid" ]; then
    prev_api_img="$(docker inspect --format '{{.Image}}' "$backend_cid")"
    prev_web_img="$(docker inspect --format '{{.Image}}' "$frontend_cid")"
    docker tag "$prev_api_img" "$API_IMAGE:previous"
    docker tag "$prev_web_img" "$WEB_IMAGE:previous"
    cp "$COMPOSE_FILE" "$STATE_DIR/docker-compose.prod.yml.previous"
    rm -f "$STATE_DIR/backup.sh.previous"
    if [ -f deploy/backup.sh ]; then cp deploy/backup.sh "$STATE_DIR/backup.sh.previous"; fi
    printf '%s\n' "${DEPLOYED_SHA:-unknown}" > "$STATE_DIR/previous_sha"
    PREV_AVAILABLE=1
    log "Tagged running images as :previous (release ${DEPLOYED_SHA:-unknown})."
else
    log "No running backend/frontend found - first deploy, rollback unavailable."
fi

# --- 3. Sync orchestration files at the release SHA ------------------------------------
sync_from_repo() {
    # $1 = path in the repo, $2 = local file to update if it changed
    repo_path="$1"
    local_path="$2"
    mkdir -p "$(dirname "$local_path")"
    # If a bind mount was started before the file existed, docker created an empty
    # directory in its place - remove it so the real file can land.
    if [ -d "$local_path" ]; then
        rmdir "$local_path" 2>/dev/null || { err "ERROR: $local_path is a non-empty directory"; return 1; }
    fi
    # Same directory as the destination, so `mv` is an atomic same-filesystem rename.
    tmp="$(mktemp "${local_path}.XXXXXX")"
    if curl -fsSL -H "Authorization: token $GITHUB_PAT" \
            "https://raw.githubusercontent.com/$GITHUB_REPO/$TARGET_SHA/$repo_path" -o "$tmp" 2>/dev/null; then
        if [ ! -f "$local_path" ] || ! cmp -s "$tmp" "$local_path"; then
            mv "$tmp" "$local_path"
            SYNC_CHANGED="$SYNC_CHANGED $repo_path"
            log "Updated $local_path from repo @ $TARGET_SHA."
        else
            rm -f "$tmp"
        fi
        return 0
    fi
    rm -f "$tmp"
    return 1
}

SYNC_CHANGED=""
if [ -n "$GITHUB_PAT" ]; then
    log "Syncing orchestration files @ $TARGET_SHA..."
    sync_ok=1
    sync_from_repo "docker-compose.prod.yml" "$COMPOSE_FILE" || sync_ok=0
    sync_from_repo "deploy/backup.sh" "deploy/backup.sh" || sync_ok=0
    if [ "$sync_ok" -ne 1 ]; then
        # Deploying new images with a stale compose file is how config drift starts.
        err "ERROR: could not fetch orchestration files @ $TARGET_SHA - not deploying."
        alert "could not fetch docker-compose.prod.yml/backup.sh @ $TARGET_SHA from GitHub (PAT expired?); deploy skipped"
        exit 1
    fi
    # Self-update: the atomic rename is safe while running (this process holds the old
    # file open); the new version takes effect on the next scheduled run.
    sync_from_repo "deploy/alert.sh" "deploy/alert.sh" || err "WARNING: could not sync deploy/alert.sh"
    sync_from_repo "deploy/check-env.sh" "deploy/check-env.sh" || err "WARNING: could not sync deploy/check-env.sh; using the local copy."
    if sync_from_repo "deploy/deploy-poll.sh" "$0"; then
        chmod +x "$0" 2>/dev/null || true
    else
        err "WARNING: could not self-update deploy-poll.sh; continuing with the current version."
    fi
else
    err "WARNING: GITHUB_PAT not set in $ENV_FILE - images only; docker-compose.prod.yml may drift from the release."
fi

# --- 3b. Preflight: required production settings ---------------------------------------
# deploy/check-env.sh prints variable NAMES and PASS/FAIL only, never values. A failure here
# aborts before anything is pulled, backed up or restarted, so the running release is untouched.
if [ -f deploy/check-env.sh ]; then
    if ! sh deploy/check-env.sh "$ENV_FILE" > "$STATE_DIR/preflight.log" 2>&1; then
        bad="$(grep -E 'MISSING \(REQUIRED\)|FAIL \(REQUIRED\)' "$STATE_DIR/preflight.log" | sed -e 's/[[:space:]]\{2,\}/ /g' | tr '
' ';' | cut -c1-600)"
        err "ERROR: production settings check failed for $TARGET_SHA: $bad"
        alert "release $TARGET_SHA NOT deployed: required production settings missing/invalid in $ENV_FILE ($bad) - see $STATE_DIR/preflight.log; current release keeps running"
        exit 1
    fi
    log "Production settings check passed."
else
    err "WARNING: deploy/check-env.sh not found - skipping the production settings preflight."
fi

# --- 4. Pull the release images -----------------------------------------------------
failed=0
for service in backend frontend; do
    log "Pulling $service @ $TARGET_SHA..."
    if ! compose_tag "$TARGET_SHA" "$COMPOSE_FILE" pull "$service"; then
        err "ERROR: pull failed for $service"
        failed=1
    fi
done
if [ "$failed" -ne 0 ]; then
    err "One or more pulls failed - NOT restarting services (staying on current release)."
    exit 1
fi

# --- 5. Pre-deploy database backup ------------------------------------------------
# The new backend runs migrations on start; this dump is the way back if one of them
# turns out to be destructive.
if docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps --status running -q db 2>/dev/null | grep -q .; then
    mkdir -p backups/predeploy
    dump="backups/predeploy/predeploy_$(date +%Y%m%d_%H%M%S)_from_${DEPLOYED_SHA:-unknown}.dump"
    log "Pre-deploy backup -> $dump"
    if docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
            sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --format=custom' > "$dump.partial" \
            && [ -s "$dump.partial" ]; then
        mv "$dump.partial" "$dump"
        chmod 600 "$dump" 2>/dev/null || true
        # keep the newest N
        ls -1t backups/predeploy/predeploy_*.dump 2>/dev/null | tail -n +"$((PREDEPLOY_BACKUP_KEEP + 1))" | while read -r old; do rm -f "$old"; done
    else
        rm -f "$dump.partial"
        alert "pre-deploy pg_dump failed; release $TARGET_SHA NOT deployed"
        exit 1
    fi
else
    log "db not running yet - skipping pre-deploy backup (first deploy)."
fi

# --- 6. Roll out + readiness gate ------------------------------------------------------
log "Rolling out $TARGET_SHA..."
rollout_ok=1
compose_tag "$TARGET_SHA" "$COMPOSE_FILE" up -d --remove-orphans --no-build || rollout_ok=0
case "$SYNC_CHANGED" in
    *deploy/backup.sh*)
        # A replaced bind-mounted file is a new inode; running containers keep the old one.
        log "backup.sh changed - recreating the backup container."
        compose_tag "$TARGET_SHA" "$COMPOSE_FILE" up -d --no-deps --force-recreate backup || true ;;
esac

wait_ready() {
    deadline=$(( $(date +%s) + READINESS_TIMEOUT ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        code=$(curl -s -o /dev/null -m 5 -w "%{http_code}" "$READINESS_URL" || true)
        if [ "$code" = "200" ]; then
            return 0
        fi
        log "Waiting for readiness at $READINESS_URL (got $code)..."
        sleep 5
    done
    return 1
}

if [ "$rollout_ok" -eq 1 ] && wait_ready; then
    printf '%s\n' "$TARGET_SHA" > "$STATE_DIR/deployed_sha"
    rm -f "$STATE_DIR/failed_sha"
    docker image prune -f >/dev/null 2>&1 || true
    log "Release $TARGET_SHA is ready. Done."
    exit 0
fi

# --- 7. Rollback ---------------------------------------------------------------------
err "ERROR: release $TARGET_SHA did not become ready within ${READINESS_TIMEOUT}s."
printf '%s\n' "$TARGET_SHA" > "$STATE_DIR/failed_sha"

if [ "$PREV_AVAILABLE" -ne 1 ]; then
    alert "release $TARGET_SHA failed readiness at $READINESS_URL and no previous release is available to roll back to"
    exit 1
fi

log "Rolling back to previous release (${DEPLOYED_SHA:-unknown})..."
cp "$STATE_DIR/docker-compose.prod.yml.previous" "$COMPOSE_FILE"
[ -f "$STATE_DIR/backup.sh.previous" ] && cp "$STATE_DIR/backup.sh.previous" deploy/backup.sh
if compose_tag previous "$COMPOSE_FILE" up -d --remove-orphans --no-build && wait_ready; then
    alert "release $TARGET_SHA failed readiness; ROLLED BACK to ${DEPLOYED_SHA:-previous}. Migrations run by the failed release are NOT reverted - check logs; pre-deploy dump is in backups/predeploy/"
else
    alert "release $TARGET_SHA failed readiness AND rollback to ${DEPLOYED_SHA:-previous} is not ready either - manual intervention required (pre-deploy dump in backups/predeploy/)"
fi
exit 1
