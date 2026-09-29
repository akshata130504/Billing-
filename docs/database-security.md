# Database security: least privilege, TLS, encryption at rest

Covers three things: running the app as a DML-only database role, TLS to a remote PostgreSQL,
and the keyring that encrypts integration credentials and TOTP seeds.

## 1. Two database roles

| Role | Used by | Rights |
| --- | --- | --- |
| **owner / migration** (`POSTGRES_USER` in the compose stack, e.g. `rooman`) | `alembic upgrade head` (the entrypoint's migration step), backups, admin sessions | owns the schema and every table. It can run DDL. |
| **runtime** (`APP_POSTGRES_USER`, e.g. `rooman_app`) | API (gunicorn) and scheduler | `CONNECT`; `USAGE` on schema `public`; `SELECT/INSERT/UPDATE/DELETE` on all tables; `USAGE/SELECT` on sequences; `EXECUTE` on functions. **No** `CREATE`, `TRUNCATE`, `REFERENCES`, `TRIGGER`, ownership, superuser, `CREATEDB` or `CREATEROLE`. |

If the API is compromised, for example through SQL injection or RCE, the attacker gets the
runtime role's rights. It can still read and write data, but it cannot drop or alter tables,
create functions or triggers, truncate, or tamper with `alembic_version`.

**Settings** (`backend/app/core/config.py`):

- The runtime connection comes from `DATABASE_URL`, or from `POSTGRES_USER`/`POSTGRES_PASSWORD` plus `POSTGRES_SERVER`/`PORT`/`DB`.
- The migration connection is `MIGRATION_DATABASE_URL`, or `MIGRATION_POSTGRES_USER`/`MIGRATION_POSTGRES_PASSWORD` on the same host and database. When `DATABASE_URL` is set, its host, database and query options are reused.
- **If no migration credentials are set, migrations use the runtime credentials.** Local development and existing deployments therefore behave exactly as before.
- `backend/alembic/env.py` uses the migration URL. An explicit `sqlalchemy.url`, as used by the tests, still wins.
- `backend/docker/entrypoint.sh` does four things:
  1. Waits for the database using both sets of credentials.
  2. Migrates as the owner.
  3. Runs `unset MIGRATION_*`.
  4. Execs gunicorn, so the API process never holds the owner password.

What the runtime role still needs, all verified:

- The scheduler's `pg_try_advisory_lock` and `pg_advisory_unlock`. `PUBLIC` has `EXECUTE` on these by default.
- `SELECT ... FOR UPDATE [NOWAIT | SKIP LOCKED]`, which needs `UPDATE` on the table.
- `SELECT` on `alembic_version`, used by `/api/v1/health/ready`.

### Enabling it on the compose stack (opt-in, re-runnable)

1. Add these to `.env.production`:

   ```env
   APP_POSTGRES_USER=rooman_app
   APP_POSTGRES_PASSWORD=<openssl rand -base64 24 | tr -d '/+='>
   ```

2. Create the role and grants. This runs `deploy/sql/least_privilege.sql` inside `db` as `POSTGRES_USER`:

   ```bash
   sh deploy/db-least-privilege.sh
   ```

   The script prints a report, for example `tables_with_dml = tables_in_schema` and `runtime_can_create = f`.

3. Restart so that `backend` and `scheduler` connect as `rooman_app`:

   ```bash
   docker compose --env-file .env.production -f docker-compose.prod.yml up -d backend scheduler
   ```

4. Check that `GET /api/v1/health/ready` returns 200. From `docker compose exec db psql -U rooman rooman_billing`, `SELECT usename, count(*) FROM pg_stat_activity GROUP BY 1;` should show `rooman_app` connections.

**Rollback:** remove `APP_POSTGRES_*` from `.env.production` and run step 3 again. The role can stay in place.

`docker-compose.prod.yml` maps `POSTGRES_USER`/`PASSWORD` for `backend` and `scheduler` to `${APP_POSTGRES_USER:-${POSTGRES_USER}}`. It also passes the owner credentials to `backend` only, as `MIGRATION_POSTGRES_*`. The `scheduler` never receives them. The `db` and `backup` services keep using the owner role.

### The SQL script

`deploy/sql/least_privilege.sql` is idempotent. It takes psql variables (`-v owner_role=... -v app_role=... -v app_password=... -v schema_name=...`) or environment variables (`RB_OWNER_ROLE`, `RB_APP_ROLE`, `RB_APP_PASSWORD`, `RB_SCHEMA`; needs psql 15 or later).

- `owner_role` defaults to the connected user and `app_role` to `rooman_app`.
- It refuses to continue if `app_role` equals `owner_role`, if the runtime role has elevated attributes, or if the runtime role owns objects.
- `ALTER DEFAULT PRIVILEGES FOR ROLE <owner>` grants tables, sequences and functions created later by migrations to the runtime role automatically. This only covers objects created **by the owner role**, so always migrate as the owner.
- Re-run it after restoring a dump from another cluster, or to rotate the runtime password.
- For a managed database, run it with an admin account that is a member of the owner role and has `CREATEROLE`.

The password is passed through the environment and executed through `\gexec`, so it is not echoed. Keep `log_statement` at its default `none` while running the script, or the server logs `ALTER ROLE ... PASSWORD`.

## 2. TLS to PostgreSQL

These settings are passed as libpq options through SQLAlchemy `connect_args` (`Settings.db_connect_args`). They apply to the API, the scheduler, Alembic and the entrypoint's wait loop. The existing `-c timezone=UTC` option is kept.

| Variable | Meaning |
| --- | --- |
| `POSTGRES_SSLMODE` | `disable`, `allow`, `prefer`, `require`, `verify-ca` or `verify-full`. Unset = libpq default (`prefer`). |
| `POSTGRES_SSLROOTCERT` | CA bundle used to verify the server, for example the RDS or Cloud SQL CA, mounted into the container. |
| `POSTGRES_SSLCERT` / `POSTGRES_SSLKEY` | Client certificate, when the server requires one. |
| `POSTGRES_REQUIRE_VERIFIED_TLS` | Default `true`. See the rule below. |

A `?sslmode=verify-full` in `DATABASE_URL` also counts.

**Production rule** (`enforce_production_safety`): if the runtime or migration database host is **not private**, startup fails unless the effective sslmode is `verify-full` or `verify-ca`.

- Private hosts are unix sockets, `localhost`, loopback and RFC 1918/ULA IPs, and single-label names such as the compose host `db`.
- Setting `POSTGRES_REQUIRE_VERIFIED_TLS=false` downgrades the failure to a warning. Use it only as a temporary escape hatch.
- The compose default (`POSTGRES_SERVER=db`) is unaffected.
- `require` is **not** accepted for a remote host, because it encrypts without authenticating the server and is open to MITM.

Example for a managed database:

```env
DATABASE_URL=postgresql+psycopg://rooman_app:<pw>@mydb.xxxx.ap-south-1.rds.amazonaws.com:5432/rooman_billing
MIGRATION_POSTGRES_USER=rooman
MIGRATION_POSTGRES_PASSWORD=<owner pw>
POSTGRES_SSLMODE=verify-full
POSTGRES_SSLROOTCERT=/app/certs/rds-global-bundle.pem
```

## 3. Encryption of secrets at rest

Integration credentials (`organization_integrations.encrypted_config`) and TOTP seeds (`users.totp_secret`) are encrypted with a **Fernet keyring** (`backend/app/core/encryption.py`, `MultiFernet`):

- `ENCRYPTION_KEYS=k2026a:<fernet key>,k2025:<old key>`. The first key encrypts; every key decrypts.
- Generate a key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- **Backwards compatible:** the key derived from `SECRET_KEY` (SHA-256), which earlier builds used, remains a decrypt-only fallback while `ENCRYPTION_LEGACY_SECRET_KEY_FALLBACK=true` (the default). With `ENCRYPTION_KEYS` empty, it is also the encryption key, so behaviour is unchanged.
- Malformed keys fail at startup, and the error message never contains key material. If no key fits, decryption returns `None` for TOTP and `{}` for integration configs, and logs an error without plaintext or ciphertext.

**Rotation:**

1. Put the new key **first** in `ENCRYPTION_KEYS`, keep the old ones, and deploy.
2. Run `docker compose ... exec backend python -m backend.app.core.encryption rotate --dry-run`, then again without `--dry-run`. The command re-encrypts every row with the primary key and prints counts only.
3. When the report shows `undecryptable: 0` and everything is on the primary key, remove the old keys. Set `ENCRYPTION_LEGACY_SECRET_KEY_FALLBACK=false` to decouple `SECRET_KEY` rotation from stored secrets.

   Warning: if you rotate `SECRET_KEY` without an `ENCRYPTION_KEYS` entry and without running `rotate`, stored secrets become undecryptable.

`python -m backend.app.core.encryption status` prints the key ids, never the keys.

**KMS:** the provider interface (`EncryptionProvider`) allows an envelope-encryption KMS provider (AWS KMS, GCP KMS, Vault Transit). **Production KMS provider integration requires infrastructure configuration** (KMS key, IAM or workload identity) and is not implemented. Today the keys come from the environment, so protect `.env.production` (mode 600) and the host.

## 4. Verification performed

The verification ran on local PostgreSQL 18 with a `rb_owner_t` owner, a `rb_app_t` runtime role and database `rb_sec_roles`:

1. Ran `alembic upgrade head` as the owner.
2. Applied `least_privilege.sql` twice, via `-f` and via stdin. It is idempotent: 90/90 tables got DML and `runtime_can_create = f`.
3. Ran `backend/tests/test_least_privilege.py` as the runtime role, with `LEAST_PRIVILEGE_DATABASE_URL` and `LEAST_PRIVILEGE_OWNER_DATABASE_URL`. It covers:
   - CRUD on the organizations, users, memberships and customers tables
   - `FOR UPDATE NOWAIT` and `SKIP LOCKED`
   - advisory lock
   - a full `run_billing_jobs`
   - reading `alembic_version`
   - denial of DDL, TRUNCATE, CREATE and triggers (SQLSTATE 42501)
   - default privileges on a table the owner creates later
   - the real app booted with uvicorn as the runtime role: `/health/ready` returns 200, and login, `/auth/me` and customer create/list work

### 2026-09-27 re-verification (branch feat/production-hardening-recovery)

- **Least privilege:** `least_privilege.sql` applied twice (92/92 tables with DML, `runtime_can_create = f`);
  `test_least_privilege.py` 21/21 passed as the runtime role. Then the whole demo seeder ran
  through an API connected **only** as the runtime role (12 customers, 12 subscriptions,
  48 invoices, 28 payments) and a scheduler pass (7 renewals, 10 overdue, 10 reminders):
  0 `permission denied`, 0 HTTP 500.
- **TLS:** a throwaway PostgreSQL 18 cluster with `ssl = on` and `hostnossl ... reject`, server
  certificate signed by a private CA (SAN `localhost`). Results: `verify-full` + correct CA connects
  (TLSv1.3); a rogue CA is refused (`certificate verify failed`); a hostname not in the SAN is refused
  under `verify-full`; plaintext is rejected by the server; `alembic upgrade head` (29 migrations) and
  the app engine work through `POSTGRES_SSLMODE=verify-full` + `POSTGRES_SSLROOTCERT`. The full
  backend suite also ran against that TLS-only server.
- **Encryption at rest:** stored integration credentials are Fernet ciphertext; a wrong key raises
  `DecryptionError` without plaintext; `rotate --dry-run` / `rotate` re-encrypt to the new primary key
  (exit 1 while any row is undecryptable); keys never appear in output or logs.
- **Not verified here:** the production database's own TLS and roles - they need the server steps in
  sections 1 and 2.