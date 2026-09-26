# Rooman Billing - Production Deployment Runbook

Target: a single Linux host running Docker Compose with PostgreSQL, the API, the scheduler and
the web tier as containers, TLS terminated by Caddy (bundled overlay) or any reverse proxy you
already operate. The same images work on any orchestrator; the compose files are the reference.

## 0. What gets deployed

| Service | Image | Role |
| --- | --- | --- |
| `db` | `postgres:16-alpine` | Data. Named volume `postgres_data`. Not exposed to the host. |
| `backend` | `rooman-billing-api` (`backend/Dockerfile`) | gunicorn with `WEB_CONCURRENCY` uvicorn workers on :8000. Waits for the DB, runs `alembic upgrade head`, then serves. `SCHEDULER_ENABLED=false`. |
| `scheduler` | same image | One container, `SCHEDULER_ENABLED=true`, command `python -c "from backend.app.services.scheduler import run_forever; run_forever()"`. Renewals, trial conversion, overdue marking, dunning. |
| `frontend` | `rooman-billing-web` (`frontend/Dockerfile`) | nginx: SPA + `/api/` proxy to `backend:8000`. Publishes `${FRONTEND_BIND:-80}:80`. |
| `caddy` (optional overlay) | `caddy:2-alpine` | Automatic HTTPS for `DOMAIN`, proxies to `frontend:80`. |

Razorpay webhooks therefore arrive at `https://<DOMAIN>/api/v1/webhooks/razorpay` -> caddy ->
nginx -> backend.

## 1. Provision the host

- Ubuntu 22.04/24.04 (or any Docker-capable distro), 2 vCPU / 4 GB RAM / 40 GB SSD is plenty for
  thousands of invoices a month. Scale `WEB_CONCURRENCY` with vCPUs (2 x cores).
- Install Docker Engine + Compose plugin (`docker compose version` >= 2.20).
- Firewall: allow 22 (restricted), 80 and 443 only. Postgres and the API are never published.
- Create an unprivileged deploy user in the `docker` group; clone the repository to
  `/opt/rooman-billing`.
- Set the host clock to UTC/NTP (renewals and due dates are computed from the server date).

## 2. DNS and TLS

1. Create an `A`/`AAAA` record `billing.example.com` -> host IP. Wait until it resolves.
2. Choose one:
   - **Bundled Caddy** (recommended for a single host): nothing else to install; certificates are
     obtained from Let's Encrypt automatically. Caddyfile: `deploy/Caddyfile`.
   - **Existing reverse proxy** (nginx/Traefik/ALB): terminate TLS there and forward to the
     frontend container port (`FRONTEND_BIND=127.0.0.1:8080`). Forward `X-Forwarded-Proto` and
     `X-Forwarded-For`; allow request bodies of at least 10 MB for CSV imports.

## 3. Create `.env.production`

```bash
cd /opt/rooman-billing
cp .env.production.example .env.production
chmod 600 .env.production
```

Edit and set at minimum:

| Variable | Value |
| --- | --- |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | `openssl rand -base64 24 \| tr -d '/+='` (anything but `postgres`) |
| `FRONTEND_URL` | `https://billing.example.com` |
| `ALLOWED_ORIGINS` | `https://billing.example.com` |
| `SECURE_COOKIES` | `true` |
| `SMTP_*`, `EMAIL_FROM_*` | your relay (optional but strongly recommended) |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | live keys (optional; can be added later) |
| `DOMAIN`, `ACME_EMAIL`, `FRONTEND_BIND=127.0.0.1:8080` | only when using the Caddy overlay |

`ENVIRONMENT=production` and `DEBUG=false` are already set in the template. The API validates
the file on boot and exits with a clear message if something is insecure.

## 4. First start

```bash
# without TLS overlay (a proxy you run terminates TLS and forwards to FRONTEND_BIND)
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build

# with the bundled Caddy
docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.caddy.yml up -d --build
```

`--env-file .env.production` makes the `${...}` interpolations (`WEB_CONCURRENCY`, `FRONTEND_BIND`,
`DOMAIN`, `IMAGE_TAG`) read the same file the containers use.

Watch it come up:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f backend
```

Expected backend log sequence: `waiting for database` -> `database reachable` ->
`applying migrations` (Alembic `Running upgrade -> 0001_initial_schema`) -> gunicorn
`Booting worker`. Then:

```bash
curl -s https://billing.example.com/api/v1/health
# {"status":"healthy", ..., "database":{"status":"connected","dialect":"postgresql"}}
curl -s https://billing.example.com/healthz          # ok

# Deep readiness: 200 only when the DB is up AND the schema is at the Alembic head.
curl -si https://billing.example.com/api/v1/health/ready | head -1   # HTTP/2 200
curl -s  https://billing.example.com/api/v1/health/ready | jq '.ready, .checks.migrations, .features'
```

A 503 from `/api/v1/health/ready` right after a deploy usually just means migrations are still
running; if it persists, `failures` names the culprit (`database` or `migrations`) - see
[`operations.md`](operations.md) section 3. Gate your deploy on this endpoint rather than on
`/api/v1/health`, which returns 200 even when the schema is behind.

Also check `features` in that response: `scheduler_enabled` must be `false` on the `backend`
service (the separate `scheduler` service runs the jobs), and `razorpay_configured` /
`smtp_configured` / `sentry_enabled` should match what you put in `.env.production`.

## 5. First login

There is no seed user. Open `https://billing.example.com/signup` and register: this calls
`POST /api/v1/auth/signup`, which creates the first **organization** and its **owner**
account in one step (the organization slug is derived from the name). From **Settings -> Team**
invite the rest of the staff with the right roles (`admin`, `finance`, `viewer`). If SMTP is not
configured yet, the invitation link is shown to you to forward manually.

Recommended next steps in **Settings**: legal name/GSTIN/address (printed on invoices and PDFs),
document prefixes and next numbers, default payment terms and tax rate, discount approval
threshold.

## 6. Configure and verify Razorpay webhooks

1. Razorpay Dashboard -> **Account & Settings -> Webhooks -> Add New Webhook**.
   URL `https://billing.example.com/api/v1/webhooks/razorpay`; events `payment.captured`,
   `payment.failed`, `refund.processed`; set a secret and copy it to `RAZORPAY_WEBHOOK_SECRET`.
2. Restart the API so it picks up the secret:
   `docker compose --env-file .env.production -f docker-compose.prod.yml up -d backend scheduler`.
3. `curl https://billing.example.com/api/v1/meta/integrations` should show `"razorpay": {"enabled": true, ...}`.
4. Create a small invoice for a test customer, send it, open its hosted page (`/pay/<token>`) and
   pay with a test card (test-mode keys) or a real small amount. The invoice becomes `paid`, the
   payment `succeeded`/`auto_matched`, and the audit log shows `PAYMENT_CAPTURED` and
   `WEBHOOK_RECEIVED`. The Razorpay webhook page shows the delivery with HTTP 200.
5. A rejected signature appears in the backend log and the audit log as `WEBHOOK_REJECTED`; check
   that the secret matches.

## 7. Upgrading

Normal path (automatic): merge to `main` -> CI passes -> `.github/workflows/deploy.yml` pushes
`rooman-billing-{api,web}:<sha>` and moves `:latest` -> the host's `rooman-billing-poll.timer`
(every 2 min) runs `deploy/deploy-poll.sh`, which

1. reads the release SHA from the `org.opencontainers.image.revision` label of `api:latest`,
2. fetches `docker-compose.prod.yml`, `deploy/backup.sh`, `deploy/alert.sh` and itself **at that
   SHA** (needs `GITHUB_PAT`),
3. pulls the images, takes a pre-deploy `pg_dump` into `backups/predeploy/`,
4. `up -d` with `IMAGE_TAG=<sha>` and waits for `READINESS_URL` to return 200,
5. records `.deploy/deployed_sha`, or rolls back and alerts (section 8).

`workflow_dispatch` of Deploy only works on `main` and only for a commit whose CI already
succeeded - it re-publishes, it cannot bypass CI.

Install / update the systemd units once:

```bash
sudo cp deploy/rooman-billing-poll.service deploy/rooman-billing-poll.timer         deploy/rooman-billing-alert@.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now rooman-billing-poll.timer
journalctl -u rooman-billing-poll.service -f
```

Any failure of the poll unit also triggers `rooman-billing-alert@.service` -> `ALERT_WEBHOOK_URL`.

Notes: the backend runs new migrations on start (brief API restart, seconds). Keep migrations
backward compatible with the previous release (expand first, contract in a later release) so an
image rollback stays possible. Read release notes for migrations that rewrite large tables.

Manual build on the host (no GHCR) still works: `make up-prod` (`up -d --build`).

## 8. Rollback

Automatic: when the new release is not ready within `READINESS_TIMEOUT` the poller re-deploys the
previous images (kept locally as `:previous`) with the previous compose file, writes the bad SHA
to `.deploy/failed_sha` (skipped until you delete it) and alerts. **Migrations are not reverted.**

Manual, to any published SHA:

```bash
IMAGE_TAG=<sha> docker compose --env-file .env.production -f docker-compose.prod.yml up -d --no-build
echo <sha> > .deploy/deployed_sha
```

If the failed release's migrations broke the old code, restore the newest
`backups/predeploy/*.dump` (see [`operations.md`](operations.md) section 1, "Restore") - or, only if
the migration's `downgrade()` is known-good:
`... run --rm -e RUN_MIGRATIONS=false backend alembic -c backend/alembic.ini downgrade <rev>`.

### Deploy / backup variables (`.env.production`)

| Variable | Default | Purpose |
|---|---|---|
| `IMAGE_TAG` | `latest` | Fallback only; the poller exports `IMAGE_TAG=<sha>` |
| `GITHUB_PAT` | - | Contents:read PAT so the poller syncs orchestration files at the release SHA |
| `READINESS_URL` | `http://127.0.0.1:<FRONTEND_BIND>/api/v1/health/ready` | Deploy gate (must be reachable from the host) |
| `READINESS_TIMEOUT` / `PREDEPLOY_BACKUP_KEEP` | `180` / `10` | Gate timeout (s) / pre-deploy dumps kept |
| `ALERT_WEBHOOK_URL` | - | `{"text": ...}` POST on backup failure, rollback, poll-unit failure |
| `BACKUP_CRON` / `BACKUP_RETENTION_DAYS` | `15 1 * * *` / `30` | Nightly backup schedule / local retention |
| `OFFSITE_BACKUP_REMOTE` | - | rclone target `offsite:<bucket>/<prefix>`; empty = local only |
| `OFFSITE_S3_PROVIDER`, `_REGION`, `_ENDPOINT`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY` | `AWS` | S3-compatible credentials for the `offsite` remote |
| `OFFSITE_RETENTION_DAYS` / `OFFSITE_REQUIRED` | - / `true` | Offsite pruning / fail+alert on upload error |
| `*_MEM_LIMIT`, `*_CPUS` | backend 1g, scheduler 512m, db 1g, frontend/redis/backup 256m | Container limits |

The `db` and `backup` containers no longer read `.env.production` wholesale; they receive only
`POSTGRES_*` (and the backup/offsite/alert variables above) via compose interpolation.

## 9. Rotating secrets

| Secret | Procedure | Impact |
| --- | --- | --- |
| `SECRET_KEY` | change in `.env.production`, `up -d backend scheduler` | all access tokens invalid; users re-authenticate transparently via refresh tokens (stored hashed, unaffected). |
| `POSTGRES_PASSWORD` | `ALTER USER rooman WITH PASSWORD '...'` inside `db`, then update the env file and restart `backend`/`scheduler` | seconds of API errors during restart. The `db` container only reads the variable on first init. |
| Razorpay keys / webhook secret | regenerate in the dashboard, update env, `up -d backend scheduler` | in-flight checkouts created with old keys may fail; do it during a quiet period. |
| SMTP credentials | update env, restart | none. |

Before the first real customer, work through the **pre-launch checklist** in
[`operations.md`](operations.md) section 9 - secrets rotation, a rehearsed backup restore, and the
Razorpay test-to-live key switchover.

## 10. Monitoring

- **Liveness**: `GET https://<DOMAIN>/healthz` (nginx) and container `docker compose ps` health
  columns (backend uses `/api/v1/health` internally).
- **Readiness**: `GET https://<DOMAIN>/api/v1/health/ready` - **alert on any non-200**. It returns
  503 when the database is unreachable or the schema is not at the Alembic head, and its `features`
  block reports scheduler/Razorpay/SMTP/Sentry configuration. This is also the right probe for a
  load balancer and for gating a deploy. See [`operations.md`](operations.md) section 3.
- **DB only**: `GET https://<DOMAIN>/api/v1/health` - always 200; alert when
  `status != "healthy"`. Cheap (a `SELECT 1`) and used by the container healthcheck.
- **Errors**: set `SENTRY_DSN` to send exceptions to Sentry. Optional - with it empty the SDK is
  never imported. Events are scrubbed of tokens, passwords, GSTIN/PAN and card-like fields before
  leaving the host; see [`operations.md`](operations.md) section 4.
- **Scheduler**: **required in production.** `docker-compose.prod.yml` runs a dedicated `scheduler`
  service with `SCHEDULER_ENABLED=true` while the API replicas keep it `false`. If no process has
  it enabled, renewals, trial conversion, overdue marking and dunning never run and nothing looks
  broken - the API logs a startup WARNING for exactly this case. Exactly one process may have it
  enabled. It logs one summary line per run (renewals, trials converted, overdue marked,
  reminders sent). Alert if no line appears for `2 x SCHEDULER_INTERVAL_MINUTES`.
  Owners can also trigger a run with `POST /api/v1/admin/jobs/run`.
- **Disk**: `postgres_data` volume and Docker log files (rotated at 5 x 20 MB per container by the
  compose logging config).
- **TLS**: Caddy renews automatically; alert on certificate expiry < 14 days anyway.
- Ship stdout logs (`LOG_JSON=true`) with your preferred agent (`docker compose logs` or the
  json-file driver under `/var/lib/docker/containers/*/`).

## 11. Hardening checklist

- [ ] `.env.production` mode 600, owned by the deploy user, not in git.
- [ ] Only 80/443 (and restricted 22) open on the host firewall.
- [ ] `SECURE_COOKIES=true`, `FRONTEND_URL` and `ALLOWED_ORIGINS` use `https://`.
- [ ] HSTS enabled at the TLS terminator (already in `deploy/Caddyfile`); the web container also
      emits it, plus a CSP, on requests it sees as `https` (`frontend/docker/security-headers.conf`).
- [ ] Hosted payment page verified **after** any CSP change - the Razorpay modal needs
      `https://checkout.razorpay.com` and `https://api.razorpay.com` to stay allow-listed.
- [ ] `/api/v1/health/ready` returns 200 and is wired to an alert.
- [ ] Exactly one process with `SCHEDULER_ENABLED=true`.
- [ ] `OFFSITE_BACKUP_REMOTE` set, `backup` container healthy, restore drill done (see `operations.md`).
- [ ] `ALERT_WEBHOOK_URL` set and tested; `rooman-billing-alert@.service` installed.
- [ ] Razorpay live keys restricted to the production account; webhook secret set.
- [ ] Docker and base images updated on a schedule (`docker compose pull db caddy`, rebuild app images).
