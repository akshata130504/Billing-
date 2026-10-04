# Platform console: separate origin, audit immutability, step-up

Status: integrated into the production release pipeline (section 3). The first production rollout still needs the one-time server setup listed there.
The tenant app keeps its own image and nginx config; the console is an additional service.

## 1. Two origins

| | Tenant app (unchanged) | Platform console (Rooman staff) |
|---|---|---|
| Origin | `FRONTEND_URL` / `ALLOWED_ORIGINS` | `PLATFORM_APP_ORIGIN` |
| Bundle | `npm run build` → `dist/` | `npm run build:platform` → `dist-platform/` (`platform.html`, own entry `src/platform/main.tsx`) |
| Image | `frontend/Dockerfile` | `frontend/Dockerfile.platform` |
| nginx | `docker/nginx.conf` (+ `security-headers.conf`) | `docker/nginx.platform.conf` (+ `platform-security-headers.conf`) |
| API reachable | all tenant paths | `/api/v1/platform/*` **only** |
| Auth | bearer tokens (no cookies) | HttpOnly cookies + CSRF header, mandatory TOTP |

The tenant bundle contains no platform routes or code; the platform bundle contains no tenant API
client, no web fonts, no payment scripts, and nothing from `public/`.

### What the backend enforces (`backend/app/core/platform_boundary.py`)

Active only when `PLATFORM_APP_ORIGIN` is set:

- **Host binding.** `/api/v1/platform/*` is served only when `Host` equals the platform host
  (`host[:port]` of `PLATFORM_APP_ORIGIN`); anywhere else it is a 404. On the platform host,
  every other path (tenant API, health, uploads, webhooks) is a 404.
- **Origin check.** On platform paths, a present `Origin` header must equal
  `PLATFORM_APP_ORIGIN` exactly (scheme, host and port; `null` is refused) - 403 otherwise.
- **Fetch metadata.** `Sec-Fetch-Site` other than `same-origin` / `none` is refused (403). This
  blocks "simple" no-CORS form/text POSTs from the tenant origin (or any sibling subdomain), which
  skip CORS preflight.
- **CORS split by path.** Tenant paths keep the existing `ALLOWED_ORIGINS` policy unchanged.
  Platform paths use a separate policy that allows only `PLATFORM_APP_ORIGIN`, with credentials,
  methods `GET POST DELETE OPTIONS` and headers `Content-Type Accept X-Platform-CSRF X-Request-ID`.
  No wildcard, no origin reflection, no regex.
- **Headers.** Platform API responses get a stricter set than tenant ones
  (`default-src 'none'; frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy:
  no-referrer`, COOP/CORP `same-origin`, `Cache-Control: no-store`). The tenant CSP is unchanged.
- **CSRF.** Double submit: cookie-authenticated writes need `X-Platform-CSRF` equal to the platform
  CSRF cookie (constant-time compare). The tenant app has no cookie auth and no CSRF token, so there
  is nothing to cross-use; tenant bearer tokens are refused by platform routes (different key,
  audience, issuer and type) and platform tokens by tenant routes.

### Cookies

Host-only (never a `Domain` attribute), `SameSite=Strict`, `HttpOnly` except the CSRF cookie.

| | Secure mode (production, https) | Local http development / tests |
|---|---|---|
| access | `__Host-rb_platform_access`, `Path=/` | `rb_platform_access`, `Path=/api/v1/platform` |
| refresh | `__Secure-rb_platform_refresh`, `Path=/api/v1/platform/auth` | `rb_platform_refresh`, same path |
| CSRF | `__Host-rb_platform_csrf`, `Path=/`, readable | `rb_platform_csrf`, `Path=/`, readable |

`__Host-` makes the browser refuse the cookie unless it is Secure, host-only and `Path=/`, so a
sibling subdomain (including the tenant app) cannot set, overwrite or "toss" it. The access
cookie's `Path=/` is harmless because the platform host serves nothing but the console.

**Why not rely on SameSite alone:** `app.example.com` and `platform.example.com` are *same-site*,
so `SameSite=Strict` does not stop the browser attaching platform cookies to a request a
tenant-origin page makes. Host-only cookies stop the *tenant host* from receiving them, and the
Origin / `Sec-Fetch-Site` checks above stop a tenant-origin page from *using* them. For the
strongest isolation, put the console on a **different registrable domain** from the tenant app
(then it is also cross-site). Browsers do not isolate cookies by port, so `localhost:5173` vs
`localhost:5174` is not a separate origin for cookies - configuration refuses a platform
hostname equal to any tenant hostname.

## 2. Configuration

| Variable | Meaning |
|---|---|
| `PLATFORM_JWT_SECRET` | Platform token signing key (≥ 32 chars, different from `SECRET_KEY`). Generate on the server; never commit. |
| `PLATFORM_APP_ORIGIN` | Bare origin of the console, e.g. `https://<platform-host>`. Required together with the key; **https in production**; its hostname must differ from every tenant origin. Its host is added to the derived `ALLOWED_HOSTS`; if you set `ALLOWED_HOSTS` explicitly, add it there. |
| `PLATFORM_COOKIE_SECURE` | Defaults to on in production. |
| `PLATFORM_STEP_UP_MINUTES` | Step-up window, default 15, allowed 1-15. |

Both empty (the default) = the platform console is disabled (503 on its API) and the boundary
middleware is a no-op. Setting only one of the two refuses to start.

No production DNS name is defined here. Choose the host, create its DNS record, and pick a TLS
certificate for it as part of the production rollout.

### Local development

```sh
# backend (from the repo root) - a throwaway key, never reuse it anywhere
PLATFORM_JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))") \
PLATFORM_APP_ORIGIN=http://platform.localhost:5174 \
  uvicorn backend.app.main:app --port 8000

# frontend
npm run dev            # tenant app   http://localhost:5173 (unchanged)
npm run dev:platform   # console      http://platform.localhost:5174
```

`*.localhost` resolves to the loopback address in current browsers. The platform dev server
proxies only `/api/v1/platform` and keeps the `Host` header (`changeOrigin: false`).

## 3. Production rollout

The console is part of the normal release (`.github/workflows/deploy.yml`, `docker-compose.prod.yml`,
`deploy/deploy-poll.sh`); nothing is rolled out by hand except the one-time setup below.

1. **GitHub repository variables** (Settings > Secrets and variables > Actions > Variables):
   `TENANT_APP_ORIGIN=https://<tenant-host>` and `PLATFORM_APP_ORIGIN=https://<platform-host>`.
   They are baked into the images ("Enter tenant" needs both origins). The Deploy run fails
   before building anything when either is missing, not https, not a bare origin, or when both are equal.
2. **`.env.production`** (see `.env.production.example`): `PLATFORM_APP_ORIGIN`, `PLATFORM_DOMAIN`
   (its host), `PLATFORM_JWT_SECRET` (>= 32 chars, different from `SECRET_KEY`), `TENANT_APP_ORIGIN`
   (the origin of `FRONTEND_URL`) and `GITHUB_PAT`. `docker-compose.prod.yml` refuses to start
   without them and `deploy/check-env.sh` (run by the poller before every release) validates them.
3. **DNS + TLS**: a second hostname for the console. With the Caddy overlay the site block for
   `{$PLATFORM_DOMAIN}` in `deploy/Caddyfile` routes it to `platform-web:80`. Optionally restrict
   that block by client IP (office / VPN ranges) with an `@allowed remote_ip` matcher - recommended
   for a staff-only console. After changing the Caddyfile on the server, recreate caddy
   (`docker compose ... -f docker-compose.caddy.yml up -d --force-recreate caddy`).
4. **Release**: merge to `main`. CI passes, Deploy publishes `rooman-billing-platform-web:<sha>`
   next to the api and web images, the poller pulls all three, runs migrations (the backend applies
   `alembic upgrade head` on start), and waits for the API readiness **and** `platform-web` health
   before recording `.deploy/deployed_sha`. A console that cannot start rolls the release back.
5. **First staff member** (no default account): see `docs/deployment.md` > Platform console
   (`python -m backend.app.cli.platform_staff create ... --password-stdin`).

Local/manual image build (CI does this with the repository variables):
`docker build -f frontend/Dockerfile.platform --build-arg VITE_TENANT_APP_ORIGIN=https://<tenant-host> ./frontend`
fails with a clear message when the origin is missing or malformed.

## 4. Audit log immutability

`platform_audit_logs` is append-only **in the database** (PostgreSQL):

- Migration 0028 installs `platform_audit_logs_append_only()` and two triggers:
  `BEFORE UPDATE OR DELETE ... FOR EACH ROW` and `BEFORE TRUNCATE ... FOR EACH STATEMENT`. Both
  raise SQLSTATE 42501 for every role, including the table owner, whether the statement comes from
  the ORM, raw SQL or a psql session. (Test databases built with `create_all` get the same trigger
  through a DDL event in `models/platform.py`.)
- Migration 0028 also revokes `UPDATE, DELETE, TRUNCATE` on this one table from every role except
  the table owner. `deploy/sql/least_privilege.sql` does the same after its table-wide `GRANT`, so
  re-running it keeps the runtime role at **SELECT + INSERT** on this table (full DML elsewhere,
  unchanged). Its report prints the audit table's privileges.
- The runtime role cannot disable or drop the triggers (only the owner can) and does not own any
  object.
- The application has no endpoint, CLI command or service to edit, delete or purge audit rows, and
  no role bypass. Staff rows referenced by audit rows cannot be deleted (`ON DELETE RESTRICT`).

Production grants (summary):

| Role | platform_audit_logs | other tables | DDL |
|---|---|---|---|
| owner (migrations only, e.g. `POSTGRES_USER`) | owner | owner | yes |
| runtime (`APP_POSTGRES_USER`, API + scheduler) | SELECT, INSERT | SELECT, INSERT, UPDATE, DELETE | no |

**Limits.** The table owner or a superuser can still drop the triggers, or the table. Keep the
owner credentials out of the running application (the app connects as the runtime role), restrict
who can use them, and ship database logs / backups off-host if tamper evidence against a
compromised owner is needed. SQLite (local development only) has no such enforcement; the
application simply never updates or deletes audit rows.

Local verification: `backend/tests/test_platform_audit_immutability.py` and
`test_migration_0028.py` (PostgreSQL via `TEST_DATABASE_URL`), and `test_least_privilege.py` with a
database prepared as described in `docs/database-security.md`.

## 5. Step-up re-authentication

`POST /api/v1/platform/auth/step-up` with `{"code": "<TOTP>"}` on a signed-in platform session
(cookie + CSRF header, or bearer). Password is not accepted. The code is replay-protected (never
the one used to sign in, never twice) and shares the per-account MFA throttle with sign-in; the
endpoint is also IP rate-limited. On success the **current session** records `step_up_at` /
`step_up_expires_at` (15 minutes by default, 1-15, never beyond the session's own expiry). No
token or cookie is issued.

`require_recent_platform_step_up` (in `api/platform_deps.py`) guards sensitive routes: 403
`STEP_UP_REQUIRED` unless this exact session stepped up within the window. The window is re-derived
from `step_up_at` with the current setting (lowering it shortens existing windows; nothing extends
one - not use, not refresh). It ends with logout, logout-all, revocation of the session, password
reset, 2FA reset and deactivation. Audited as `PLATFORM_STEP_UP_SUCCEEDED`, `_FAILED`,
`_REQUIRED`; codes are never recorded.

## 6. Platform Roles and Privileges

| Role | Organization Directory | Organization Lifecycle | Staff Admin | Platform Audit | Jobs & Health | Landing CMS | Tenant Access Grants |
|---|---|---|---|---|---|---|---|
| `platform_administrator` | Full (search, inspect) | Suspend, Reactivate, Schedule Deletion, Cancel, Revoke Sessions, Pause/Resume Jobs (Step-up required) | List, View, Activate, Deactivate, Revoke Sessions (Self-deactivation & last admin protected) | Full search & view (append-only) | View operational metrics & job status (No money-moving execution) | Edit Draft, Preview, Publish, Rollback | Request, Enter, Emergency Dual Approval, Review |
| `platform_operations` | Full (search, inspect) | Suspend, Reactivate, Pause/Resume Jobs | Read-only | Full search & view | View operational metrics & job status | Read-only | Request, Enter (scoped) |
| `platform_support` | Metadata view & search | View metadata | None | Own activity | View operational health | None | Request, Enter (Tenant Owner approved) |

## 7. Organization Lifecycle Governance

- **Lifecycle states:** `ACTIVE` → `SUSPENDED` → `PENDING_DELETION` → `DELETED`.
- **Suspension:** Platform-side control flag. Tenant login is rejected; scheduler skips suspended organizations.
- **Reactivation:** Restores tenant access. **Does not replay missed billing runs**; jobs remain paused until explicitly resumed via step-up authorized mutation.
- **Deletion Schedule:** 30-day graceful window before any hard data purging. Can be cancelled by Platform Administrator.
- **Audit Requirement:** Every lifecycle transition requires step-up MFA and explicit justification logged to `platform_audit_logs`.

## 8. Tenant Access Grants & Scoped Access

- **Zero Unrestricted Super Admin Access:** Platform staff have no default access to tenant data.
- **Grant Request Flow:** Staff specifies tenant organization, specific read scopes (`READ_METADATA`, `READ_CUSTOMERS`, `READ_QUOTES`, `READ_INVOICES`, `READ_PAYMENTS`, `READ_SUBSCRIPTIONS`, `READ_AUDIT`, `READ_CONFIG`), duration (15-480m), ticket reference, and business reason.
- **Tenant Owner Approval:** The Tenant Owner must review and approve the grant in `Settings > Platform Access`.
- **Emergency Dual Control:** Break-glass access requires two independent Platform Administrators (requester + distinct approver) with critical justification and alert dispatch.
- **Read-Only Invariant:** Under no grant can financial mutations, refunds, voiding, Razorpay charges, or owner changes occur.
- **Bi-Directional Audit:** Every access request, approval, entry, viewed API endpoint, and exit is logged in both `platform_audit_logs` and tenant `audit_logs`.
- **Banner & Ephemeral Token:** Active grant session renders a persistent banner with expiration countdown, active scopes, and immediate Exit capability. Token exists in-memory only.

## 9. Landing Page CMS Governance

- **Architecture:** Draft → Preview → Published with rollback capability.
- **Public Isolation:** Public visitors only receive published content via `/api/v1/content/landing`. Draft content requires authenticated platform staff authorization.
- **Sanitization & Safety:** Structured JSON model prevents script/HTML injection. Markdown is sanitized and verified.
- **Pricing Content:** Marketing/illustrative pricing tiers on landing page are CMS content only and completely decoupled from tenant billing plans or SaaS subscriptions.

## 10. Tenant Isolation (Defense-in-Depth)

1. **ORM Layer (`backend/app/core/tenant_context.py`):**
   - Central `ContextVar` tracks active tenant ID.
   - `do_orm_execute` event automatically injects `with_loader_criteria` for all `TenantMixin` entities.
   - Unscoped queries in strict context fail closed with `MissingTenantContextError` (preventing accidental cross-tenant data leakage).
2. **Database Engine Layer (PostgreSQL Row Level Security):**
   - Migration `0032_tenant_row_level_security.py` applies `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` across 14 sensitive tenant tables.
   - Policy: `organization_id = NULLIF(current_setting('app.current_organization_id', true), '') OR current_setting('app.current_organization_id', true) = '__SYSTEM__'`.
   - Local setting applied per transaction via `SELECT set_config('app.current_organization_id', ..., true)`.

## 11. Migration Sequence & Database Integrity

1. `0026_platform_staff_and_sessions.py`: Staff tables, TOTP secrets, session revocation.
2. `0027_platform_audit_log.py`: Platform audit logging table.
3. `0028_platform_audit_immutability.py`: PostgreSQL triggers and privilege revocation for audit immutability.
4. `0029_platform_lifecycle_metadata.py`: Organization lifecycle columns (`status_reason`, `jobs_paused`, `deletion_scheduled_for`).
5. `0030_landing_page_cms.py`: CMS sections, draft/published versions, rollback history.
6. `0031_tenant_access_grants.py`: Access grant requests, approvals, token tracking, emergency flags.
7. `0032_tenant_row_level_security.py`: Row Level Security policies and enforcement across sensitive tenant tables.

