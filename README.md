# Rooman Billing

Multi-tenant billing and subscription management for Indian SMEs: customers, catalog, quotes,
subscriptions, invoices with a hosted payment page, Razorpay online payments, manual payments and
reconciliation, refunds, dunning, approvals, audit trail and a control-center dashboard.

- **Backend** - Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic, PostgreSQL 16, APScheduler, ReportLab (PDF), Razorpay SDK.
- **Frontend** - React 18, Vite, TypeScript, Tailwind CSS, React Router v6, TanStack Query, Axios.
- **Ops** - Docker images for API and web, `docker compose` production stack, GitHub Actions CI.

The API contract shared by both halves is [`docs/api-contract.md`](docs/api-contract.md).

---

## Features in this release

| Area | What works |
| --- | --- |
| Auth & RBAC | Signup creates an organization and its owner; login, rotating refresh tokens, logout, password change/reset, invitations, account lockout after 5 failed logins, rate limiting on credential endpoints. Roles `owner > admin > finance > viewer`. |
| Organizations | Profile, GSTIN/PAN, default currency, payment terms, tax rate, document numbering prefixes/sequences, discount-approval threshold, team management, switching between organizations. |
| Customers | CRUD with contacts, billing address, per-customer terms and currency, activity stats, related invoices/payments/subscriptions. |
| Catalog | Products (service/goods/subscription, HSN/SAC, tax rate) and plans (one-time/monthly/quarterly/semiannual/yearly, flat or per-unit, setup fee, trial days). |
| Quotes | Draft, send, public accept/decline page, mark accepted/declined, convert to invoice. Discounts above the organization threshold require an approval before sending. |
| Subscriptions | Trials, active periods, pause/resume, cancel now or at period end, MRR, invoice generation per period, automatic renewals. |
| Invoices | Draft/sent/partially paid/paid/overdue/void lifecycle, server-side totals, PDF download, email with pay link, reminders, hosted public invoice page. |
| Payments | Razorpay Checkout on the hosted page with signature verification and webhooks; manual payments (bank transfer, UPI, card, cash, cheque); allocations across invoices; reconciliation statuses; refunds (gateway or manual) that re-open invoices. |
| Dunning | Scheduler marks invoices overdue, moves subscriptions to past due and sends reminders at a configurable cadence and cap. |
| Control center | Dashboard KPIs and trends, action center, calendar, approvals, activity feed, global search, audit log with CSV/JSON export, CSV import (customers, products, plans) with dry run. |

Everything above is backed by real endpoints; the UI renders a "coming soon" page for anything else instead of mock data.

---

## Repository layout

```
.
+-- backend/                  FastAPI application (imported as `backend.app`)
|   +-- app/                  api/ core/ models/ repositories/ schemas/ services/
|   +-- alembic/              migrations (run from the repo root with backend/alembic.ini)
|   +-- tests/                pytest suite (SQLite by default, PostgreSQL via TEST_DATABASE_URL)
|   +-- docker/entrypoint.sh  waits for DB, migrates, starts gunicorn
|   +-- Dockerfile            build context = repository root
+-- frontend/                 React + Vite SPA
|   +-- docker/nginx.conf     SPA fallback, /api/ proxy, caching, security headers
|   +-- Dockerfile            build context = frontend/
+-- deploy/Caddyfile          optional automatic-HTTPS front door
+-- docker-compose.yml        local PostgreSQL only
+-- docker-compose.prod.yml   production: db + backend + scheduler + frontend
+-- docker-compose.caddy.yml  overlay adding Caddy (TLS)
+-- .env.production.example   production configuration template
+-- .github/workflows/ci.yml  pytest on PostgreSQL, migrations, tsc, vite build, docker builds
+-- Makefile                  dev / test / build / up-prod shortcuts (`make help`)
+-- docs/                     architecture, development-setup, deployment, operations, api-contract
```

---

## Quick start (development)

Prerequisites: Python 3.12, Node 22 (20+ works), Docker (for PostgreSQL).

```bash
# 1. database
docker compose up -d

# 2. backend (from the repository root)
python3 -m venv backend/venv
source backend/venv/bin/activate            # Windows: backend\venv\Scripts\activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
alembic -c backend/alembic.ini upgrade head
uvicorn backend.app.main:app --reload --port 8000

# 3. frontend (second terminal)
cd frontend
npm ci
cp .env.example .env
npm run dev                                 # http://localhost:5173, /api proxied to :8000
```

Open http://localhost:5173 and click **Sign up** - the first signup creates your organization and
its owner account. API docs: http://localhost:8000/api/v1/docs. Health: http://localhost:8000/api/v1/health.

Tests: `pytest` from the repository root (SQLite), or
`TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/rooman_test pytest` to run on PostgreSQL.
Frontend checks: `cd frontend && npx tsc --noEmit && npm run build`.

Full guide: [`docs/development-setup.md`](docs/development-setup.md).

---

## Production deployment (Docker Compose)

```bash
git clone <repo> rooman-billing && cd rooman-billing
cp .env.production.example .env.production
chmod 600 .env.production
# edit .env.production: SECRET_KEY (openssl rand -hex 32), POSTGRES_PASSWORD, FRONTEND_URL,
# ALLOWED_ORIGINS, SMTP_*, RAZORPAY_* ...
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

This starts PostgreSQL, the API (gunicorn + uvicorn workers, migrations applied on start), one
scheduler container for background jobs and nginx serving the SPA on port 80 with `/api/` proxied
to the API. Put TLS in front of it - the bundled Caddy overlay does it automatically:

```bash
# .env.production: DOMAIN=billing.example.com  ACME_EMAIL=ops@example.com  FRONTEND_BIND=127.0.0.1:8080
docker compose --env-file .env.production -f docker-compose.prod.yml -f docker-compose.caddy.yml up -d --build
```

Then open `https://<DOMAIN>/signup` to create the first organization and owner.
Step-by-step runbook (host sizing, DNS, upgrades, rollback): [`docs/deployment.md`](docs/deployment.md).
Day-2 operations (backups, logs, failures): [`docs/operations.md`](docs/operations.md).

---

## Configuration

All settings are environment variables read by `backend/app/core/config.py` (a `.env` at the repo root
and `backend/.env` are also loaded, the latter winning). In `production`/`staging` the API refuses to
start with an insecure `SECRET_KEY`, `DEBUG=true`, the default `postgres` password, SQLite, or a
`localhost` CORS origin.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development` / `test` / `staging` / `production`. Staging and production enable the safety checks. |
| `DEBUG` | `true` | Must be `false` in production. |
| `SECRET_KEY` | dev placeholder | JWT signing key, >= 32 random chars (`openssl rand -hex 32`). |
| `FRONTEND_URL` | `http://localhost:5173` | Public URL of the web app; used in emails and hosted-page links. |
| `ALLOWED_ORIGINS` | localhost origins | CORS allow-list, comma-separated or JSON array. |
| `API_V1_STR` | `/api/v1` | API prefix. The nginx proxy assumes `/api/`. |
| `BACKEND_HOST` / `BACKEND_PORT` | `0.0.0.0` / `8000` | Bind address for `python -m backend.app.main`; gunicorn binds `0.0.0.0:8000` in the image. |
| `JWT_ALGORITHM` | `HS256` | Access-token algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT lifetime. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Rotating opaque refresh-token lifetime. |
| `INVITE_TOKEN_EXPIRE_HOURS` | `72` | Team invitation validity. |
| `PASSWORD_RESET_EXPIRE_MINUTES` | `60` | Reset-link validity. |
| `PASSWORD_MIN_LENGTH` | `10` | Passwords also need mixed case and a digit. |
| `AUTH_RATE_LIMIT` | `10/minute` | Per-IP limit on signup/login/forgot/reset. |
| `SECURE_COOKIES` | `false` | Set `true` behind HTTPS. |
| `POSTGRES_SERVER` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `localhost` / `5432` / `postgres` / `postgres` / `rooman_billing` | Assembled into the connection string when `DATABASE_URL` is unset. |
| `DATABASE_URL` | unset | Full SQLAlchemy URL (`postgresql+psycopg://...`); overrides the `POSTGRES_*` values. SQLite allowed only outside production. |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `20` | Connection pool per process. |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | empty | Enable online payments when both are set. |
| `RAZORPAY_WEBHOOK_SECRET` | empty | Verifies `X-Razorpay-Signature` on `/api/v1/webhooks/razorpay`. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` | empty / `587` | Outbound mail; empty host disables email and surfaces links in the UI instead. |
| `SMTP_USE_TLS` / `SMTP_USE_SSL` | `true` / `false` | STARTTLS (587) or implicit TLS (465). |
| `EMAIL_FROM_ADDRESS` / `EMAIL_FROM_NAME` | `billing@example.com` / `Rooman Billing` | Sender identity. |
| `SCHEDULER_ENABLED` | `true` | Run background jobs in this process. Exactly one process per deployment. |
| `SCHEDULER_INTERVAL_MINUTES` | `15` | Job cadence. |
| `DUNNING_REMINDER_INTERVAL_DAYS` / `DUNNING_MAX_REMINDERS` | `3` / `3` | Reminder cadence and cap for overdue invoices. |
| `LOG_JSON` | `false` | JSON log lines for log shippers. |
| `WEB_CONCURRENCY` | `2` | (compose/image) gunicorn worker processes. |

The frontend build reads `VITE_API_BASE_URL` (empty = same origin, which is what the Docker image uses)
and `VITE_APP_TITLE`.

---

## Razorpay setup

1. Razorpay Dashboard -> **Account & Settings -> API Keys** -> generate **Live** keys (use Test keys on
   staging). Put them in `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
2. **Account & Settings -> Webhooks -> Add New Webhook**
   - Webhook URL: `https://<your-host>/api/v1/webhooks/razorpay`
   - Active events: `payment.captured`, `payment.failed`, `refund.processed`
   - Secret: generate one (`openssl rand -hex 24`), paste the same value into `RAZORPAY_WEBHOOK_SECRET`.
3. Restart the API and scheduler containers (`docker compose ... up -d`).
4. Verify: `GET https://<your-host>/api/v1/meta/integrations` returns `razorpay.enabled: true`; pay a test
   invoice from its hosted page (`/pay/<token>`) and confirm the payment shows as `succeeded` /
   `auto_matched`; the Razorpay webhook log should show `200 {"received": true}`.

Without keys the platform still runs - invoices are settled by recording manual payments.

## Email (SMTP) setup

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM_ADDRESS` and either
`SMTP_USE_TLS=true` (port 587, STARTTLS) or `SMTP_USE_SSL=true` (port 465). Any provider works
(Amazon SES, SendGrid, Postmark, Google Workspace). Make sure the from-domain has SPF/DKIM set up.
When SMTP is not configured, invitation and password-reset links are returned to the administrator in
the UI, and invoice/quote emails are skipped (the hosted links can still be copied and shared).

---

## Backups

Only PostgreSQL holds state (PDFs are rendered on demand). Dump it from the running stack:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' | gzip > rooman_$(date +%F).sql.gz
```

`make backup` does the same into `backups/`. Restore procedure and retention advice are in
[`docs/operations.md`](docs/operations.md).

---

## Security notes

- Never run with `ENVIRONMENT=development` or `DEBUG=true` on the internet; the production checks exist for a reason.
- Terminate TLS in front of the stack and set `FRONTEND_URL`/`ALLOWED_ORIGINS` to the `https://` origin, `SECURE_COOKIES=true`.
- Passwords are bcrypt-hashed (after SHA-256 pre-hashing); refresh, invite and reset tokens are stored only as SHA-256 hashes; refresh-token reuse revokes the whole chain.
- Razorpay webhooks and Checkout callbacks are HMAC-verified; webhook events are deduplicated by event id.
- The database is not published outside the compose network; the API is reachable only through nginx.
- Rotate `SECRET_KEY`, the DB password and gateway secrets per the procedure in `docs/deployment.md`.
- Keep `.env.production` at mode 600 and out of git (it is ignored).

---

## Documentation

- [Architecture](docs/architecture.md)
- [Development setup](docs/development-setup.md)
- [Deployment runbook](docs/deployment.md)
- [Operations](docs/operations.md)
- [API contract](docs/api-contract.md)
