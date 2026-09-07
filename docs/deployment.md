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
```

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

```bash
cd /opt/rooman-billing
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' | gzip > /var/backups/rooman_pre_upgrade_$(date +%F_%H%M).sql.gz
git pull --ff-only
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

- Images are rebuilt; the `backend` container runs new migrations on start, `frontend` picks up
  the new bundle (index.html is served `no-cache`, assets are content-hashed).
- Brief API downtime while the backend container restarts (seconds). For zero-downtime, run two
  hosts behind a load balancer or scale `backend` before recreating (`--scale backend=2` is
  safe because the scheduler is a separate service; migrations are idempotent).
- Read the release notes for any migration that rewrites large tables and schedule accordingly.

Pin releases by checking out a tag and setting `IMAGE_TAG=<tag>` in `.env.production` so old
images remain available for rollback.

## 8. Rollback

1. `git checkout <previous-tag>` (or set `IMAGE_TAG` to the previous tag if images were kept).
2. If the new release added migrations that the old code cannot run with, downgrade first:
   ```bash
   docker compose --env-file .env.production -f docker-compose.prod.yml run --rm -e RUN_MIGRATIONS=false backend \
     alembic -c backend/alembic.ini downgrade <previous_revision>
   ```
   or restore the pre-upgrade dump (see `operations.md`, restore section).
3. `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build`.

## 9. Rotating secrets

| Secret | Procedure | Impact |
| --- | --- | --- |
| `SECRET_KEY` | change in `.env.production`, `up -d backend scheduler` | all access tokens invalid; users re-authenticate transparently via refresh tokens (stored hashed, unaffected). |
| `POSTGRES_PASSWORD` | `ALTER USER rooman WITH PASSWORD '...'` inside `db`, then update the env file and restart `backend`/`scheduler` | seconds of API errors during restart. The `db` container only reads the variable on first init. |
| Razorpay keys / webhook secret | regenerate in the dashboard, update env, `up -d backend scheduler` | in-flight checkouts created with old keys may fail; do it during a quiet period. |
| SMTP credentials | update env, restart | none. |

## 10. Monitoring

- **Liveness**: `GET https://<DOMAIN>/healthz` (nginx) and container `docker compose ps` health
  columns (backend uses `/api/v1/health` internally).
- **Readiness/DB**: `GET https://<DOMAIN>/api/v1/health` - alert when `status != "healthy"` or the
  HTTP code is not 200. It is public and cheap (a `SELECT 1`).
- **Scheduler**: it logs one summary line per run (renewals, trials converted, overdue marked,
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
- [ ] HSTS enabled at the TLS terminator (already in `deploy/Caddyfile`).
- [ ] Daily `pg_dump` to off-host storage with a tested restore (see `operations.md`).
- [ ] Razorpay live keys restricted to the production account; webhook secret set.
- [ ] Docker and base images updated on a schedule (`docker compose pull db caddy`, rebuild app images).
