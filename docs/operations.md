# Rooman Billing - Operations Guide

Day-2 procedures for the Docker Compose deployment described in [`deployment.md`](deployment.md).
All commands assume the repository directory on the host and the alias

```bash
alias rb='docker compose --env-file .env.production -f docker-compose.prod.yml'
```

(add `-f docker-compose.caddy.yml` if you run the TLS overlay).

## 1. Backups

The database is the only stateful component. PDFs are rendered on demand, webhook events and
audit logs are tables, and there are no uploaded files.

### Daily logical backup

```bash
rb exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --format=custom' \
  > /var/backups/rooman/rooman_$(date +%F).dump
```

`--format=custom` allows selective and parallel restores with `pg_restore`; `make backup` produces
a gzipped plain-SQL variant instead. Suggested schedule (cron, as the deploy user):

```
15 1 * * * cd /opt/rooman-billing && docker compose --env-file .env.production -f docker-compose.prod.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --format=custom' > /var/backups/rooman/rooman_$(date +\%F).dump && find /var/backups/rooman -name '*.dump' -mtime +30 -delete
```

Copy the directory off-host (object storage, `rclone`, `restic`). Keep 30 daily and 12 monthly
copies; billing data has statutory retention requirements (GST: 6 years), so also archive year-end
dumps permanently.

Always take a dump before upgrading or running manual SQL.

### Restore

Restoring replaces the whole database; stop the API first so nothing writes during the restore.

```bash
rb stop backend scheduler
rb exec -T db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";" -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"'
# custom-format dump
rb exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' < /var/backups/rooman/rooman_2026-09-01.dump
# plain SQL (.sql.gz from make backup)
gunzip -c backups/rooman_billing_20260901_011500.sql.gz | rb exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
rb start backend scheduler
```

Starting `backend` runs `alembic upgrade head`, so a dump from an older release is migrated
forward automatically. Restoring a dump from a **newer** release onto older code is not supported.

Test the restore quarterly on a scratch host: `rb up -d db`, restore, `rb up -d backend`, check
that `/api/v1/health/ready` reports `ready: true` with `migrations.status: at_head`, and log in.
See the pre-launch checklist (section 9) for the full drill.

### Volume snapshot (alternative)

Stopping the stack and snapshotting the `postgres_data` volume (or the host disk) is also
consistent. Never snapshot a running Postgres data directory without `pg_start_backup` semantics.

## 2. Logs

Everything logs to stdout/stderr and is captured by Docker's `json-file` driver (rotated at
5 x 20 MB per container by `docker-compose.prod.yml`).

| Source | Command | What you find |
| --- | --- | --- |
| API | `rb logs -f backend` | entrypoint (DB wait, Alembic output), gunicorn access log (one line per request incl. `/webhooks/razorpay` deliveries), application log (`LOG_JSON=true` -> JSON lines) |
| Scheduler | `rb logs -f scheduler` | one summary per run: renewals, trials converted, overdue marked, reminders sent; email/gateway errors |
| Web | `rb logs -f frontend` | nginx access/error log; `/healthz` requests are suppressed |
| Database | `rb logs -f db` | Postgres startup, checkpoints, slow-query notices if enabled |
| Caddy | `rb logs -f caddy` | certificate issuance/renewal, access log |

Raw files live under `/var/lib/docker/containers/<id>/<id>-json.log`; ship them with Promtail,
Vector, Fluent Bit or the CloudWatch agent.

The application audit trail (who changed what) is **not** in the logs; it is in the database
(`audit_logs`) and in the UI under **Control Center -> Audit Log**, exportable as CSV/JSON.

## 3. Health and readiness probes

Two endpoints, two jobs. Point different things at them.

| Endpoint | Depth | Used by | Codes |
| --- | --- | --- | --- |
| `GET /healthz` (nginx) | static string | web container liveness | 200 |
| `GET /api/v1/health` | `SELECT 1` | container healthcheck in `docker-compose.prod.yml`, uptime monitor | always 200; body `status` is `healthy` or `degraded` |
| `GET /api/v1/health/ready` | DB + Alembic revision | load balancer readiness, post-deploy gate | **200 ready / 503 not ready** |

```bash
curl -s https://<DOMAIN>/api/v1/health/ready | jq
```

```json
{
  "ready": true,
  "version": "0.1.0",
  "environment": "production",
  "checks": {
    "database": {"status": "connected", "dialect": "postgresql"},
    "migrations": {"status": "at_head", "current": "c1d2e3f4a5b6", "head": "c1d2e3f4a5b6"}
  },
  "features": {"scheduler_enabled": false, "razorpay_configured": true, "smtp_configured": true, "sentry_enabled": true},
  "failures": []
}
```

**A 503 means "do not send this instance traffic".** Only two things cause it, and `failures`
names them:

- `"database"` - `SELECT 1` failed. See "Common failures" below; usually the `db` container or
  the credentials. Migrations are reported as `unknown` in this case because they cannot be read.
- `"migrations"` - the schema is not at the head revision the running code expects:
  - `behind` - `alembic upgrade head` has not run (or is still running). Normal for the few
    seconds after a deploy; if it persists, the entrypoint's migration step failed - check
    `rb logs backend`. Fix with the manual migration run in "Maintenance tasks".
  - `multiple_heads` - the migration chain forked (two heads merged from different branches).
    The build is broken; `alembic heads` then merge them, do not deploy.

The `features` block is **informational only** and never fails the probe. It is the fastest way
to confirm that an environment is configured the way you think: whether this process runs the
scheduler, and whether Razorpay, SMTP and Sentry are wired up. Check it right after a deploy.

The endpoint is unauthenticated (like `/health`) and cheap, but it does hit the database and read
the Alembic version table - poll it at most every 10 s.

## 4. Error tracking (Sentry)

Optional and off by default. With `SENTRY_DSN` empty the SDK is never imported and no code runs,
so the feature cannot break a boot.

1. Create a Sentry project (platform: FastAPI) and copy its DSN.
2. In `.env.production`:
   ```
   SENTRY_DSN=https://<key>@<org>.ingest.sentry.io/<project>
   SENTRY_TRACES_SAMPLE_RATE=0.0   # errors only; 0.05-0.1 once you want latency data
   ```
3. `rb up -d backend scheduler`. The log line `Sentry error tracking enabled (environment=production)`
   confirms it, as does `"sentry_enabled": true` in `/api/v1/health/ready`.

**PII handling.** This is a billing system, so events are scrubbed before they leave the host
(`backend/app/core/sentry.py`):

- `send_default_pii=False` and `max_request_body_size="never"` - no request bodies, cookies or
  client IPs are attached.
- A `before_send` hook walks the whole event and redacts any key containing `authorization`,
  `token`, `password`, `secret`, `api_key`, `cookie`, `session`, `signature`, `gstin`, `pan`,
  `aadhaar`, `card`, `cvv`, `account_number`, `ifsc`, `upi` and friends.
- Free text (messages, stack frames, URLs) is pattern-matched for `Bearer <token>`,
  `?token=`/`?secret=` query parameters, GSTIN, PAN and 13-19 digit card numbers.
- The user context is reduced to an opaque id - never an email address.
- If the scrubber itself ever raises, the event is dropped rather than sent unredacted.

Business fields that merely contain those substrings (`plan_name`, `company_name`, `expansion`)
are allow-listed and survive intact. If you add a new sensitive field, add it to
`SENSITIVE_KEY_PARTS` and cover it in `backend/tests/test_health_and_ops.py`.

Sentry is a *supplement* to the stdout logs, not a replacement: the audit trail and the
per-request log lines remain the primary record.

## 5. The background scheduler is mandatory

`SCHEDULER_ENABLED` defaults to **false** in code (safe for tests and for extra API replicas).
If no process in the deployment has it enabled, the platform looks healthy while silently doing
none of this:

- subscription renewals and renewal invoices
- trial expiry and conversion
- marking invoices `overdue`
- dunning reminder emails

`docker-compose.prod.yml` gets this right: `backend` sets `SCHEDULER_ENABLED=false`, the dedicated
`scheduler` service sets it to `true`. **Exactly one process may have it enabled** - two means
duplicate renewal invoices.

The API logs a WARNING at startup in production when it is running with the scheduler disabled, so
grep for it if you are unsure:

```bash
rb logs backend | grep SCHEDULER_ENABLED
rb ps scheduler                 # must exist and be running
rb logs --since 1h scheduler    # one summary line per SCHEDULER_INTERVAL_MINUTES
```

Alert if no scheduler summary line appears for `2 x SCHEDULER_INTERVAL_MINUTES`. Owners can force
a run with `POST /api/v1/admin/jobs/run`.

## 6. Routine checks

```bash
rb ps                                              # all "healthy"/"running"
curl -fsS https://<DOMAIN>/api/v1/health | jq      # status healthy, database connected
curl -fsS https://<DOMAIN>/api/v1/health/ready | jq # ready:true, migrations at_head, features as expected
rb exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from webhook_events where created_at > now() - interval '1 day';"
df -h /var/lib/docker                              # disk
docker system df                                   # image/volume usage; `docker image prune` after upgrades
```

## 7. Common failures

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `backend` exits immediately with `Refusing to start in production with insecure configuration: ...` | `.env.production` still has a default `SECRET_KEY`, `DEBUG=true`, password `postgres`, SQLite URL or a localhost origin | Fix the listed variable(s); `rb up -d backend scheduler`. |
| `backend` logs `waiting for database` for 60 s then exits | DB not healthy yet, wrong `POSTGRES_*`, or the `db` volume was initialised with a different password | `rb logs db`; `rb ps`. If the password changed after first init, run `ALTER USER ... PASSWORD` in `db` or reset the volume (data loss). |
| Alembic error `Target database is not up to date` / `Can't locate revision` | Database from a different branch/release; someone ran migrations manually | `rb run --rm -e RUN_MIGRATIONS=false backend alembic -c backend/alembic.ini history` and `current`; downgrade/upgrade to the expected revision or restore a backup. |
| Web loads, every API call fails with 502 | nginx cannot reach `backend:8000` | `rb ps backend` (healthy?), `rb logs backend`. After scaling/renaming, nginx re-resolves within 10 s. |
| Login page loads, API returns CORS errors in the browser | `ALLOWED_ORIGINS` does not contain the exact `https://` origin (scheme, host, port) | Fix env, restart backend. With the bundled nginx the app is same-origin and CORS never triggers; this appears only when the SPA is hosted elsewhere. |
| Emails not sent, links shown in UI instead | `SMTP_HOST` empty | Configure SMTP. |
| Emails fail with auth/TLS errors | wrong port/TLS combination | 587 -> `SMTP_USE_TLS=true, SMTP_USE_SSL=false`; 465 -> `SMTP_USE_TLS=false, SMTP_USE_SSL=true`. |
| Hosted page shows "online payments unavailable" (503 `GATEWAY_NOT_CONFIGURED`) | Razorpay keys missing | Set `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`, restart. |
| Webhook deliveries fail in the Razorpay dashboard (401/400) | `RAZORPAY_WEBHOOK_SECRET` mismatch or URL wrong | Compare with the dashboard secret; URL must be `/api/v1/webhooks/razorpay`; check `WEBHOOK_REJECTED` audit rows. |
| Payment succeeded in Razorpay but the invoice is still `sent` | verify call failed (user closed tab) and webhook not configured/rejected | Configure webhooks (the `payment.captured` event settles it); meanwhile record the payment manually with the gateway payment id as reference. |
| Invoices not renewing / reminders not sent | scheduler container down or `SCHEDULER_ENABLED=false` everywhere | `rb ps scheduler`, `rb logs scheduler`. Trigger once via `POST /api/v1/admin/jobs/run` (owner). |
| Duplicate renewal invoices | more than one process with `SCHEDULER_ENABLED=true` (e.g. someone set it on `backend`) | Ensure only `scheduler` has it enabled; void the duplicates. |
| `/api/v1/health/ready` returns 503 with `failures: ["migrations"]` | `alembic upgrade head` has not run, is still running, or failed | `rb logs backend` for the Alembic output; run the manual migration in "Maintenance tasks". If `status` is `multiple_heads` the release itself is broken - do not deploy it. |
| `/api/v1/health/ready` returns 503 with `failures: ["database", "migrations"]` | the database is unreachable; the migration check cannot run either | Same as the `waiting for database` row above. |
| Hosted invoice/quote page returns `429 RATE_LIMITED` | more than `PUBLIC_RATE_LIMIT` requests/minute from that IP - often many customers behind one corporate NAT, occasionally token scanning | Check the source IPs in the nginx log. Raise `PUBLIC_RATE_LIMIT` for the legitimate case; leave it and block the IP for the other. |
| `413 Request Entity Too Large` on CSV import | file larger than the 10 MB nginx limit (the API itself allows 5 MB) | Split the CSV. |
| `429 RATE_LIMITED` on login | more than `AUTH_RATE_LIMIT` attempts per minute from one IP (often a shared office NAT) | Wait a minute or raise `AUTH_RATE_LIMIT`. |
| Account locked after failed logins | 5 failures -> 15 minute lock | Wait or reset the password via forgot-password. |
| `frontend` container restarts in a loop with `host not found in upstream` | old nginx config without the resolver | Rebuild the web image (`rb up -d --build frontend`). |
| Disk full | Docker logs or old images | Log rotation is configured; `docker image prune -a`; move `/var/lib/docker` or backups to a larger disk. |

## 8. Maintenance tasks

- **Scaling the API**: raise `WEB_CONCURRENCY` (2 x vCPU) or `rb up -d --scale backend=2`.
  Never scale `scheduler`.
- **Database maintenance**: Postgres autovacuum is on by default; for large audit tables consider
  `VACUUM (ANALYZE) audit_logs` monthly and archiving exports older than the retention period.
- **Postgres major upgrade**: dump with the old version, change the image tag, start with an empty
  volume, restore. Do not start `postgres:17` on a 16 data directory.
- **Manual migration run** (rarely needed):
  `rb run --rm -e RUN_MIGRATIONS=false backend alembic -c backend/alembic.ini upgrade head`.
- **Database shell**: `rb exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"` (read-only queries
  only; every business change should go through the API so it is audited).
- **Stopping for maintenance**: `rb stop frontend backend scheduler` keeps the DB up for backups;
  `rb down` stops everything and keeps volumes; `rb down -v` destroys the database.

## 9. Pre-launch checklist

Run through this the week before the first real customer, and again on go-live day. Everything
here has burned someone before.

### Secrets

- [ ] `SECRET_KEY` regenerated for production (`openssl rand -hex 32`) and never shared with
      staging - rotating it invalidates access tokens, so do it *before* users exist.
- [ ] `POSTGRES_PASSWORD` is not `postgres` and not the staging password. The API refuses to
      start otherwise, but check the value is actually strong.
- [ ] `.env.production` is mode 600, owned by the deploy user, and not in git
      (`git check-ignore .env.production` must print the path).
- [ ] Every secret that was ever pasted into a chat, ticket or screenshot has been rotated.
- [ ] A rotation owner and schedule are written down (see "Rotating secrets" in
      [`deployment.md`](deployment.md)); at minimum, rotate on staff departure.
- [ ] No default/test accounts remain; the first owner account uses a real, unique password.

### Backup restore drill

A backup you have never restored is not a backup. Do this on a scratch host, not production:

- [ ] The nightly `pg_dump` cron exists and has produced a dump in the last 24 h.
- [ ] Dumps are copied off-host and the off-host copy is what you restore from.
- [ ] Restore drill: `rb up -d db` on a clean host, restore yesterday's dump (section 1),
      `rb up -d backend`, then verify `/api/v1/health/ready` is `ready: true` **and**
      `migrations.status` is `at_head`, log in, and spot-check an invoice total, a payment and
      the audit log.
- [ ] Time the drill and record it - that number is your RTO. Record the dump schedule as your
      RPO (24 h with the default cron; tighten it if that is not acceptable for billing data).
- [ ] Calendar reminder to repeat the drill quarterly.

### Razorpay live-key switchover

Test keys (`rzp_test_*`) fail silently against live traffic; do this deliberately:

- [ ] Complete at least one full test-mode payment end to end first (hosted page -> capture ->
      invoice `paid` -> `payment.captured` webhook -> audit rows).
- [ ] KYC/activation complete on the Razorpay account and settlements configured to the right
      bank account.
- [ ] Replace `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` with the **live** pair (`rzp_live_*`) in
      `.env.production`.
- [ ] Create a **new webhook in live mode** - test-mode webhooks do not carry over. URL
      `https://<DOMAIN>/api/v1/webhooks/razorpay`, events `payment.captured`, `payment.failed`,
      `refund.processed`. Put its secret in `RAZORPAY_WEBHOOK_SECRET`.
- [ ] `rb up -d backend scheduler`, then confirm
      `curl -s https://<DOMAIN>/api/v1/meta/integrations` shows `"razorpay": {"enabled": true}`
      and `/api/v1/health/ready` shows `"razorpay_configured": true`.
- [ ] Smoke test with a real payment of a small amount from a real card, then refund it. Confirm
      the invoice settles, the webhook delivery is HTTP 200 in the dashboard, and the audit log
      shows `PAYMENT_CAPTURED` + `WEBHOOK_RECEIVED`.
- [ ] Confirm no `rzp_test_` string remains anywhere: `grep -r rzp_test .env.production`.

### Everything else

- [ ] `ENVIRONMENT=production`, `DEBUG=false`, `SECURE_COOKIES=true`, `LOG_JSON=true`.
- [ ] `FRONTEND_URL` and `ALLOWED_ORIGINS` are the real `https://` origin (no localhost).
- [ ] TLS valid, HTTP redirects to HTTPS, HSTS present
      (`curl -sI https://<DOMAIN> | grep -i strict-transport`).
- [ ] CSP present and the hosted payment page still opens the Razorpay modal - an over-tight CSP
      breaks checkout and only shows up on the payment page
      (`curl -sI https://<DOMAIN> | grep -i content-security-policy`).
- [ ] Exactly one process with `SCHEDULER_ENABLED=true` (section 5).
- [ ] SMTP configured and a real invitation/reset email received (not just accepted by the relay).
- [ ] `SENTRY_DSN` set, a deliberate test error visible in Sentry, and the event confirmed free of
      tokens and customer PII.
- [ ] Uptime monitor on `/api/v1/health/ready` (alert on 503) and a log alert on the scheduler
      summary line going missing.
- [ ] Organization settings complete: legal name, GSTIN, address, invoice prefixes and next
      numbers, payment terms, tax rate - these print on customer-facing PDFs.
- [ ] Roles reviewed: staff have `viewer`/`finance`/`admin` as appropriate, not `owner`.
