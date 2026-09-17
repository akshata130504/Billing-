#!/bin/sh
# Polls GHCR for newer production images and rolls them out.
#
# This runs ON the production server itself (see rooman-billing-poll.timer), pulling
# images that .github/workflows/deploy.yml already built and pushed to GHCR on the
# last successful CI run on main. The server is behind a private/LAN network with no
# inbound path from GitHub's hosted runners, so it pulls on its own schedule instead
# of GitHub pushing/SSHing into it.
#
# One-time setup on this server, before the first run:
#   docker login ghcr.io -u <your-github-username>
#   (password: a GitHub PAT with the `read:packages` scope - any collaborator can
#   create one for themselves, no repo Admin access needed)
#
# Optional but recommended - keep this script and docker-compose.prod.yml in sync
# with the repo automatically (not just the images): add a line
#   GITHUB_PAT=<a token with read access to this repo's contents>
# to .env.production. A fine-grained PAT scoped to just this one repo with
# "Contents: Read-only" is the safest choice; a classic PAT needs the `repo` scope.
# Without this set, the sync step below is skipped and only images are updated.
#
# Expected to run with its working directory set to the same directory that holds
# docker-compose.prod.yml and .env.production (normally /opt/rooman-billing).
set -eu

REPO_RAW_BASE="https://raw.githubusercontent.com/rooman-itsd/Rooman-Billing/main"
COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"
LOG_PREFIX="[deploy-poll $(date -Iseconds)]"

# --- Keep orchestration files in sync with the repo, not just the images ------------
# Without this, a fix to docker-compose.prod.yml or this script itself would silently
# require someone to manually re-paste it on the server forever.
GITHUB_PAT="$(grep -E '^GITHUB_PAT=' .env.production 2>/dev/null | head -n1 | cut -d '=' -f2-)"

sync_from_repo() {
    # $1 = path in the repo, $2 = local file to update if it changed
    repo_path="$1"
    local_path="$2"
    # Same directory as the destination, so the `mv` below is always an atomic
    # same-filesystem rename - a temp dir like /tmp could be a different filesystem,
    # which would silently degrade `mv` to a non-atomic copy+unlink.
    tmp="$(mktemp "${local_path}.XXXXXX")"
    if curl -fsSL -H "Authorization: token $GITHUB_PAT" "$REPO_RAW_BASE/$repo_path" -o "$tmp" 2>/dev/null; then
        if [ ! -f "$local_path" ] || ! cmp -s "$tmp" "$local_path"; then
            mv "$tmp" "$local_path"
            echo "$LOG_PREFIX Updated $local_path from repo."
        else
            rm -f "$tmp"
        fi
    else
        echo "$LOG_PREFIX WARNING: could not fetch $repo_path from repo, keeping existing $local_path" >&2
        rm -f "$tmp"
    fi
}

if [ -n "$GITHUB_PAT" ]; then
    echo "$LOG_PREFIX Syncing orchestration files from repo..."
    sync_from_repo "docker-compose.prod.yml" "docker-compose.prod.yml"
    # Self-update: replacing this file via `mv` (atomic rename) is safe even while it's
    # running - this process already holds the old file's data open. The new version
    # only takes effect on the *next* scheduled run, which keeps this simple and avoids
    # any self-modifying-script hazards.
    sync_from_repo "deploy/deploy-poll.sh" "$0"
    chmod +x "$0" 2>/dev/null || true
else
    echo "$LOG_PREFIX GITHUB_PAT not set in .env.production - skipping repo file sync (images only)."
fi

# --- Pull and roll out any new images -------------------------------------------------
echo "$LOG_PREFIX Checking for new images..."

# Pull one service at a time and prune (never -a, that would also remove images other
# things on this host still need) after each. This way a disk-full failure partway
# through never leaves some services on new images and others silently stuck on old
# ones - we only cut over once every pull has succeeded.
failed=0
for service in backend frontend; do
    echo "$LOG_PREFIX Pulling $service..."
    if $COMPOSE pull "$service"; then
        docker image prune -f >/dev/null 2>&1 || true
    else
        echo "$LOG_PREFIX ERROR: pull failed for $service" >&2
        failed=1
    fi
done

if [ "$failed" -ne 0 ]; then
    echo "$LOG_PREFIX One or more pulls failed - NOT restarting services (staying on current images)." >&2
    exit 1
fi

echo "$LOG_PREFIX All pulls succeeded. Rolling out..."
$COMPOSE up -d --remove-orphans --no-build

# Confirm the rollout actually came up healthy rather than assuming `up -d` succeeding
# means the app is serving traffic - `docker compose up` only waits for depends_on
# conditions on (re)started containers, it doesn't itself verify the public endpoint.
echo "$LOG_PREFIX Waiting for the service to report ready..."
ready=0
for i in $(seq 1 30); do
    code=$(curl -s -o /dev/null -w "%{http_code}" https://billing.futureacad.ae/api/v1/health/ready || true)
    if [ "$code" = "200" ]; then
        echo "$LOG_PREFIX Service is ready."
        ready=1
        break
    fi
    echo "$LOG_PREFIX Waiting for readiness (attempt $i, got $code)..."
    sleep 5
done

if [ "$ready" -ne 1 ]; then
    echo "$LOG_PREFIX ERROR: service did not become ready in time after rollout." >&2
    exit 1
fi

echo "$LOG_PREFIX Done."
