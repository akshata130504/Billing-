# Platform console: one origin (/admin + /superadmin), audit immutability, step-up

Status: integrated into the production release pipeline (section 3). The first production rollout still needs the one-time server setup listed there.

## 1. One website, one origin

Rooman Billing is ONE public website on ONE origin (the origin of `FRONTEND_URL`):

| | Tenant app (organizations) | Platform console (Rooman staff / Super Admin) |
|---|---|---|
| URL | `https://<official-domain>/admin` (sign-in; `/admin/<page>` = `/<page>`) | `https://<official-domain>/superadmin`, every console page under `/superadmin/*` |
| Entry document | `index.html` -> `src/main.tsx` | `superadmin.html` -> `src/platform/main.tsx` (router `basename="/superadmin"`) |
| Build / image | one `npm run build` -> `dist/` (both documents, shared hashed `assets/`), one web image `frontend/Dockerfile` | same |
| nginx | `docker/nginx.conf`, `security-headers.conf` | same server; `/superadmin*` and `/api/v1/platform/` use `platform-security-headers.conf` |
| Auth | bearer tokens (no cookies) | HttpOnly cookies + CSRF header, email + password sign-in, password step-up |

Same origin does **not** mean shared authorization. The console shares no router, auth provider,
API client or storage with the tenant SPA; the tenant bundle contains no console route
(`/superadmin` is answered with `superadmin.html` by nginx and by the Vite dev/preview servers).
A tenant user who opens `/superadmin` gets the platform staff sign-in: a tenant token is not a
platform credential (different signing key, audience, issuer and token type), and the console
loads nothing without a platform session.

### What the backend enforces (`backend/app/core/platform_boundary.py`)

Active whenever platform sign-in is configured (`PLATFORM_JWT_SECRET` set):

- **Origin check.** On platform paths (`/api/v1/platform/*`), a present `Origin` header must equal
  the application origin (`FRONTEND_URL`) exactly - scheme, host and port; another origin, a
  sibling host, another port or `null` is refused (403).
- **Fetch metadata.** `Sec-Fetch-Site` other than `same-origin` / `none` is refused (403). This
  blocks "simple" no-CORS form/text POSTs from any other site or sibling subdomain, which skip
  CORS preflight.
- **CORS split by path.** Tenant paths keep the existing `ALLOWED_ORIGINS` policy unchanged.
  Platform paths use a separate policy that allows only the application origin, with credentials,
  methods `GET POST DELETE OPTIONS` and headers `Content-Type Accept X-Platform-CSRF X-Request-ID`.
  No wildcard, no origin reflection, no regex.
- **Headers.** Platform API responses get a stricter set than tenant ones
  (`default-src 'none'; frame-ancestors 'none'`, `X-Frame-Options: DENY`, `Referrer-Policy:
  no-referrer`, COOP/CORP `same-origin`, `Cache-Control: no-store`). The tenant CSP is unchanged.
  The console document (`/superadmin*`) is served by nginx with its own strict CSP: no
  third-party scripts, fonts or frames, not framable, `noindex`.
- **CSRF.** Double submit: cookie-authenticated writes need `X-Platform-CSRF` equal to the platform
  CSRF cookie (constant-time compare), even from the same origin. The tenant app has no cookie
  auth and no CSRF token, so there is nothing to cross-use; tenant bearer tokens are refused by
  platform routes and platform tokens/cookies by tenant routes.
- **Websockets** on platform paths are refused.

### Cookies

Host-only (never a `Domain` attribute), `SameSite=Strict`, `HttpOnly` except the CSRF cookie.

| | Secure mode (production, https) | Local http development / tests |
|---|---|---|
| access | `__Host-rb_platform_access`, `Path=/` | `rb_platform_access`, `Path=/api/v1/platform` |
| refresh | `__Secure-rb_platform_refresh`, `Path=/api/v1/platform/auth` | `rb_platform_refresh`, same path |
| CSRF | `__Host-rb_platform_csrf`, `Path=/`, readable | `rb_platform_csrf`, `Path=/`, readable |

`__Host-` makes the browser refuse the cookie unless it is Secure, host-only and `Path=/`, so a
sibling subdomain cannot set, overwrite or "toss" it. On the shared origin the secure access
cookie also travels with tenant API requests; tenant routes read bearer tokens only and ignore it
(covered by tests).

### Residual risk of sharing the origin (accepted with the single-origin requirement)

**This is weaker isolation than the previous separate-origin design.** A separate origin kept
script running on the tenant app away from the console. On one origin, script injected into ANY
page of the site (an XSS bug in the tenant app, or in the console) runs on the same origin as the
console. If a Rooman staff member is signed in to the console in the same browser, that script can
call the platform API with their session: the browser attaches the cookies, the Origin and
`Sec-Fetch-Site` checks pass (it IS the same origin), and the CSRF double submit does not stop it
(the CSRF cookie is readable by same-origin script by design). Within the staff member's role it
could:

- read everything the console shows (organization directory, platform audit log, staff list,
  health, CMS drafts);
- perform the state changes that do not require step-up (for example requesting or cancelling
  access grants, saving CMS drafts or uploading media, revoking sessions, some organization
  lifecycle actions);
- perform the step-up-protected actions too (suspension, deletion scheduling, staff
  activation/deactivation, entering a tenant, emergency approval, CMS publish/rollback) if the
  session completed a step-up within the last `PLATFORM_STEP_UP_MINUTES` (at most 15).

What still limits it: the platform tokens are HttpOnly, so the script cannot steal the session
for use elsewhere; sessions are short (10-minute access token, idle and absolute limits); without
a step-up in the last 15 minutes the sensitive actions above need the staff member's password,
which a script does not have (it could only phish it with a fake prompt on the same origin); both apps run under a `script-src 'self'` CSP with no third-party
scripts on the console; tenant tokens and platform tokens remain unusable on each other's routes;
every platform action is audited. Recommended operating practice: Rooman staff use the console in
a separate browser profile (or browser) from any tenant account, and sign out when done.

## 2. Configuration

| Variable | Meaning |
|---|---|
| `FRONTEND_URL` | THE application origin (bare origin, **https in production**), e.g. `https://<official-domain>`. Serves `/admin` and `/superadmin`; the only origin the platform API accepts. |
| `PLATFORM_JWT_SECRET` | Platform token signing key (≥ 32 chars, different from `SECRET_KEY`). Generate on the server; never commit. Empty = platform sign-in disabled (503 on its API) and the boundary middleware is a no-op. |
| `PLATFORM_COOKIE_SECURE` | Defaults to on in production. |
| `PLATFORM_STEP_UP_MINUTES` | Step-up window, default 15, allowed 1-15. |

There is no separate platform origin or domain: `PLATFORM_APP_ORIGIN`, `PLATFORM_DOMAIN` and
`TENANT_APP_ORIGIN` are retired (ignored if present; `deploy/check-env.sh` warns). No production
DNS name is defined here.

### Local development

```sh
# backend (from the repo root) - a throwaway key, never reuse it anywhere
PLATFORM_JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))") \
FRONTEND_URL=http://localhost:5173 \
  uvicorn backend.app.main:app --port 8000

# frontend
npm run dev     # http://localhost:5173/admin       tenant app
                # http://localhost:5173/superadmin  platform console (same dev server)
```

## 3. Production rollout

The console is part of the normal release (`.github/workflows/deploy.yml`, `docker-compose.prod.yml`,
`deploy/deploy-poll.sh`) inside the one web image; nothing is rolled out by hand except the
one-time setup below.

1. **`.env.production`** (see `.env.production.example`): `FRONTEND_URL` (the https application
   origin), `PLATFORM_JWT_SECRET` (>= 32 chars, different from `SECRET_KEY`) and `GITHUB_PAT`.
   `docker-compose.prod.yml` refuses to start without the key and `deploy/check-env.sh` (run by
   the poller before every release) validates them. Remove the retired `PLATFORM_APP_ORIGIN`,
   `PLATFORM_DOMAIN` and `TENANT_APP_ORIGIN` if an older setup added them.
2. **DNS + TLS**: one hostname (`DOMAIN` for the Caddy overlay = the host of `FRONTEND_URL`).
   No second hostname. To restrict the console by client IP (office / VPN ranges), add a matcher
   on `/superadmin*` and `/api/v1/platform/*` with `remote_ip` to the `{$DOMAIN}` site block.
3. **Release**: merge to `main`. CI passes, Deploy publishes `rooman-billing-{api,web}:<sha>`, the
   poller pulls both, runs migrations (the backend applies `alembic upgrade head` on start), and
   waits for API readiness before recording `.deploy/deployed_sha`. A failed release rolls back.
4. **First staff member** (no default account): see `docs/deployment.md` > Platform console
   (`python -m backend.app.cli.platform_staff create ... --password-stdin`).

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

`POST /api/v1/platform/auth/step-up` with `{"password": "<current password>"}` on a signed-in
platform session (cookie + CSRF header, or bearer). Wrong passwords are throttled per account
(separately from the sign-in throttle); the endpoint is also IP rate-limited. On success the **current session** records `step_up_at` /
`step_up_expires_at` (15 minutes by default, 1-15, never beyond the session's own expiry). No
token or cookie is issued.

`require_recent_platform_step_up` (in `api/platform_deps.py`) guards sensitive routes: 403
`STEP_UP_REQUIRED` unless this exact session stepped up within the window. The window is re-derived
from `step_up_at` with the current setting (lowering it shortens existing windows; nothing extends
one - not use, not refresh). It ends with logout, logout-all, revocation of the session, password
reset and deactivation. Audited as `PLATFORM_STEP_UP_SUCCEEDED`, `_FAILED`, `_REQUIRED`;
passwords are never recorded.

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

