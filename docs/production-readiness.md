# Rooman Billing — Production Readiness & Operations Guide

This document summarizes the production readiness status, architecture configurations, deployment instructions, and known items requiring Sir/product decisions.

---

## 1. Production Readiness Audit Summary

| Area | Status | Notes |
| :--- | :--- | :--- |
| **A. SMTP / Email** | **READY** | Dual-layer SMTP architecture (global environment fallback + tenant-level encrypted credentials with STARTTLS/SSL, PDF attachment for invoices & quotes, HTML templates, connection tests, non-blocking delivery). |
| **B. Production Environment Configuration** | **READY** | Validated via `backend/app/core/config.py` against weak keys, SQLite in production, `DEBUG=true`, or wildcard origins. Safe template provided in `.env.production.example`. |
| **C. Production Deployment Readiness** | **READY** | Multi-container Docker Compose (`docker-compose.prod.yml`) with per-service resource limits, Nginx reverse proxy with SPA fallback, Caddy TLS overlay, health probes. CI-gated image publish by immutable SHA tag; pull-based deploy with pre-deploy DB dump, readiness gate, automatic rollback and webhook alerts (section 10). |
| **G. Backups** | **READY once offsite is configured** | Nightly DB dump + uploads tarball, rclone offsite copy, failure alerts, healthcheck on last success. Set `OFFSITE_BACKUP_REMOTE` + `OFFSITE_S3_*` and `ALERT_WEBHOOK_URL`. |
| **D. Persistent File/Logo Storage** | **READY (Single Host) / REQUIRES EXTERNAL DECISION (Multi-Instance)** | Local filesystem storage (`uploads_data` volume mounted to `/app/backend/uploads`) with 5MB validation, MIME/magic byte checks, and automatic file cleanup. Multi-instance shared object storage (S3/GCS/R2) requires Sir's external provider decision. |
| **E. Production QA & Verification** | **READY** | All 578 backend tests and 303 frontend tests passing; TypeScript (`tsc --noEmit`) and Vite production bundle passing; live smoke tests verified across all 18 business workflows. |
| **F. Documentation** | **READY** | Complete operations, deployment, and runbook documentation available in `docs/`. |

---

## 2. Production Environment Variables Reference

A production deployment requires `.env.production` (cloned from `.env.production.example` and set to `chmod 600`).

### Core Security & Database
```env
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<GENERATE_WITH_OPENSSL_RAND_HEX_32>
POSTGRES_USER=rooman
POSTGRES_PASSWORD=<STRONG_RANDOM_PASSWORD>
POSTGRES_DB=rooman_billing
DATABASE_URL=postgresql://rooman:<STRONG_RANDOM_PASSWORD>@db:5432/rooman_billing
APP_POSTGRES_USER=rooman_app                      # REQUIRED runtime role, != POSTGRES_USER
APP_POSTGRES_PASSWORD=<STRONG_RANDOM_PASSWORD_16+>  # REQUIRED
REDIS_URL=redis://redis:6379/0
```

Required: `APP_POSTGRES_USER`/`APP_POSTGRES_PASSWORD` make the app run as a DML-only `NOSUPERUSER NOBYPASSRLS` runtime role (so row level security applies) while migrations keep running as `POSTGRES_USER`. Create it with `sh deploy/db-least-privilege.sh`; the app refuses to start in production as a superuser/BYPASSRLS role. `POSTGRES_SSLMODE=verify-full` plus `POSTGRES_SSLROOTCERT` are **required** for a non-private DB host. `ENCRYPTION_KEYS` sets the keyring for stored secrets. See [`database-security.md`](database-security.md).

### URLs, CORS, hosts & proxies
```env
FRONTEND_URL=https://billing.example.com          # must be https in production
ALLOWED_ORIGINS=https://billing.example.com       # https only, no '*'
ALLOWED_HOSTS=billing.example.com                 # optional; derived from FRONTEND_URL if empty; '*' refused
TRUSTED_PROXIES=                                  # optional; default private + loopback CIDRs
SECURE_COOKIES=true
ALERT_WEBHOOK_URL=https://hooks.slack.com/...     # app + deploy + backup alerts
```

### Outbound SMTP Relay (Global Fallback)
```env
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=<PRODUCTION_SMTP_KEY>
SMTP_USE_TLS=true
SMTP_USE_SSL=false
EMAIL_FROM_ADDRESS=billing@example.com
EMAIL_FROM_NAME="Rooman Billing"
```

### Storage Configuration
```env
UPLOAD_DIR=/app/backend/uploads
```

### Payment Gateway & Webhooks (Pending Provider Approval)
```env
RAZORPAY_KEY_ID=<RAZORPAY_KEY_ID>
RAZORPAY_KEY_SECRET=<RAZORPAY_KEY_SECRET>
RAZORPAY_WEBHOOK_SECRET=<RAZORPAY_WEBHOOK_SECRET>
```

---

## 3. SMTP Setup & Testing

1. **Global Fallback**: Set in `.env.production`. Used when an organization has not configured custom SMTP.
2. **Tenant Custom SMTP**: Configured via UI (**Settings -> Integrations -> Custom SMTP Server**) or `POST /api/v1/integrations/smtp`. Credentials are encrypted at rest with AES-128 Fernet and redacted in all API outputs.
3. **Connection Testing**:
   - UI: **Test Connection** button tests socket & handshake.
   - UI: **Send Test Email** sends a test email to verify mailbox delivery.
   - API: `POST /api/v1/integrations/smtp/test` and `POST /api/v1/integrations/smtp/test-email`.
4. **Resilience**: Outbound email failure does not roll back invoice creation or quote submission; warnings are logged and public links remain accessible in the UI.

---

## 4. Deployment Steps & Startup Architecture

### Target Topology
- **Reverse Proxy**: Nginx (in `rooman-billing-web`) or Caddy (in `deploy/Caddyfile`) terminating TLS.
- **Frontend**: Single-page application static bundle served with `try_files $uri /index.html`.
- **Backend API**: FastAPI running under Gunicorn with Uvicorn workers (`WEB_CONCURRENCY=2`), `SCHEDULER_ENABLED=false`.
- **Background Scheduler**: Exactly one container running `run_forever()` with `SCHEDULER_ENABLED=true` for renewals, trial conversion, dunning, and invoice reminders.
- **Database**: PostgreSQL 16 on internal network with named volume `postgres_data`.

### Starting the Stack
```bash
# 1. Prepare environment
cp .env.production.example .env.production
chmod 600 .env.production
# Fill in production values

# 2. Start stack with Docker Compose
docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.caddy.yml up -d --build

# 3. Verify services
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

---

## 5. Database Setup & Migrations

- Migrations run automatically on API startup via Alembic (`RUN_MIGRATIONS=true`). They run as the owner role (`MIGRATION_*`, which is `POSTGRES_USER` in compose). The API itself can run as a DML-only role. The entrypoint unsets the owner credentials before gunicorn starts. See [`database-security.md`](database-security.md).
- To manually execute migrations:
```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec backend alembic upgrade head
```

---

## 6. Health Checks & Monitoring

1. **Liveness Probe**:
   - `GET /healthz` (Nginx): returns HTTP 200 `ok`.
   - `GET /api/v1/health` (FastAPI): lightweight `SELECT 1` DB probe.
2. **Deep Readiness Probe**:
   - `GET /api/v1/health/ready`: returns HTTP 200 only if the database is connected AND Alembic migrations are at the current `head`. Returns HTTP 503 if migrations are pending or DB is unavailable.
3. **Features Check**:
   - Verify `features.scheduler_enabled` is `false` on the API and `true` on the scheduler container.
   - `features.scheduler_heartbeat.status` should be `ok` (informational; never makes the API unready). The `scheduler` container healthcheck uses the same heartbeat.
4. **Errors**: the health endpoints never return raw database errors (`"error": "database unreachable"`); details are in the backend log.

---

## 7. Persistent File & Logo Storage

### Current Implementation (Single-Host Production)
- Organization logos and avatars are stored in `UPLOAD_DIR` (`/app/backend/uploads`).
- Mounted via Docker named volume: `uploads_data:/app/backend/uploads`.
- Security controls:
  - File size restricted to <= 5 MB.
  - Allowed MIME types: `image/jpeg`, `image/png`, `image/webp`.
  - Magic byte verification prevents disguised executable/malicious uploads.
  - Previous logos are removed upon replacement to prevent storage bloat.
  - `.gitignore` prevents upload assets from being committed to source control.

### Multi-Instance Production Deployment
- In a horizontally scaled cluster (multi-host Kubernetes/ECS), local volumes are not shared across nodes.
- **Status: REQUIRES EXTERNAL DECISION**. Selection of an object storage provider (AWS S3, Google Cloud Storage, Azure Blob Storage, or Cloudflare R2) requires Sir's architectural approval.

---

## 8. Backup & Recovery Considerations

- The `backup` service (`deploy/backup.sh`) runs nightly (`BACKUP_CRON`): `pg_dump -Fc` + `tar.gz` of the uploads volume, local retention (`BACKUP_RETENTION_DAYS`), optional **offsite** copy via rclone (`OFFSITE_BACKUP_REMOTE`, `OFFSITE_S3_*`), `last_success` marker (container turns unhealthy after 26 h without success), alert to `ALERT_WEBHOOK_URL` on failure.
- The deploy poller takes a pre-deploy dump into `backups/predeploy/` before every rollout.
- Restore procedures for the database **and** uploads, plus the quarterly drill: `docs/operations.md` section 1.

---

## 9. Architectural Items Requiring Sir / Product Approval

The following items are deliberately maintained without modification and require Sir's explicit direction:

1. **Project Payments Architecture**:
   - Direct payment recording against projects vs. routing payments strictly through project invoices.
2. **Project ↔ Invoice Financial Synchronization**:
   - Automated real-time balance propagation between project budget consumed vs. invoiced/paid amounts.
3. **Production Payment Gateway / Provider Selection**:
   - Final approval of primary payment processor (Razorpay live mode vs. Stripe / CCAvenue / cashfree / bank gateway).

---

## 10. Infrastructure & Operations Checklist (current)

**Deploy pipeline**
- [x] Images published only after CI passes on a `push` to `main`; manual dispatch restricted to `main` and to commits with a successful CI run (`.github/workflows/deploy.yml`).
- [x] Images tagged `<git sha>` + label `org.opencontainers.image.revision`; `:latest` moved only after both images are pushed.
- [x] Poller deploys `IMAGE_TAG=<sha>` and syncs `docker-compose.prod.yml` / `deploy/*.sh` **at that SHA**, not from the tip of `main`.
- [x] Pre-deploy `pg_dump`; readiness gate on `READINESS_URL` (from env, host-local default); automatic rollback to `:previous` + alert; failed SHA not retried.
- [x] systemd `OnFailure=rooman-billing-alert@%n.service` posts poll failures to `ALERT_WEBHOOK_URL`.
- [ ] Migrations kept backward compatible with the previous release (rollback swaps images only; migrations are forward-only).

**Runtime**
- [x] Resource limits: backend 1g, scheduler 512m, db 1g, frontend/redis/backup 256m (override via `*_MEM_LIMIT` / `*_CPUS`).
- [x] `db` and `backup` get only the variables they need (no `env_file`).
- [x] Scheduler container healthcheck on the heartbeat; heartbeat reported in `/health/ready`.
- [x] Caddy global `debug` removed.
- [x] Health endpoints return a generic DB error.

**Backups**
- [x] Nightly DB + uploads backup, local retention, last-success healthcheck, failure alert.
- [ ] `OFFSITE_BACKUP_REMOTE` + credentials configured and an upload verified.
- [ ] Restore drill (DB + uploads) performed from the offsite copy.

**CI quality gates** (`.github/workflows/ci.yml`)
- [x] ruff (real-error rules, `backend/ruff.toml`), pytest on PostgreSQL 16, vitest, tsc, vite build.
- [x] Postgres enum labels vs Python enums checked after `alembic upgrade head` (`backend/tests/test_migrations.py`).
- [x] pip-audit / npm audit (high) - **non-blocking** for now.
- [ ] `alembic check` still a warning: declare the 5 known indexes in the models (`ix_subscriptions_org_status`, `ix_org_integrations_org_id`, `ix_org_integrations_provider`), then make it blocking.
- [x] Runtime deps pinned exactly in `backend/requirements.txt`; test/lint tools in `backend/requirements-dev.txt` (not in the image).

**Security hardening** ([`database-security.md`](database-security.md), [`security-roadmap.md`](security-roadmap.md))
- [x] Startup refuses non-https `FRONTEND_URL`/origins, `*` origins or hosts, and a remote DB without verified TLS. Validation errors hide input values.
- [x] `TrustedHostMiddleware` (`ALLOWED_HOSTS`), `TRUSTED_PROXIES` for `X-Real-IP`, explicit CORS methods and headers, `Cache-Control: no-store` on API responses.
- [x] Log redaction covers `%`-args and tracebacks (passwords, OTPs, tokens, API keys, Authorization, card numbers).
- [x] App alerts via `core/alerts.send_alert`: login/MFA lockouts and readiness DB failures. Deduplicated and redacted.
- [x] Encryption keyring (`ENCRYPTION_KEYS`) plus a `python -m backend.app.core.encryption rotate` helper. Backwards compatible.
- [ ] Least-privilege runtime role enabled in production (`APP_POSTGRES_*` + `sh deploy/db-least-privilege.sh`).
- [ ] Cookie-based auth + CSRF (designed in `security-roadmap.md`; **not implemented**).
- [ ] KMS-backed keys. Production KMS provider integration requires infrastructure configuration.

**Secrets / settings to provide**
- [ ] `ALERT_WEBHOOK_URL`, `OFFSITE_*`, `GITHUB_PAT` (Contents: read) in `.env.production`.
- [ ] Install `deploy/rooman-billing-alert@.service` next to the poll service/timer.
