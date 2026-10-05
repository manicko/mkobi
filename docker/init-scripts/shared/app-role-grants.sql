-- =============================================================================
-- mkobi_app role and grants - the single referenced definition of the
-- least-privilege application role's privileges.
--
-- This file is loaded by docker/init-scripts/01-create-app-role.sh on the
-- PostgreSQL container's first volume initialisation. It is the authority for
-- what mkobi_app may do; the grants below are transcribed from this file, not
-- duplicated beside it.
--
-- -----------------------------------------------------------------------------
-- Per-tier difference (deliberate; do not harmonise)
-- -----------------------------------------------------------------------------
-- The schema-level privilege granted here on schema `public` is USAGE. The
-- test-tier path in src/mkobi/db/starter.py::recreate_test_database grants
-- USAGE, CREATE. The two are intentionally different, per tier:
--
--   * This artefact runs against the *persistent* database (development and
--     production), whose volume is initialised once. Migrations there run as
--     the postgres superuser, which owns every object in schema public, so the
--     application role never needs CREATE: it only ever reads and writes rows
--     and consumes sequences. USAGE is the least privilege that works.
--
--   * The test-tier path recreates a throwaway database on every run and then
--     applies migrations, and in that tier the freshly created schema is built
--     under conditions where the application role is expected to be able to
--     create schema objects. There, USAGE, CREATE is granted. The test tier is
--     ephemeral; widening it cannot affect a persistent database.
--
-- Harmonising the two would silently change what the test tier can do (or
-- widen the persistent role), so the divergence is recorded, not removed.
--
-- -----------------------------------------------------------------------------
-- Role migration is not a task for Alembic
-- -----------------------------------------------------------------------------
-- Roles are cluster-global, not part of any one database, and a per-database
-- migration cannot describe them. No GRANT, REVOKE, CREATE ROLE or ALTER
-- DEFAULT PRIVILEGES belongs under alembic/; the per-environment grant model
-- would break if a migration created a role. This file, loaded by the init
-- script, is that model's home.
--
-- -----------------------------------------------------------------------------
-- Idempotence
-- -----------------------------------------------------------------------------
-- CREATE ROLE has no IF NOT EXISTS, so the role is created only when absent,
-- reusing the same guard shape as Makefile.ps1's globals load and
-- db/starter.py. The ALTER ROLE that follows re-applies the login password on
-- every run. GRANT and ALTER DEFAULT PRIVILEGES are idempotent in PostgreSQL.
-- Re-running this file against an existing cluster must not abort.
-- =============================================================================

-- Create the role only when it does not already exist. The password is applied
-- separately below so a re-run can refresh it without a DROP.
DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mkobi_app') THEN
        CREATE ROLE mkobi_app WITH LOGIN;
    END IF;
END
$do$;

-- Re-apply login credentials on every run (idempotent).
ALTER ROLE mkobi_app WITH LOGIN PASSWORD :'app_password';
-- CREATEDB is deliberately NOT granted - admin credentials (postgres superuser)
-- are used for CREATE/DROP DATABASE operations in recreate_test_database().

-- Connect to this database.
GRANT CONNECT ON DATABASE :"dbname" TO mkobi_app;

-- Schema privilege: USAGE only, for the reason documented in the header.
GRANT USAGE ON SCHEMA public TO mkobi_app;

-- Data manipulation privileges on all current objects.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mkobi_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mkobi_app;

-- Default privileges for objects created in the future (PostgreSQL 14+).
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mkobi_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO mkobi_app;
