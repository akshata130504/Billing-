# Rooman Billing: Project Guide

This is the single entry point for anyone working on Rooman Billing. It covers what the product does, how
the code is organized, how to run, test and deploy it, how production is set up, and what is still open.
The other files in [`docs/`](.) go deeper on specific topics; they are linked where relevant.

> Status (October 2026): the code is **fully modular** (19 product modules) and running in production at
> **https://billing.futureacad.ae**. Production source repository: **`akshata130504/Billing-`** (`main`).

---

## Contents

1. [What Rooman Billing is](#1-what-rooman-billing-is)
2. [Tech stack](#2-tech-stack)
3. [Architecture at a glance](#3-architecture-at-a-glance)
4. [Repository layout](#4-repository-layout)
5. [Modules (the modular structure)](#5-modules-the-modular-structure)
6. [Shared core](#6-shared-core)
7. [Data model](#7-data-model)
8. [Users, roles and sign-in](#8-users-roles-and-sign-in)
9. [Multi-tenancy and security](#9-multi-tenancy-and-security)
10. [Background jobs (scheduler)](#10-background-jobs-scheduler)
11. [Payments, email, PDFs and AI](#11-payments-email-pdfs-and-ai)
12. [Frontend](#12-frontend)
13. [Configuration (environment variables)](#13-configuration-environment-variables)
14. [Local development](#14-local-development)
15. [Testing](#15-testing)
16. [Production: server, deploy, rollback](#16-production-server-deploy-rollback)
17. [Operations: health, logs, backups](#17-operations-health-logs-backups)
18. [Git workflow and repositories](#18-git-workflow-and-repositories)
19. [How to add or change a module](#19-how-to-add-or-change-a-module)
20. [Open items and known issues](#20-open-items-and-known-issues)
21. [Further documentation](#21-further-documentation)

---

## 1. What Rooman Billing is

A **multi-tenant billing and subscription management** web app for Indian SMEs. Each organization
(tenant) manages its own customers, catalog, quotes, subscriptions, invoices and payments; Rooman's
platform team runs the whole service from a separate **Super Admin console**.

Main capabilities:

| Area | What it does |
| --- | --- |
| Customers | Customer records with contacts, billing address, per-customer terms and currency, activity history |
| Products & Plans | Products (service/goods/subscription, HSN/SAC, tax rate), plans (one-time, monthly … yearly, flat or per-unit, setup fee, trial days), pricing simulator, offerings and price books |
| Quotes & CPQ | Draft → send → public accept/decline page → convert to invoice; discounts above a threshold need approval |
| Subscriptions & Usage | Trials, renewals, pause/resume, cancel, plan changes with proration, metered usage, MRR |
| Invoices & Credit Notes | Full lifecycle (draft/sent/partially paid/paid/overdue/void), GST totals, PDF, email with pay link, public invoice page, credit notes |
| Payments | Razorpay online payments (hosted page, signature verification, webhooks), manual payments, allocation across invoices, refunds |
| Reconciliation | Matching payments to invoices, reconciliation summary |
| Collections & Dunning | Ageing, collection work, automatic overdue marking and reminder cadence |
| Customer Portal | Customer-facing portal (login, invoices, payments, subscriptions, profile) and hosted payment pages |
| Customer Lifecycle | Lifecycle timeline per customer |
| Expenses, Projects, Timesheets | Expense tracking (incl. recurring), projects, time entries that can be invoiced |
| Reports & Revenue Intelligence | Financial reports and revenue analytics |
| AI Billing Assistant | AI help (ask, draft, writing) and the "Roomi" chat assistant (Google Gemini) |
| Automation | Automation rules, schedules, document templates, number series, signed outgoing webhooks |
| Integrations | Per-organization integration settings (encrypted credentials) |
| Mobile & Desktop | Device registration and native-app bootstrap endpoints |
| Control Center | Dashboard KPIs, action center, approvals, calendar, audit log, global search, CSV import |

**Business model in the app:** a new organization signs up (email OTP verified) and gets a **free trial**
with every module open. After the trial it requests a subscription; a Platform Administrator decides
which **modules and seats** it gets. Modules not granted are hidden in the UI and refused by the API.

---

## 2. Tech stack

**Backend**: Python 3.12, FastAPI 0.136, SQLAlchemy 2.0, Pydantic v2 (+ pydantic-settings), Alembic,
PostgreSQL 16 (psycopg 3), Redis 5 (rate limiting / single-use keys), APScheduler (background jobs),
ReportLab (PDF), Razorpay SDK, PyJWT, bcrypt, cryptography (Fernet keyring), slowapi (rate limits),
httpx, Sentry SDK, gunicorn + uvicorn workers.

**Frontend**: React 18, TypeScript 5, Vite 6, Tailwind CSS 3, React Router 7, TanStack Query 5, Axios,
lucide-react icons, react-phone-number-input. Tests: Vitest 3 + jsdom.

**Infrastructure**: Docker images (API and web), `docker compose` production stack (PostgreSQL, Redis,
backend, scheduler, backup, nginx frontend), hosted on a Proxmox LXC container (CT111).

---

## 3. Architecture at a glance

```
Browser ──HTTPS──> nginx (frontend container, port 80)
                     ├── /            React single-page app (tenant app, /admin sign-in)
                     ├── /superadmin  Platform (Super Admin) console, separate page + separate auth
                     └── /api/v1/*  ──> backend container (FastAPI, gunicorn)
                                          ├── PostgreSQL 16 (db container, row-level security)
                                          └── Redis (rate limits, single-use tokens)
scheduler container (same API image) ── runs renewals, trials, overdue, dunning every N minutes
backup container (postgres image) ───── nightly pg_dump + uploads archives (+ optional offsite)
```

- **One origin**: the tenant app, the Super Admin console and the API are all served from the same domain.
- The **backend** is a single FastAPI app (`backend/app/main.py`). Every router is registered in
  [`backend/app/api/v1/api_router.py`](../backend/app/api/v1/api_router.py) under `/api/v1`.
- On start the backend container **runs Alembic migrations** (`backend/docker/entrypoint.sh`) as the
  database owner, then serves requests as a **least-privilege runtime role** (`APP_POSTGRES_USER`).
- The API contract between frontend and backend is [`docs/api-contract.md`](api-contract.md).

More detail: [`docs/architecture.md`](architecture.md).

---

## 4. Repository layout

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                FastAPI app, middleware, error handling, scheduler start
│   │   ├── api/                   deps.py (auth/tenant context), v1/api_router.py, v1/endpoints/
│   │   │                          (endpoints/ = shared-core routers + forwarding aliases of moved ones)
│   │   ├── modules/<module>/      ← the 19 product modules (routers + services + schemas)
│   │   ├── services/              shared-core services (+ forwarding aliases of moved services)
│   │   ├── models/                SQLAlchemy models (one file per area)
│   │   ├── schemas/               Pydantic request/response models
│   │   ├── core/                  config, security, encryption, rate limits, logging, modules.json
│   │   ├── repositories/          data-access helpers
│   │   ├── website/  app_ui/  cli/
│   ├── alembic/                   migrations (run with -c backend/alembic.ini from the repo root)
│   ├── tests/                     pytest suite (+ tests/architecture/ module map and alias checks)
│   ├── docker/entrypoint.sh       wait for DB → migrate → start gunicorn
│   └── Dockerfile                 build context = repository root
├── frontend/
│   ├── src/
│   │   ├── modules/<module>/      ← product module pages
│   │   ├── pages/                 shared pages (auth, dashboard, settings, control center, public …)
│   │   │                          + re-export aliases of moved pages
│   │   ├── platform/              Super Admin console app
│   │   ├── components/            shared UI (common/Button, Input, layout/Header, Sidebar …)
│   │   ├── services/              API clients (apiClient.ts, authService.ts, …)
│   │   ├── routes/index.tsx       all app routes
│   │   ├── entitlements/          modules.json (module keys and nav items)
│   │   └── test/architecture/     moduleMap.ts and import report
│   ├── docker/nginx.conf          SPA fallback, /api proxy, caching, security headers
│   └── Dockerfile                 build context = frontend/
├── deploy/                        backup.sh, deploy-poll.sh, check-env.sh, db-least-privilege.sh,
│                                  systemd units, Caddyfile, sql/
├── docker-compose.yml             local PostgreSQL only
├── docker-compose.prod.yml        production stack
├── docker-compose.caddy.yml       optional overlay: Caddy for automatic HTTPS
├── .env.production.example        production configuration template (all settings documented)
├── Makefile                       shortcuts (`make help`)
└── docs/                          this guide and the topic documents
```

---

## 5. Modules (the modular structure)

The product is split into **19 modules**, listed in
[`backend/app/core/modules.json`](../backend/app/core/modules.json) (mirrored in
`frontend/src/entitlements/modules.json`). A module is a **feature** (roughly one sidebar section), not a
single button or tab: everything on the Invoices pages belongs to the invoices module.

Each module owns:
- **Backend**: `backend/app/modules/<key>/`, with its routers (API endpoints) and its domain services
  (business logic), sometimes schemas.
- **Frontend**: `frontend/src/modules/<key>/`, with its pages and components.

| Module key | Backend `modules/…` (main files) | Frontend `src/modules/…` | API prefixes |
| --- | --- | --- | --- |
| customers | customers/ router, service, schemas | customers/ | `/customers` |
| products | products/ products & plans routers, service, pricing_engine, catalog_cpq_service, pricing & catalog routers | products/ (+ plans-pricing/) | `/products`, `/plans`, `/pricing`, `/catalog` |
| quotes | quotes/ quotes & cpq routers, service, quote_pdf, public router | quotes/ | `/quotes`, `/cpq`, `/public/quotes` |
| subscriptions | subscriptions/ router, service, change/meter/trial/offering services, proration_calculator, changes/meters/trials routers | subscriptions/ (+ usage/, proration/) | `/subscriptions`, `/meters`, `/trials` |
| invoices | invoices/ invoices & credit-notes routers, service, credit_service, invoice_pdf, public router | invoices/ | `/invoices`, `/credit-notes`, `/public/invoices` |
| payments | payments/ router, service, payment_method_service, razorpay_gateway, payment-methods & webhooks routers | payments/ | `/payments`, `/webhooks` |
| reconciliation | inside **payments** (`/payments/reconciliation`) | inside payments | `/payments/reconciliation` |
| collections | collections/ collections & dunning routers, service, dunning_service | collections/ | `/collections` |
| dunning | inside **collections** (backend) | dunning/ | `/dunning` |
| customer_portal | customer_portal/ portal & checkout routers, service, checkout_service | customer_portal/ (+ hosted-payment-pages/, portal-customer/) | `/portal`, `/checkout` |
| customer_lifecycle | customer_lifecycle/ router, service | customer_lifecycle/ | `/lifecycle` |
| expenses | expenses/ | expenses/ | `/expenses` |
| projects | projects/ | projects/ | `/projects` |
| timesheets | timesheets/ | timesheets/ | `/timesheets` |
| reports | reports/ router, service | reports/ (+ revenue-intelligence/) | `/reports` |
| ai_billing | ai_billing/ ai & chat routers, service, roomi_service | ai_billing/ | `/ai`, `/chat` |
| automation | automation/ router, service (customization), outbox_processor | automation/ (+ customization/) | `/automation`, customization routes |
| integrations | integrations/ router, service | integrations/ | `/settings/integrations` |
| platforms | platforms/ router, service (devices) | platforms/ | `/devices`, `/mobile` |

### Old paths still work (forwarding aliases)

When a file moved into a module, its **old path became a small forwarding alias** (for example
`backend/app/services/invoice_service.py` now just points at `backend/app/modules/invoices/service.py`).
Both paths give the **same module object**, so old imports, `mock.patch("backend.app.services.…")` in
tests, and the circular imports between invoices/subscriptions/payments/timesheets keep working. The
frontend does the same with one-line re-exports in `src/pages/<old folder>/`.

**Rule for new code:** import from the module path (`backend.app.modules.<key>…`,
`src/modules/<key>/…`). Inside a module, never import the module's own old paths (a test enforces this).

### Architecture tests that guard the structure

- `backend/tests/architecture/module_map.py` lists which files belong to which module.
- `backend/tests/test_<module>*_module_aliases.py` check, per module, that: the package `__init__` only has
  a docstring; old paths are real forwarding aliases; old and new path are one object; patching the old
  path reaches the new module; routes are registered exactly once with unchanged counts; importing any
  path first loads each module once; nothing in the module imports its own old paths.
- `frontend/src/test/architecture/moduleMap.ts` + `importReport.test.ts`, and an `aliases.test.ts` in each
  old page folder.

---

## 6. Shared core

Code that every module uses stays outside the modules, on purpose:

- **Identity & access**: `auth` (sign-up with email OTP, login, MFA/TOTP, sessions, refresh, password
  reset, invitations), `rooman_one_login` (OpenID Connect), `users`, `organization` (profile, team,
  switching), `subscription_requests` / `platform_access` (the organization's own Billing subscription and
  module access).
- **Platform (Super Admin) console**: `platform_*` routers and services (organizations, staff, website CMS,
  app-UI visual editor, access grants, subscription requests, overview).
- **Control center**: `dashboard`, `approvals`, `audit_logs`, `search`, `imports`, `notifications`.
- **Public**: `public_website` (landing page content).
- **Helpers**: money, GST, numbering, currency totals, timezones, pagination, email, audit,
  platform_audit, idempotency, unit_of_work, durable jobs, scheduler, org access/lifecycle.

---

## 7. Data model

SQLAlchemy models live in `backend/app/models/` (one file per area): identity (organizations, users,
memberships, refresh tokens, login throttles), catalog, catalog_cpq, customers, quotes, subscriptions,
billing_cycles, proration, meters, trials, invoices, credits, payments, checkout, collections, dunning,
portal, lifecycle, expenses, projects, timesheets, ai, customization, integrations, devices, events
(outbox), notifications, governance (audit, approvals), platform, access_grants, subscription_access,
app_ui, website.

- IDs are UUID strings (`String(36)`).
- Every tenant table carries `organization_id`; PostgreSQL **row-level security** enforces isolation.
- Schema changes are **Alembic migrations only** (`backend/alembic/versions/`). Never edit a migration
  that has shipped; add a new one. The current head is checked by `GET /api/v1/health/ready`.

---

## 8. Users, roles and sign-in

**Tenant roles** (per organization membership), highest first: `owner` > `admin` > `finance` > `viewer`.
Endpoints declare the minimum role they need.

**Organization status**: `active` (incl. trial / trial expired as computed states), `pending_approval`,
`rejected`, `suspended`, `pending_deletion`, `deleted`. Status gates every request (for example, a
suspended organization is read-only for admins and blocked for others).

**Sign-in options**
- **Email + password** with optional **TOTP two-factor** (login returns an MFA challenge when enabled).
  Failed logins are throttled per (email, IP); credential endpoints are rate limited.
- **Sign in with Rooman One** (OpenID Connect, authorization code + PKCE). Off until the `OIDC_*`
  settings are set; enabled in production. The first sign-in of a Rooman One organization creates it in
  Billing with the **same ids** (user `sub`, organization `org_id`), with a free trial. Role mapping: the
  founding `admin` → owner, `admin` → admin, `staff` → finance, `viewer`/unknown → viewer. An email that
  already has its own Billing account is refused (never merged). Details:
  [`docs/rooman-one-sign-in.md`](rooman-one-sign-in.md).
- **Super Admin console** (`/superadmin`): separate staff accounts, separate token secret
  (`PLATFORM_JWT_SECRET`), password sign-in. See
  [`docs/platform-administration-design.md`](platform-administration-design.md) and
  [`docs/platform-console-deployment.md`](platform-console-deployment.md).
- **Customer portal**: customers of an organization sign in to `/portal` with their own portal accounts.

Tokens: short-lived access token (JWT) + rotating refresh token (stored hashed). The tenant frontend
keeps them in `localStorage` (`rooman.access_token` / `rooman.refresh_token`).

---

## 9. Multi-tenancy and security

- **Tenant isolation**: application-level tenant context **and** PostgreSQL row-level security (RLS). The
  app connects as a least-privilege role (`NOSUPERUSER`, `NOBYPASSRLS`); migrations run as the owner role.
  See [`docs/database-security.md`](database-security.md).
- **Encryption at rest** for integration credentials and TOTP seeds: Fernet keyring `ENCRYPTION_KEYS`
  (rotation command: `python -m backend.app.core.encryption rotate`).
- **Rate limits** (slowapi, Redis-backed in production): auth, public pages, public actions, webhooks.
- **Security headers** in nginx; strict CORS (`ALLOWED_ORIGINS`), trusted hosts and proxies.
- **Audit**: every important action is written to the tenant audit log; platform actions to an
  append-only platform audit log.
- **Webhooks**: Razorpay webhook signatures are verified; outgoing automation webhooks are signed.
- Further reading: [`docs/security-roadmap.md`](security-roadmap.md),
  [`docs/production-readiness.md`](production-readiness.md).

---

## 10. Background jobs (scheduler)

The `scheduler` container runs `backend/app/services/scheduler.py` every `SCHEDULER_INTERVAL_MINUTES`
(default 15), under a database lock so only one run happens at a time. Each organization is processed on
its own local date (organization timezone). One run:

1. Expire organization free trials that have ended (platform metadata).
2. Apply scheduled subscription changes due today (before renewals).
3. Evaluate subscription trials: convert/charge, fallback plans, cancel-at-period-end, reminders.
4. Finalize metered usage, then renew subscriptions that are due (builds the renewal invoice).
5. Mark open invoices past their due date as **overdue** (owning subscription → past due).
6. Dunning: reminders at `DUNNING_REMINDER_INTERVAL_DAYS`, up to `DUNNING_MAX_REMINDERS`.

Inactive organizations (suspended, paused jobs) are skipped. Each run writes a heartbeat that
`/api/v1/health/ready` reports.

---

## 11. Payments, email, PDFs and AI

- **Razorpay**: hosted checkout on the public invoice / hosted payment pages; payment signature checked;
  webhook `POST /api/v1/webhooks/razorpay` (requires `RAZORPAY_WEBHOOK_SECRET` whenever keys are set).
  Manual payments (bank transfer, UPI, card, cash, cheque) are recorded by staff; online (razorpay)
  payments can only come through the hosted page.
- **Email**: SMTP (`SMTP_*`, `EMAIL_FROM_*`). Used for sign-up OTP, invitations, password reset,
  invoices/quotes with links, reminders. See [`docs/email-setup-guide.md`](email-setup-guide.md).
- **PDFs**: ReportLab (`modules/invoices/invoice_pdf.py`, `modules/quotes/quote_pdf.py`).
- **AI**: Google Gemini (`GEMINI_API_KEY`, `GEMINI_MODEL`) for the AI Billing Assistant and the Roomi
  chatbot (`modules/ai_billing/`).

---

## 12. Frontend

- **Entry and routes**: `frontend/src/routes/index.tsx` (lazy-loaded pages). `/admin` and `/login` are the
  tenant sign-in; `/auth/rooman-one` completes Rooman One sign-in; `/portal/*` is the customer portal;
  `/superadmin` is a separate HTML page for the platform console.
- **API access**: `src/services/apiClient.ts` (Axios, base `/api/v1`, automatic token refresh).
- **State**: TanStack Query for server data; `useAuth` hook for the session.
- **UI components**: `src/components/common/` (one shared `Button` with `variant`, `size`,
  `leadingIcon`/`trailingIcon`, `isLoading`; `Input`, `Toast`, `LoadingState` …) and
  `src/components/layout/` (Header, Sidebar, AppLayout).
- **Theme**: Tailwind with Rooman colours, defined as CSS variables in `src/index.css` and named in
  `tailwind.config.js`: navy `#11194F`, indigo `#25247A` / `#3F51C9`, pink accent `#E83E8C`, page
  background `#F7F8FC`. Fonts: **Inter** (text), **JetBrains Mono** (numbers/code). Dark mode via the
  `dark` class. Primary call-to-action buttons use a navy → indigo → pink gradient.
- **Button convention**: an icon, when a button has one, sits **before** the label, is
  `w-4 h-4 shrink-0`, and the button is `inline-flex items-center gap-2`. Not every button needs an icon.
- **Module access in the UI**: the sidebar shows only modules the organization has
  (`src/entitlements/`).

---

## 13. Configuration (environment variables)

Production settings live in **`.env.production`** on the server (never in git). Every variable is
documented in [`.env.production.example`](../.env.production.example). Grouped:

| Group | Variables |
| --- | --- |
| App | `PROJECT_NAME`, `ENVIRONMENT`, `DEBUG`, `FRONTEND_URL`, `ALLOWED_ORIGINS`, `ALLOWED_HOSTS`, `TRUSTED_PROXIES`, `DOMAIN`, `FRONTEND_BIND`, `WEB_CONCURRENCY`, `IMAGE_TAG`, `API_IMAGE`, `WEB_IMAGE` |
| Secrets | `SECRET_KEY`, `PLATFORM_JWT_SECRET`, `ENCRYPTION_KEYS`, `ENCRYPTION_LEGACY_SECRET_KEY_FALLBACK` |
| Auth | `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `INVITE_TOKEN_EXPIRE_HOURS`, `PASSWORD_RESET_EXPIRE_MINUTES`, `PASSWORD_MIN_LENGTH`, `SECURE_COOKIES`, `JWT_ALGORITHM` |
| Rooman One | `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI` |
| Database | `POSTGRES_SERVER/PORT/USER/PASSWORD/DB`, `APP_POSTGRES_USER/PASSWORD` (runtime role), `MIGRATION_*`, `DATABASE_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `POSTGRES_SSL*` (remote DB) |
| Redis & limits | `REDIS_URL`, `AUTH_RATE_LIMIT`, `PUBLIC_RATE_LIMIT`, `PUBLIC_ACTION_RATE_LIMIT`, `WEBHOOK_RATE_LIMIT` |
| Email | `SMTP_HOST/PORT/USERNAME/PASSWORD/USE_TLS/USE_SSL`, `SMTP_TIMEOUT_SECONDS`, `EMAIL_FROM_ADDRESS/NAME` |
| Payments | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` |
| Scheduler | `SCHEDULER_ENABLED`, `SCHEDULER_INTERVAL_MINUTES`, `DUNNING_REMINDER_INTERVAL_DAYS`, `DUNNING_MAX_REMINDERS` |
| AI | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| Backups | `BACKUP_CRON`, `BACKUP_RETENTION_DAYS`, `OFFSITE_BACKUP_REMOTE`, `OFFSITE_S3_*`, `OFFSITE_REQUIRED`, `OFFSITE_RETENTION_DAYS` |
| Monitoring | `LOG_JSON`, `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `ALERT_WEBHOOK_URL`, `ALERT_DEDUP_SECONDS` |
| Container limits | `*_MEM_LIMIT`, `*_CPUS` |
| Auto-deploy poller (not used now) | `GITHUB_PAT`, `GITHUB_REPO`, `READINESS_URL`, `READINESS_TIMEOUT`, `PREDEPLOY_BACKUP_KEEP` |

`sh deploy/check-env.sh .env.production` checks required settings (prints names, never values).

---

## 14. Local development

Prerequisites: Python 3.12, Node 22, Git. Docker is optional (SQLite works for development).

```bash
# backend (from the repository root)
python -m venv backend/venv
source backend/venv/bin/activate            # Windows PowerShell: backend\venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env        # for SQLite set DATABASE_URL=sqlite:///./dev_rooman_billing.db
alembic -c backend/alembic.ini upgrade head
uvicorn backend.app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm ci
npm run dev                                 # http://localhost:5173, /api proxied to :8000
```

- API docs: http://localhost:8000/api/v1/docs · health: `/api/v1/health/ready`.
- **Sign-up needs an email code.** Without real SMTP, run the local mail catcher and point SMTP at it:
  `python scripts/local_smtp_server.py` (on Windows prefix `PYTHONIOENCODING=utf-8`), then set
  `SMTP_HOST=127.0.0.1`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`. The code is printed in its output.
- **Demo data**: `API=http://127.0.0.1:8000 EMAIL=… PASSWORD=… python scripts/seed_demo.py` after
  creating an account (see [known issues](#20-open-items-and-known-issues)).
- PostgreSQL locally: `docker compose up -d` (PostgreSQL 16 on 5432).
- Full guide: [`docs/development-setup.md`](development-setup.md).

---

## 15. Testing

| What | Command | Size (Oct 2026) |
| --- | --- | --- |
| Backend tests | `python -m pytest -q` (from repo root; SQLite by default) | 2,487 passed, 101 skipped, ~60 min |
| Backend on PostgreSQL | `TEST_DATABASE_URL=postgresql+psycopg://… pytest` (runs the RLS checks too) | |
| One area only | `python -m pytest backend/tests -k invoice` | minutes |
| Lint | `python -m ruff check backend` | |
| Frontend type check | `cd frontend && npx tsc --noEmit` | |
| Frontend tests | `cd frontend && npx vitest run` | 1,008 passed |
| Frontend build | `cd frontend && npm run build` | |

Tips:
- **Never run two backend test runs in the same folder at once**: they share one SQLite test database
  file and break each other.
- Keep at least ~10 GB free disk; a full disk shows up as `database or disk is full`.
- Don't let the PC sleep during a full run; a suspended run produces false failures (timeouts).
- **GitHub Actions is currently turned off** on `akshata130504/Billing-`, so run the tests locally before
  merging. The workflows (`.github/workflows/ci.yml`, `deploy.yml`) are kept for when it is re-enabled.

---

## 16. Production: server, deploy, rollback

**Where it runs**
- Proxmox host → LXC container **CT111** (`akshata-app`), folder **`/opt/rooman-billing`** (a git
  checkout of `akshata130504/Billing-`, remote `origin`).
- Public URL **https://billing.futureacad.ae**; the frontend container listens on port 80
  (`FRONTEND_BIND`). TLS can be added with the Caddy overlay (`docker-compose.caddy.yml`).
- Containers: `db`, `redis`, `backend`, `scheduler`, `backup`, `frontend`. Images are **built on the
  server** from the checked-out code and tagged with the git commit (`IMAGE_TAG` in `.env.production`).
  `API_IMAGE=rooman-billing-api`, `WEB_IMAGE=rooman-billing-web`.

**Deploy a new version** (run in the CT111 console, one line at a time):

```sh
cd /opt/rooman-billing
git pull origin main
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > /root/predeploy-$(date +%Y%m%d-%H%M).dump
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$(git rev-parse --short HEAD)/" .env.production
docker compose --env-file .env.production -f docker-compose.prod.yml build backend frontend
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
curl -s http://127.0.0.1/api/v1/health/ready
```

Check: the health response says `"ready":true`, `docker ps` shows the new tag on the api/web images,
and a few pages open. Don't use `export IMAGE_TAG=…` in the shell: it overrides the file.

**Roll back** to an earlier build (its images stay on the server; list with
`docker images | grep rooman-billing`):

```sh
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=<previous short sha>/" .env.production
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

Migrations only go forward; if a migration ever has to be undone, restore the pre-deploy dump (see
[`docs/operations.md`](operations.md)).

**Changing a setting** (for example `OIDC_*`, SMTP): edit `.env.production` with `nano`, then
`docker compose --env-file .env.production -f docker-compose.prod.yml up -d backend scheduler`.

**Automatic deploys (optional, not active)**: `deploy/deploy-poll.sh` + `rooman-billing-poll.timer` can
pull images that GitHub Actions publishes to GHCR and roll back on failure. That needs GitHub Actions on.
See [`docs/deployment.md`](deployment.md).

---

## 17. Operations: health, logs, backups

- **Health**: `GET /api/v1/health` (alive) and `GET /api/v1/health/ready` (database, migrations at
  head, scheduler heartbeat, feature flags). `GET /api/v1/auth/rooman-one` shows whether Rooman One
  sign-in is enabled.
- **Logs**: `docker compose --env-file .env.production -f docker-compose.prod.yml logs backend --tail 100`
  (also `scheduler`, `frontend`, `backup`). JSON logs when `LOG_JSON=true`.
- **Backups**: the `backup` container runs `deploy/backup.sh` nightly (`BACKUP_CRON`, default 01:15 UTC)
  and at start: `pg_dump` (custom format, verified), `uploads_<date>.tar.gz` and
  `private_uploads_<date>.tar.gz`, local retention `BACKUP_RETENTION_DAYS` (30). With
  `OFFSITE_BACKUP_REMOTE` set it also copies them to S3-compatible storage (Cloudflare R2, Backblaze B2,
  AWS S3 …). Plus the manual `/root/predeploy-*.dump` taken before each deploy.
- **Restore** and the full runbook: [`docs/operations.md`](operations.md).

---

## 18. Git workflow and repositories

| Repository | Role |
| --- | --- |
| **`akshata130504/Billing-`** | **Production source.** CT111 deploys its `main`. All PRs go here. |
| `rooman-itsd/Rooman-Billing` | Original upstream repository (private). Its `main` is fully contained in ours. |

Workflow:
1. Branch from the latest `main` (`feature/…`, `fix/…`, `refactor/…`, `docs/…`).
2. Commit, run backend + frontend tests locally, push, open a PR into `main`.
3. Merge after review → deploy on CT111 (section 16).

Bring new upstream work into ours:

```sh
git remote add rooman https://github.com/rooman-itsd/Rooman-Billing.git   # once
git fetch rooman && git checkout main && git pull origin main
git merge rooman/main            # resolve conflicts if any, run tests
git push origin main
```

Merged history so far: #1 configurable image owner · #2 backup container fix (private uploads mount) ·
#3 Sign in with Rooman One · #4–#6 modularization (all 19 modules) · #7 icon button alignment.

---

## 19. How to add or change a module

**Change an existing feature**: work in its module folders (`backend/app/modules/<key>/`,
`frontend/src/modules/<key>/`) and run its tests (`pytest backend/tests -k <key>`).

**Add a new product module**:
1. Add its key, label, nav items and API prefixes to `backend/app/core/modules.json` and
   `frontend/src/entitlements/modules.json`.
2. Backend: create `backend/app/modules/<key>/__init__.py` (docstring only), `router.py` (an `APIRouter`
   named `router`), `service.py` (logic), and register it in `backend/app/api/v1/api_router.py`
   (`ROUTERS`). Models go in `backend/app/models/`, with an Alembic migration for new tables
   (`alembic -c backend/alembic.ini revision --autogenerate -m "…"`, then review it). New tenant tables
   need `organization_id` and an RLS policy (see existing migrations).
3. Frontend: pages in `frontend/src/modules/<key>/`, routes in `src/routes/index.tsx`, sidebar entry.
4. Add the files to `backend/tests/architecture/module_map.py` and
   `frontend/src/test/architecture/moduleMap.ts`; write tests.

**Moving a file into a module**: keep a forwarding alias at the old path (copy the pattern from any
`backend/app/services/<moved>.py`), add the module-map entry and an alias test
(`backend/tests/test_<key>_module_aliases.py` shows the template).

---

## 20. Open items and known issues

Production readiness (to do):
- **Rotate leaked secrets**: the Gmail SMTP app password, `APP_POSTGRES_PASSWORD`, `PLATFORM_JWT_SECRET`
  and `SECRET_KEY` were exposed in a chat. For `SECRET_KEY`, first move stored secrets to
  `ENCRYPTION_KEYS` and run the `rotate` command (see [`docs/database-security.md`](database-security.md)
  §3), otherwise stored 2FA seeds and integration credentials become unreadable.
- **Off-site backups**: `OFFSITE_BACKUP_REMOTE` is not set yet; backups exist only on CT111.
- **Rooman One**: enabled; confirm one full end-to-end sign-in with a Rooman One account whose email is not
  already registered in Billing.
- **GitHub Actions** is off; tests are run locally.

Known issues:
- `scripts/seed_demo.py` is partly outdated: newer validation rejects back-dated quotes and manually
  recorded "razorpay" payments, so those demo records are skipped.
- Dashboard: the "Total Invoices" card's overdue count and the Payment Status chart's overdue count can
  differ (different date ranges or a bug; to be checked).
- `scripts/local_smtp_server.py` crashes on Windows consoles unless `PYTHONIOENCODING=utf-8` is set.
- Frontend tests can time out when the machine is busy; re-run the failing file alone.

---

## 21. Further documentation

| File | Topic |
| --- | --- |
| [`architecture.md`](architecture.md) | Architecture in depth |
| [`api-contract.md`](api-contract.md) | API contract between frontend and backend |
| [`development-setup.md`](development-setup.md) | Local setup, migrations, tests |
| [`deployment.md`](deployment.md) | Production deployment, settings, secret rotation |
| [`operations.md`](operations.md) | Backups, restore, rollback, monitoring, pre-launch checklist |
| [`database-security.md`](database-security.md) | RLS, least-privilege roles, encryption keyring |
| [`production-readiness.md`](production-readiness.md) | Production readiness review |
| [`security-roadmap.md`](security-roadmap.md) | Security roadmap |
| [`platform-administration-design.md`](platform-administration-design.md) | Super Admin console design |
| [`platform-console-deployment.md`](platform-console-deployment.md) | Super Admin console deployment |
| [`rooman-one-sign-in.md`](rooman-one-sign-in.md) | Sign in with Rooman One |
| [`email-setup-guide.md`](email-setup-guide.md) | Email (SMTP) setup |
| [`browser-qa-checklist.md`](browser-qa-checklist.md) | Manual browser QA checklist |
