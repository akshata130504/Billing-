# Security roadmap

This page covers what is implemented, what is designed but not built, and what depends on
infrastructure. It covers application-level controls only.

## Implemented (application level)

| Area | What | Where |
| --- | --- | --- |
| Startup validation | Production or staging refuses to start in any of these cases: weak or placeholder `SECRET_KEY`; `DEBUG=true`; SQLite; DB password `postgres`; localhost, `*` or non-https `ALLOWED_ORIGINS`; non-https `FRONTEND_URL`; `ALLOWED_HOSTS=*`; no `SMTP_HOST`; a remote DB host without `verify-full`/`verify-ca`. Validation errors never echo input values (`hide_input_in_errors`). | `core/config.py` `enforce_production_safety` |
| Host header allowlist | `TrustedHostMiddleware` with `ALLOWED_HOSTS`. When empty in production, the list is derived from the hostnames in `FRONTEND_URL`/`ALLOWED_ORIGINS`. `localhost`/`127.0.0.1` are always allowed for the container and deploy probes. Disabled (`*`) outside production, so tests keep using `testserver`. | `main.py` |
| Trusted proxies | `X-Real-IP` is honoured only when the TCP peer is inside `TRUSTED_PROXIES`. The default is RFC 1918, loopback and ULA, which matches the compose nginx. `X-Forwarded-For` is never used. | `api/deps.py` `client_ip` |
| CORS | Explicit origins, methods and headers. A wildcard origin never gets `allow_credentials` (and is refused in production). | `main.py` |
| Security headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP, and HSTS when `SECURE_COOKIES=true`. `Cache-Control: no-store` on API responses. The nginx container adds its own set. | `main.py`, `frontend/docker/security-headers.conf` |
| Log redaction | Every log line is scrubbed after `%`-formatting, including tracebacks and JSON logs. Covered: passwords, OTP/TOTP codes, tokens, JWTs, API keys (Razorpay, Google, GitHub, Slack, AWS, Stripe-style), `Authorization`/Basic/Bearer, URL credentials, Fernet ciphertext, PEM keys and Luhn-valid card numbers. | `core/redaction.py`, `core/logging.py` |
| Alerts | `send_alert()` is non-blocking, deduplicated and redacted. It posts `{"text": ...}` to `ALERT_WEBHOOK_URL` and is wired to login/MFA lockouts and readiness DB failures. | `core/alerts.py` |
| Least privilege DB | Runtime DML-only role plus an owner/migration role (opt-in). | [`database-security.md`](database-security.md) |
| DB TLS | `POSTGRES_SSLMODE`/`SSLROOTCERT`/`SSLCERT`/`SSLKEY`. | [`database-security.md`](database-security.md) |
| Secrets at rest | Fernet keyring (`ENCRYPTION_KEYS`) with rotation. Backwards compatible with ciphertext derived from `SECRET_KEY`. | `core/encryption.py` |

## Designed, not implemented: httpOnly cookie + CSRF authentication

**Current state:** the SPA keeps the access token and the opaque refresh token in browser storage
and sends `Authorization: Bearer`. **Cookie authentication is NOT implemented.** `SECURE_COOKIES`
only controls HSTS today.

**Why migrate:** XSS could steal a token kept in browser storage. An httpOnly cookie cannot be read by
script, which limits XSS to acting in-session.

**Target design:**

1. **Refresh token cookie**
   - Name `__Host-rb_refresh`, attributes `HttpOnly; Secure; SameSite=Strict; Path=/`. The `__Host-` prefix pins it to the exact origin and forbids a `Domain` attribute.
   - Set by `/auth/login`, `/auth/login/mfa` and `/auth/refresh`; cleared by `/auth/logout`.
   - It stays opaque, hashed at rest and rotated with reuse detection, exactly as today.
2. **Access token:** stays short-lived and **in memory only**, not in storage. The SPA gets it from
   the `/auth/refresh` response body on page load. Bearer auth keeps working for API clients.
3. **CSRF:** only `/auth/refresh` and `/auth/logout` read the cookie, so the attack surface is
   limited to those two endpoints. Three layers of defence:
   - `SameSite=Strict`.
   - A double-submit token: a non-httpOnly `__Host-rb_csrf` cookie that must be echoed in an `X-CSRF-Token` header. Compare it with `hmac.compare_digest`.
   - An `Origin`/`Referer` check against `ALLOWED_ORIGINS`.
4. **CORS:** `allow_credentials` is already on and the origins are explicit, so no wildcard is
   possible. Add `X-CSRF-Token` to `CORS_ALLOWED_HEADERS`.
5. **Customer portal:** `X-Portal-Token` gets the same treatment in a second phase.
6. **Rollout:**
   1. The backend accepts both the body and the cookie (feature flag `AUTH_REFRESH_COOKIE=true`).
   2. The frontend switches to the cookie and to in-memory access tokens.
   3. The backend stops returning `refresh_token` in bodies.
   4. The storage-migration code is removed after one refresh-token lifetime (30 days).
7. **Tests:** login sets the cookie with the correct attributes; refresh without a CSRF header
   returns 403; a cross-origin `Origin` header returns 403; logout clears the cookie; a replayed
   refresh cookie revokes the family.

No configuration was added for this yet, because a half-wired flag would suggest it is
implemented.

## Infrastructure-only (cannot be done in application code)

- **KMS-backed encryption keys** (envelope encryption, AWS KMS, GCP KMS or Vault Transit). The
  `EncryptionProvider` interface is ready. **Production KMS provider integration requires infrastructure
  configuration** (key, IAM or workload identity).
- **Secret storage:** moving `.env.production` into a secrets manager or Docker secrets.
- **DB TLS certificates:** the server certificate and a CA bundle mounted into the containers, for remote or managed databases.
- **Running `deploy/db-least-privilege.sh`** on the production host, then setting `APP_POSTGRES_*`.
- **A dedicated one-shot migration job,** so the API container never receives the owner credentials. Today the entrypoint unsets them before gunicorn starts, but they are still in the container's configured environment.
- **WAF / DDoS protection,** host firewall, SSH hardening, OS patching, image scanning in the registry.
- **Alert webhook receiver** (Slack/Teams channel), with on-call routing.
