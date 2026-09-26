-- ============================================================================
-- Rooman Billing - least-privilege runtime database role (idempotent).
--
-- Creates (or updates) a runtime login role that can read and write application data
-- but cannot change the schema, and makes every table/sequence/function the OWNER role
-- creates in the future (i.e. by Alembic migrations) accessible to it automatically.
--
--   owner_role  owns the schema objects and runs `alembic upgrade head`
--               (default: the connected user, e.g. the compose POSTGRES_USER)
--   app_role    what the API + scheduler connect as (default: rooman_app)
--               DML on tables, USAGE/SELECT on sequences, EXECUTE on functions,
--               USAGE on the schema. No CREATE, no DDL, no superuser.
--
-- Run as a superuser or as a member of owner_role that has CREATEROLE, connected to the
-- application database. Parameters come from psql variables (-v) or, psql >= 15, from the
-- environment (RB_OWNER_ROLE, RB_APP_ROLE, RB_APP_PASSWORD, RB_SCHEMA), so the password
-- never has to appear on a command line:
--
--   RB_APP_ROLE=rooman_app RB_APP_PASSWORD='...' \
--     psql -v ON_ERROR_STOP=1 -U rooman -d rooman_billing -f deploy/sql/least_privilege.sql
--
-- or use the wrapper deploy/db-least-privilege.sh for the docker compose stack.
-- Safe to re-run at any time (e.g. after restoring a dump or to rotate the password).
-- See docs/database-security.md.
-- ============================================================================
\set ON_ERROR_STOP on
\set QUIET on

\if :{?owner_role}
\else
\getenv owner_role RB_OWNER_ROLE
\endif
\if :{?owner_role}
\else
\set owner_role :USER
\endif

\if :{?app_role}
\else
\getenv app_role RB_APP_ROLE
\endif
\if :{?app_role}
\else
\set app_role rooman_app
\endif

\if :{?app_password}
\else
\getenv app_password RB_APP_PASSWORD
\endif

\if :{?schema_name}
\else
\getenv schema_name RB_SCHEMA
\endif
\if :{?schema_name}
\else
\set schema_name public
\endif

\echo [least_privilege] owner_role=:owner_role app_role=:app_role schema=:schema_name

-- ---- sanity checks -----------------------------------------------------------------
SELECT 'DO $$BEGIN RAISE EXCEPTION ''app_role must differ from owner_role''; END$$'
WHERE :'app_role' = :'owner_role' \gexec

SELECT format('DO $$BEGIN RAISE EXCEPTION ''owner role %s does not exist''; END$$', :'owner_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'owner_role') \gexec

-- ---- runtime role ----------------------------------------------------------------------
BEGIN;

SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'app_role'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role') \gexec

\if :{?app_password}
-- Generated statement is executed, not echoed. (A server with log_statement=ddl/all would
-- log it - leave log_statement at its default "none" while running this script.)
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'app_role', :'app_password') \gexec
\endif

-- Refuse to continue if the runtime role has elevated attributes (e.g. it pre-existed).
SELECT format(
    'DO $$BEGIN RAISE EXCEPTION ''role %s must not be SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS''; END$$',
    rolname
)
FROM pg_roles
WHERE rolname = :'app_role'
  AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls) \gexec

-- The runtime role must not own schema objects (owners can always run DDL on them).
SELECT format(
    'DO $$BEGIN RAISE EXCEPTION ''role %s owns %s object(s) in schema %s; reassign them to the owner role first (REASSIGN OWNED BY %s TO %s)''; END$$',
    :'app_role', count(*), :'schema_name', :'app_role', :'owner_role'
)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :'schema_name' AND pg_get_userbyid(c.relowner) = :'app_role'
HAVING count(*) > 0 \gexec

-- ---- database + schema -----------------------------------------------------------------
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_role') \gexec
-- Nobody but the owner creates objects in the schema (PostgreSQL 15+ default for public;
-- explicit here for clusters initialised by older versions).
SELECT format('REVOKE CREATE ON SCHEMA %I FROM PUBLIC', :'schema_name') \gexec
SELECT format('REVOKE CREATE ON SCHEMA %I FROM %I', :'schema_name', :'app_role') \gexec
SELECT format('REVOKE CREATE ON DATABASE %I FROM %I', current_database(), :'app_role') \gexec
SELECT format('GRANT USAGE ON SCHEMA %I TO %I', :'schema_name', :'app_role') \gexec

-- ---- existing objects -------------------------------------------------------------------
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO %I', :'schema_name', :'app_role') \gexec
SELECT format('REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA %I FROM %I', :'schema_name', :'app_role') \gexec
SELECT format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO %I', :'schema_name', :'app_role') \gexec
SELECT format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO %I', :'schema_name', :'app_role') \gexec

-- ---- future objects created by the owner (Alembic migrations) --------------------------
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'owner_role', :'schema_name', :'app_role') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT USAGE, SELECT ON SEQUENCES TO %I', :'owner_role', :'schema_name', :'app_role') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT EXECUTE ON FUNCTIONS TO %I', :'owner_role', :'schema_name', :'app_role') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT USAGE ON TYPES TO %I', :'owner_role', :'schema_name', :'app_role') \gexec

COMMIT;

-- ---- report ---------------------------------------------------------------------------
\set QUIET off
SELECT :'app_role' AS runtime_role,
       count(*) AS tables_in_schema,
       count(*) FILTER (WHERE has_table_privilege(:'app_role', c.oid, 'SELECT')
                          AND has_table_privilege(:'app_role', c.oid, 'INSERT')
                          AND has_table_privilege(:'app_role', c.oid, 'UPDATE')
                          AND has_table_privilege(:'app_role', c.oid, 'DELETE')) AS tables_with_dml,
       count(*) FILTER (WHERE pg_get_userbyid(c.relowner) <> :'owner_role') AS tables_not_owned_by_owner_role,
       has_schema_privilege(:'app_role', :'schema_name', 'CREATE') AS runtime_can_create
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :'schema_name' AND c.relkind IN ('r', 'p');
