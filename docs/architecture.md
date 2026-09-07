# Rooman Billing - Architecture

This document describes the system as built. The request/response shapes it refers to are
specified in [`api-contract.md`](api-contract.md); nothing here supersedes that contract.

## 1. Overview

Rooman Billing is a multi-tenant SaaS billing platform: one deployment serves many
**organizations**, each with its own users (via memberships), customers, catalog, quotes,
subscriptions, invoices, payments and audit trail.

```
                  HTTPS (Caddy / any TLS proxy)
                              |
                 +------------v-------------+
                 | frontend (nginx)         |   static React SPA
                 |   /      -> index.html   |
                 |   /api/  -> backend      |
                 +------------+-------------+
                              | http://backend:8000
        +---------------------v----------------------+
        | backend (gunicorn + uvicorn workers)       |   SCHEDULER_ENABLED=false
        | FastAPI, WEB_CONCURRENCY processes         |
        +---------------------+----------------------+
                              | SQLAlchemy / psycopg
        +---------------------v----------------------+     +--------------------------+
        | PostgreSQL 16                              |<----| scheduler (same image)   |
        +--------------------------------------------+     | SCHEDULER_ENABLED=true   |
                                                           +--------------------------+
   External: Razorpay (Checkout + REST + webhooks), SMTP relay
```

Two container images are produced: `rooman-billing-api` (`backend/Dockerfile`, context = repo
root) and `rooman-billing-web` (`frontend/Dockerfile`, context = `frontend/`). The API image is
reused for the scheduler process.

## 2. Repository layout

```
backend/
  app/
    main.py                 FastAPI factory: CORS, exception handlers, router mount, lifespan
    api/
      deps.py               get_db, get_current_user, require_role(min_role), tenant scoping
      v1/api_router.py      aggregates endpoint routers under /api/v1
      v1/endpoints/*.py     thin HTTP controllers (one module per domain)
    core/
      config.py             Settings (pydantic-settings) + production safety validator
      database.py           engine, SessionLocal, Base, check_db_health()
      security.py           bcrypt password hashing, JWT access tokens, opaque token helpers
      exceptions.py         AppException hierarchy + error envelope handler
      logging.py            stdlib logging setup (LOG_JSON toggles JSON lines)
    models/                 SQLAlchemy models grouped by domain
      base.py               UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin
      identity.py           Organization, User, Membership, RefreshToken, PasswordResetToken
      customers.py          Customer, CustomerContact
      catalog.py            Product, Plan
      quotes.py             Quote, QuoteItem
      subscriptions.py      Subscription
      invoices.py           Invoice, InvoiceItem
      payments.py           Payment, PaymentAllocation, Refund, WebhookEvent
      governance.py         ApprovalRequest, AuditLog, ImportJob
    repositories/           query objects; every method takes/filters organization_id
    schemas/                Pydantic v2 request/response DTOs (money as strings)
    services/               business logic, one module per domain + shared helpers
      money.py              Decimal helpers and compute_totals()
      numbering.py          per-organization document sequences (INV-000001, ...)
      audit.py              write audit_logs rows
      email.py              SMTP sender (no-op when SMTP_HOST is empty)
      pagination.py         page/page_size -> Paginated envelope
      scheduler.py          APScheduler jobs + run_forever() for the dedicated container
  alembic/                  migrations; env.py imports backend.app.models for autogenerate
  tests/                    pytest; conftest forces test settings before importing the app
frontend/
  src/
    services/               axios client + one typed service per domain (api-contract section 11)
    hooks/useAuth.tsx       AuthProvider: tokens, current org, hasRole()
    pages/, components/, routes/, types/api.ts, utils/
```

## 3. Backend layering

```
HTTP request
   |  api/v1/endpoints   parse/validate body & query (schemas), resolve deps, map to status codes
   v
services               business rules, state transitions, totals, side effects (email, gateway, audit)
   |
   v
repositories           SQLAlchemy queries; always scoped by organization_id; pagination/sorting
   |
   v
models / PostgreSQL    constraints, indexes, enums, FK cascades
```

Rules that keep the layers honest:

- Endpoints never contain business logic and never build SQL. Services never read HTTP objects.
- Every mutation happens inside one request-scoped `Session` (`get_db`), committed by the service
  after writing its audit row, so the audit entry and the change are atomic.
- All errors are `AppException` subclasses rendered as
  `{ "error": { "code", "message", "details" } }` with the matching HTTP status
  (`VALIDATION_ERROR` 422, `UNAUTHORIZED` 401, `FORBIDDEN` 403, `ENTITY_NOT_FOUND` 404,
  `CONFLICT`/`INVALID_STATE` 409, `RATE_LIMITED` 429, `GATEWAY_NOT_CONFIGURED` 503,
  `GATEWAY_ERROR` 502, `INTERNAL_SERVER_ERROR` 500).
- Configuration is only read through `settings` (`core/config.py`). Production and staging
  refuse to boot with insecure values (weak `SECRET_KEY`, `DEBUG`, default DB password, SQLite,
  localhost CORS).

## 4. Tenancy model

- `organizations` is the tenant root. Every business table mixes in `TenantMixin`, i.e. carries
  an indexed, non-null `organization_id` FK (`ON DELETE CASCADE`).
- `users` are global (an email exists once); `memberships` link a user to an organization with a
  `role` and `status` (`invited` / `active` / `deactivated`). A user may belong to several
  organizations and switches via `POST /auth/switch-organization`.
- The JWT access token carries `org` (active organization) and `role`. `get_current_user`
  resolves the membership and rejects tokens for deactivated memberships; repositories filter on
  the organization id from the token - never on a client-supplied id.
- Role hierarchy (ascending): `viewer` (10) < `finance` (20) < `admin` (30) < `owner` (40).
  `require_role(min)` compares ranks. Viewers are read-only; finance operates documents and
  payments; admins manage the team, catalog deletion, refunds and approvals; owners manage owners
  and run admin jobs. An organization must always keep at least one active owner.
- Document numbers (`INV-`, `QUO-`, `PAY-`, `SUB-`, `CUS-` + zero-padded sequence) are allocated
  per organization from counters on the organization row, inside the same transaction as the
  document insert.

## 5. Authentication and tokens

| Token | Form | Lifetime | Storage |
| --- | --- | --- | --- |
| Access | JWT (HS256, `SECRET_KEY`), claims `sub` (user id), `org`, `role`, `type=access`, `iat`, `exp`, `jti` | `ACCESS_TOKEN_EXPIRE_MINUTES` (30) | client only |
| Refresh | opaque 32-byte random string | `REFRESH_TOKEN_EXPIRE_DAYS` (30), **rotating** | `refresh_tokens` row holding the SHA-256 hash, user, org, expiry, revocation, parent link |
| Invitation | opaque | `INVITE_TOKEN_EXPIRE_HOURS` (72) | hashed on the membership |
| Password reset | opaque | `PASSWORD_RESET_EXPIRE_MINUTES` (60) | hashed in `password_reset_tokens` |

- `POST /auth/refresh` revokes the presented refresh token and issues a new pair. Presenting an
  already-revoked token is treated as theft: the whole chain is revoked and the call returns 401.
- Password change revokes all other refresh tokens; deactivating a member revokes that user's
  tokens for the organization.
- Passwords are SHA-256 pre-hashed then bcrypt (cost 12). Policy: at least `PASSWORD_MIN_LENGTH`
  characters, mixed case, a digit. Five failed logins lock the account for 15 minutes.
- Credential endpoints are rate limited per IP (`AUTH_RATE_LIMIT`, slowapi).
- The frontend keeps both tokens in `localStorage` (`rooman.access_token`,
  `rooman.refresh_token`); the axios client attaches the access token, and on 401 performs one
  refresh + retry before logging out.

## 6. Money and rounding

- All amounts are `Decimal` in Python and `NUMERIC` in PostgreSQL; the API serialises them as
  strings with two decimals (`"1250.00"`), never floats. Currency is ISO 4217 (`INR` default).
- `services/money.py::compute_totals` is the single implementation of the contract's rules
  (`ROUND_HALF_UP` to 2 dp at each step):

  ```
  amount          = round(quantity * unit_price, 2)
  subtotal        = sum(amount)
  discount_amount = round(subtotal * discount_pct / 100, 2)
  tax_amount      = sum over lines of round((amount - round(amount * discount_pct / 100, 2)) * tax_rate_pct / 100, 2)
  total           = subtotal - discount_amount + tax_amount
  ```

- Invoice `amount_paid` is the sum of `payment_allocations`; `amount_due = total - amount_paid`;
  status becomes `paid` when `amount_due == 0`, `partially_paid` when some but not all is paid.
- Razorpay amounts are integers in paise (`total * 100`) at the gateway boundary only.
- Refunds reverse allocations proportionally and re-open the affected invoices; a payment becomes
  `refunded` or `partially_refunded`.

## 7. Background jobs (scheduler)

`services/scheduler.py` registers one APScheduler job that runs every
`SCHEDULER_INTERVAL_MINUTES` and performs, for every organization:

1. **Trial conversion** - `trialing` subscriptions with `trial_end <= today` become `active`,
   the first period starts, an invoice is generated and sent.
2. **Renewals** - `active` subscriptions with `next_billing_date <= today` advance to the next
   period and get a renewal invoice (or end when `cancel_at_period_end` is set).
3. **Overdue marking** - `sent`/`partially_paid` invoices past `due_date` become `overdue`; the
   owning subscription becomes `past_due`.
4. **Dunning** - overdue invoices receive a reminder email every
   `DUNNING_REMINDER_INTERVAL_DAYS` up to `DUNNING_MAX_REMINDERS` times
   (`reminder_count`, `last_reminder_at`).

The same routine is exposed to owners as `POST /api/v1/admin/jobs/run`, which returns the counts
`{ renewals, trials_converted, marked_overdue, reminders_sent }`.

Deployment rule: **exactly one process** may have `SCHEDULER_ENABLED=true`. In development the
API process runs it in-process; in `docker-compose.prod.yml` the API containers set it to `false`
and a single `scheduler` container runs `run_forever()` (a blocking loop around the same
scheduler). Running it twice would double-invoice.

## 8. Online payments and webhook idempotency

1. The hosted page (`/pay/<token>`) calls `POST /public/invoices/{token}/razorpay-order`, which
   creates a Razorpay Order and a `pending` `Payment` (`gateway=razorpay`).
2. Razorpay Checkout completes in the browser; the page posts
   `razorpay_order_id / razorpay_payment_id / razorpay_signature` to `.../razorpay-verify`. The
   server recomputes `HMAC-SHA256(order_id|payment_id, KEY_SECRET)`; on match the payment becomes
   `succeeded`, is allocated to the invoice and marked `auto_matched`.
3. Independently, Razorpay POSTs to `/api/v1/webhooks/razorpay`. The raw body is verified against
   `RAZORPAY_WEBHOOK_SECRET` (`X-Razorpay-Signature`). Each event is stored in `webhook_events`
   keyed by the `x-razorpay-event-id` header; a duplicate id is acknowledged with `200` and
   ignored. `payment.captured` has the same effect as a successful verify (so a closed browser tab
   still results in a paid invoice), `payment.failed` marks the payment `failed` with the reason,
   `refund.processed` completes a refund. Invalid signatures are rejected (audit
   `WEBHOOK_REJECTED`).

Both paths are idempotent, so whichever arrives first wins and the second is a no-op.

## 9. Audit log

Every state change writes an `audit_logs` row: actor (user or `system`/`webhook`), `action`
(the constants in api-contract section 12, e.g. `INVOICE_SENT`, `PAYMENT_CAPTURED`), `entity_type`,
`entity_id`, human `entity_label`, `status` (`success`/`warning`/`denied`), `before_state`/
`after_state` JSON snapshots and the client IP. Reads never write audit rows. The log is visible
to admins (`GET /audit-logs`, CSV/JSON export up to 10,000 rows) and feeds the activity feed and
dashboard "recent activity". Rows are append-only; there is no API to edit or delete them.

## 10. Approvals

Sending a quote whose `discount_pct` exceeds `organization.discount_approval_threshold_pct`
creates an `ApprovalRequest(type=quote_discount)` and parks the quote in `pending_approval`.
An admin (other than the requester) approves - the quote is sent - or rejects - it returns to
`draft`. The same mechanism carries `refund` and `invoice_void` approvals.

## 11. Frontend

- Vite-built React SPA; all API access goes through `services/apiClient.ts`
  (`baseURL = ${VITE_API_BASE_URL}/api/v1`; empty base = same origin) and the typed domain
  services. Components never call axios directly and never compute financial totals.
- TanStack Query handles caching/invalidation; React Router v6 defines public routes (`/login`,
  `/signup`, `/forgot-password`, `/reset-password`, `/accept-invitation`, `/pay/:token`,
  `/quote/:token`) and the authenticated app shell.
- Light theme only; Tailwind design tokens in `tailwind.config.js`.
- Production build is served by nginx (`frontend/docker/nginx.conf`): `try_files $uri /index.html`
  for client-side routes, immutable caching of `/assets/*`, `/api/` reverse-proxied to
  `backend:8000` with `X-Forwarded-*` headers, security headers, `client_max_body_size 10m` for
  CSV uploads.

## 12. Persistence and migrations

- Schema is owned by Alembic (`backend/alembic`, config `backend/alembic.ini` with
  `script_location=backend/alembic` and `prepend_sys_path=.`, so commands run from the repository
  root). `env.py` imports `backend.app.models` so `--autogenerate` sees every table.
- The API container applies `alembic upgrade head` on start before gunicorn binds; the scheduler
  container skips migrations (`RUN_MIGRATIONS=false`).
- Tests create the schema directly from the models (`Base.metadata.create_all`) on SQLite by
  default or PostgreSQL when `TEST_DATABASE_URL` is set; CI additionally runs the migrations on a
  fresh PostgreSQL database and warns on model/migration drift (`alembic check`).

## 13. Observability

- `GET /api/v1/health` -> `{ status: healthy|degraded, version, environment, database: {status, dialect} }`.
  It returns 200 even when degraded; alert on the body.
- Logs go to stdout (`LOG_JSON=true` for JSON lines); gunicorn access/error logs also go to
  stdout. nginx logs requests, including webhook deliveries.
- `/healthz` on the web container is a static liveness probe.
