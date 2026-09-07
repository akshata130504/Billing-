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
`/api/v1/health` and log in.

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

## 3. Routine checks

```bash
rb ps                                              # all "healthy"/"running"
curl -fsS https://<DOMAIN>/api/v1/health | jq      # status healthy, database connected
rb exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from webhook_events where created_at > now() - interval '1 day';"
df -h /var/lib/docker                              # disk
docker system df                                   # image/volume usage; `docker image prune` after upgrades
```

## 4. Common failures

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
| `413 Request Entity Too Large` on CSV import | file larger than the 10 MB nginx limit (the API itself allows 5 MB) | Split the CSV. |
| `429 RATE_LIMITED` on login | more than `AUTH_RATE_LIMIT` attempts per minute from one IP (often a shared office NAT) | Wait a minute or raise `AUTH_RATE_LIMIT`. |
| Account locked after failed logins | 5 failures -> 15 minute lock | Wait or reset the password via forgot-password. |
| `frontend` container restarts in a loop with `host not found in upstream` | old nginx config without the resolver | Rebuild the web image (`rb up -d --build frontend`). |
| Disk full | Docker logs or old images | Log rotation is configured; `docker image prune -a`; move `/var/lib/docker` or backups to a larger disk. |

## 5. Maintenance tasks

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
