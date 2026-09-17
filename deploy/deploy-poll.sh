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
# Expected to run with its working directory set to the same directory that holds
# docker-compose.prod.yml and .env.production (normally /opt/rooman-billing).
set -eu

COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"
LOG_PREFIX="[deploy-poll $(date -Iseconds)]"

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

echo "$LOG_PREFIX Done."
