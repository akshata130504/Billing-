# Platform console: separate origin, audit immutability, step-up

Status: **phase 2.5 hardening, not production-ready.** Nothing in this document has been deployed.
The existing tenant deployment (`deploy/Caddyfile`, `docker-compose.prod.yml`, `frontend/Dockerfile`,
`frontend/docker/nginx.conf`) is unchanged. The platform console is off unless it is configured.

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

## 3. Production rollout sketch (not applied)

1. Build and publish the platform image: `docker build -f frontend/Dockerfile.platform ./frontend`.
2. Add a compose service (example - adapt to the real stack):

   ```yaml
   platform-web:
     image: <registry>/rooman-billing-platform-web:<tag>
     restart: unless-stopped
     depends_on:
       backend:
         condition: service_healthy
     # not published on a host port: only Caddy reaches it
   ```

3. Add a Caddy site block next to the existing one (the existing `{$DOMAIN}` block is unchanged):

   ```caddy
   {$PLATFORM_DOMAIN} {
       encode zstd gzip
       header {
           Strict-Transport-Security "max-age=31536000; includeSubDomains"
           -Server
       }
       request_body {
           max_size 64KB
       }
       reverse_proxy platform-web:80 {
           header_up X-Forwarded-Proto {scheme}
           header_up X-Real-IP {remote_host}
       }
   }
   ```

   Optionally restrict the block by client IP (office / VPN ranges) with a `@allowed remote_ip`
   matcher - recommended for a staff-only console.
4. Set `PLATFORM_JWT_SECRET` and `PLATFORM_APP_ORIGIN=https://<platform-host>` in the backend and
   scheduler environment; run `alembic upgrade head` (0028) as the owner role; re-run
   `deploy/db-least-privilege.sh` (idempotent).
5. Create the first staff member with the server-side CLI (`python -m backend.app.cli.platform_staff
   create ... --password-stdin`). There is no default account.

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
`_REQUIRED`; codes are never recorded. No production route uses it yet (phase 3 will).
