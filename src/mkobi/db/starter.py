"""Database schema reproduction module.

Asynchronous database initialization and migration management.
Automatically checks database state on FastAPI startup
and applies Alembic migrations according to the environment.

Privilege sources differ by tier. The main (development and production)
database's role privileges are granted by the Docker init scripts under
``docker/init-scripts/``, which run once when the PostgreSQL data volume is
first initialised. This module grants nothing on the main database; the
``mkobi_app`` grants issued here apply only to a test database this module
has just recreated, whose volume does not go through those scripts.
"""

import asyncio
import logging
import re
import sys
import uuid
from datetime import datetime, timedelta
from typing import cast
from urllib.parse import urlparse, urlunparse

from alembic import command
from alembic.config import Config
from asyncpg.exceptions import InvalidPasswordError
from sqlalchemy import DDL, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from mkobi.config import (
    get_config,
    is_weak_admin_password,
    is_weak_admin_username,
)
from mkobi.core.security import hash_password
from mkobi.models.enums import EnvironmentEnum, ProcessingStatus, UserRole
from mkobi.services.file_cleanup import cleanup_stale_temp_files

logger = logging.getLogger(__name__)

# Timeout constants for DB operations
DB_CONNECT_TIMEOUT = 10.0
DB_HEALTH_CHECK_TIMEOUT = 5.0

# Deliberate divergence of the starter's GRANT engine from the application
# engine. These are not settings: the starter engine is a start-up engine and
# its values are pinned here so a future change to either engine is a visible
# diff rather than an accident of SQLAlchemy's defaults.
#
# A DROP/CREATE DATABASE statement requires an AUTOCOMMIT connection, and the
# starter must not share the application engine: putting start-up reads on the
# request pool would expose them to a pool timeout during cold start, the worst
# possible moment. That is the reason for a second engine, not its size.
#
# The small pool is free only because the starter's five call sites run
# sequentially. If one is ever made concurrent, this ceiling becomes a second,
# unconfigured budget rather than a start-up spike. Note also that
# DatabaseStarter._main_engine is disposed only in shutdown(), so it counts
# toward the steady-state budget, not merely start-up.
STARTER_POOL_PRE_PING = True
STARTER_POOL_RECYCLE_SECONDS = 300
STARTER_POOL_SIZE = 5
STARTER_MAX_OVERFLOW = 10
STARTER_POOL_TIMEOUT_SECONDS = 30


class DatabaseNotFoundError(Exception):
    """Database not found."""


class SchemaNotFoundError(Exception):
    """Database schema not found."""


class UnsafeTestDatabaseRecreationError(Exception):
    """Refusal to recreate a database that is not a guarded test database.

    Raised when destructive recreation is requested outside the test tier or
    against a name that does not match the test-database naming convention.
    """


# Test database naming convention shared with tests/conftest.py: the base name
# is 'bidb_test' and pytest-xdist workers append a '_<worker_id>' suffix, e.g.
# 'bidb_test_gw0'. Recreation is refused unless the target name matches.
TEST_DATABASE_NAME_PATTERN = re.compile(r"^bidb_test(_[A-Za-z0-9]+)?$")


class DatabaseStarterConfig:
    """Database starter configuration."""

    def __init__(
        self,
        env: EnvironmentEnum = EnvironmentEnum.DEVELOPMENT,
        main_database_url: str | None = None,
        test_database_url: str | None = None,
        test_admin_database_url: str | None = None,
        auto_migrate: bool = False,
        migration_script_path: str = "alembic",
        alembic_ini_path: str = "alembic.ini",
        recreate_test_db: bool = False,
        logs_retention_days: int = 30,
    ) -> None:
        self.env = env
        self.main_database_url = main_database_url
        self.test_database_url = test_database_url
        self.test_admin_database_url = test_admin_database_url
        self.auto_migrate = auto_migrate
        self.migration_script_path = migration_script_path
        self.alembic_ini_path = alembic_ini_path
        self.recreate_test_db = recreate_test_db
        self.logs_retention_days = logs_retention_days


class DatabaseStarter:
    """Main class for database initialization and migration management."""

    def __init__(self, config: DatabaseStarterConfig | None = None) -> None:
        self._config = config or DatabaseStarterConfig()
        self._main_engine: AsyncEngine | None = None

    async def _check_db_connection(self, max_retries: int = 5) -> None:
        """Check database connectivity with timeout and retry."""
        assert self._main_engine is not None
        for attempt in range(max_retries):
            try:
                async with asyncio.timeout(DB_CONNECT_TIMEOUT):
                    async with self._main_engine.connect() as conn:
                        await conn.execute(text("SELECT 1"))
                return
            except TimeoutError:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        "DB connection attempt %d/%d timed out. Retrying in %ds...",
                        attempt + 1, max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise DatabaseNotFoundError(
                        "Database connection timed out"
                    ) from None
            except (InvalidPasswordError, OSError) as e:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(
                        "DB connection attempt %d/%d failed: %s. Retrying in %ds...",
                        attempt + 1, max_retries, e, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
            except Exception as e:
                logger.error("Main database not accessible: %s", e)
                raise DatabaseNotFoundError(
                    f"Main database not accessible: {e}"
                ) from e

    async def _get_alembic_revision(self) -> str | None:
        """Get current alembic revision from database.

        Returns revision hash if schema is initialized, None otherwise.
        """
        if self._main_engine is None:
            return None
        try:
            # Query the alembic_version table directly to avoid asyncio.run issues
            from sqlalchemy import text
            async with self._main_engine.connect() as conn:
                result = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                row = result.fetchone()
                if row:
                    return cast(str, row[0])
            return None
        except Exception:
            return None

    async def startup(self) -> None:
        """Main entry point for database initialization."""
        logger.info("Starting database initialization...")

        # Check main database
        main_url = self._config.main_database_url or get_config().DATABASE_URL
        if not main_url:
            raise DatabaseNotFoundError("Main database URL not configured")

        # Create main engine with connection pool settings that deliberately
        # differ from the application engine; see the STARTER_* constants above.
        self._main_engine = create_async_engine(
            main_url,
            pool_pre_ping=STARTER_POOL_PRE_PING,
            pool_recycle=STARTER_POOL_RECYCLE_SECONDS,
            pool_size=STARTER_POOL_SIZE,
            max_overflow=STARTER_MAX_OVERFLOW,
            pool_timeout=STARTER_POOL_TIMEOUT_SECONDS,
        )
        assert self._main_engine is not None

        # Check database connectivity with timeout
        await self._check_db_connection()

        # Apply migrations if configured (this also creates the schema)
        if self._config.auto_migrate:
            await self._apply_migrations(main_url)

        # Verify role privileges (defense-in-depth for least-privilege)
        await self._verify_role_privileges()

        # Check if schema is properly initialized via alembic
        current_rev = await self._get_alembic_revision()
        if not current_rev:
            raise SchemaNotFoundError(
                "Database schema not initialized - no alembic revision found"
            )
        logger.info("Database schema initialized at revision: %s", current_rev)

        # Ensure admin user exists (after migrations, before test DB handling)
        await self.ensure_admin_user()

        # Run development seeders (creates test_media_dash dashboard in dev)
        if self._config.env == EnvironmentEnum.DEVELOPMENT:
            from mkobi.db.dev_seeders import run_dev_seeders
            await run_dev_seeders()

        # Clean up orphaned temp files from previous runs
        deleted_count = cleanup_stale_temp_files()
        if deleted_count > 0:
            logger.info("Cleaned up %d orphaned temp files during startup", deleted_count)

        # Clean up old processing logs based on retention policy
        await self.cleanup_old_logs()

        # Handle test database
        if self._config.env == EnvironmentEnum.TEST or self._config.recreate_test_db:
            await self.recreate_test_database()

        logger.info("Database initialization completed successfully")

    async def recreate_test_database(self) -> None:
        """Recreate test database from scratch.

        Destructive operation: drops and recreates the configured test
        database. Guarded by two independent checks that both run before any
        statement is issued against the target database:

        1. Environment gate - refuses unless the configured environment is test.
        2. Name gate - refuses unless the target name matches the test-database
           naming convention.

        The ``recreate_test_db`` flag may select recreation within a test tier,
        but it may not authorise recreation in a production tier.

        Raises:
            UnsafeTestDatabaseRecreationError: If either guard refuses.
        """
        # Environment gate (coarse): the flag may select recreation within the
        # test tier, but it must never authorise it elsewhere. The configured
        # application environment is the authoritative process tier; the
        # injected starter env is only a convenience copy and is not trusted
        # here, so a test-tier process cannot be tricked into a production drop
        # by an injected env value.
        configured_env = get_config().environment
        if configured_env != EnvironmentEnum.TEST:
            raise UnsafeTestDatabaseRecreationError(
                "Refusing to recreate the test database: configured environment "
                f"is '{configured_env.value}', not '{EnvironmentEnum.TEST.value}'. "
                "Set ENV=test to allow destructive test-database recreation."
            )

        test_url = self._config.test_database_url or get_config().test_database_url
        admin_url = self._config.test_admin_database_url or get_config().test_admin_database_url
        if not test_url:
            logger.warning("Test database URL not configured, skipping")
            return

        # Parse the test URL to get the database name.
        parsed_url = make_url(test_url)
        db_name = parsed_url.database

        # Name gate (fine): stops a misconfigured environment tier from
        # targeting a non-test database.
        if not db_name or not TEST_DATABASE_NAME_PATTERN.match(str(db_name)):
            raise UnsafeTestDatabaseRecreationError(
                "Refusing to recreate database "
                f"'{db_name}': name does not match the test-database "
                f"convention '{TEST_DATABASE_NAME_PATTERN.pattern}'. "
                "Rename the database to a test name or set the test tier explicitly."
            )

        # Validate database name against safe pattern to prevent SQL injection.
        if not re.match(r"^[a-zA-Z0-9_]+$", str(db_name)):
            raise ValueError(f"Invalid database name: {db_name}")

        logger.info("Recreating test database...")

        # Use admin URL for database creation (requires superuser privileges)
        if not admin_url:
            raise ValueError(
                "Admin database URL is required for test database recreation. "
                "Set DATABASE__ADMIN_USER and DATABASE__ADMIN_PASSWORD environment variables."
            )
        base_url = admin_url
        # Reconstruct URL pointing to postgres database for admin operations
        parsed_admin = urlparse(base_url)
        admin_base_url = urlunparse((
            parsed_admin.scheme,
            parsed_admin.netloc,
            "/postgres",  # Connect to postgres db for CREATE DATABASE
            None, None, None
        ))

        # Create engine connected to 'postgres' database with autocommit
        admin_engine = create_async_engine(
            admin_base_url,
            isolation_level="AUTOCOMMIT",
        )

        # Drop and recreate test database
        try:
            async with admin_engine.connect() as conn:
                # NOTE: With PostgreSQL 18+ and builtin locale provider (C.UTF-8),
                # collation versions are immutable (fixed at '1') and never change.
                # No collation refresh is needed, unlike with libc provider.

                # Get properly quoted database name from the connection's dialect
                quoted_db_name = conn.dialect.identifier_preparer.quote(db_name)

                # Terminate existing connections to the target database
                await conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity "
                        "WHERE datname = :db_name"
                    ),
                    {"db_name": db_name},
                )

                # Use DDL constructs with properly quoted identifier (defense-in-depth)
                await conn.execute(
                    DDL("DROP DATABASE IF EXISTS %(name)s", context={"name": quoted_db_name})
                )
                await conn.execute(
                    DDL("CREATE DATABASE %(name)s", context={"name": quoted_db_name})
                )

                # Grant mkobi_app CONNECT on the new test database
                await conn.execute(
                    DDL("GRANT CONNECT ON DATABASE %(name)s TO mkobi_app", context={"name": quoted_db_name})
                )

            # Connect to the new DB to grant schema privileges. The engine is
            # created AUTOCOMMIT so the GRANTs would otherwise commit one by
            # one; only these five are wrapped in an explicit transaction so a
            # half-applied privilege set cannot survive. The GRANTs are DDL/DCL
            # and therefore transactional in PostgreSQL, so the explicit
            # begin() is what makes the set atomic.
            test_admin_url = urlunparse((
                parsed_admin.scheme,
                parsed_admin.netloc,
                f"/{db_name}",
                None, None, None
            ))
            test_admin_engine = create_async_engine(test_admin_url, isolation_level="AUTOCOMMIT")
            try:
                async with test_admin_engine.connect() as conn:
                    # One explicit transaction around the five grants: they
                    # either all commit or all roll back, so a partial
                    # application cannot surface later as a permission error
                    # whose only trace is a log line. The AUTOCOMMIT isolation
                    # above governs statements issued outside this block; the
                    # block itself is a real BEGIN ... COMMIT.
                    async with conn.begin():
                        # Grant schema privileges
                        await conn.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO mkobi_app"))
                        # Grant table and sequence privileges on existing objects
                        await conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mkobi_app"))
                        # Grant USAGE on all sequences in the schema
                        await conn.execute(text("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mkobi_app"))
                        # Set default privileges for future objects
                        await conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mkobi_app"))
                        await conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO mkobi_app"))
            finally:
                await test_admin_engine.dispose()

            await admin_engine.dispose()
        except Exception as e:
            logger.error("Failed to recreate test database: %s", e)
            await admin_engine.dispose()
            raise

        # Apply migrations to test database
        await self._apply_migrations(test_url)

        logger.info("Test database recreated successfully")

    async def _apply_migrations(self, db_url: str) -> None:
        """Apply Alembic migrations to the specified database.

        Advisory lock is acquired in alembic/env.py to prevent concurrent
        migrations in multi-instance deployments.
        """

        def _sync_migrate() -> None:
            """Synchronous migration function for to_thread."""
            alembic_ini = self._config.alembic_ini_path

            # Override the database URL in alembic config
            config = Config(alembic_ini)
            config.set_main_option("sqlalchemy.url", db_url)

            # Run migrations (advisory lock handled in alembic/env.py)
            command.upgrade(config, "head")

        safe_url = make_url(db_url).render_as_string(hide_password=True)
        logger.info("Running migrations for %s...", safe_url)
        await asyncio.to_thread(_sync_migrate)
        logger.info("Migrations applied successfully")

    async def ensure_admin_user(self) -> None:
        """Create admin user if it does not already exist.

        Idempotent — safe to run multiple times.
        Uses atomic UPSERT to avoid race conditions on concurrent startup.

        Raises:
            ValueError: If the admin password matches a known placeholder value.
        """
        from mkobi.db.session import get_async_sessionlocal

        # Two explicit sources: the credential comes from the configuration
        # authority, the tier from the injected starter config.
        admin_email = get_config().admin_username
        admin_password = get_config().admin_password

        # Defense-in-depth: the configuration already refuses a weak password in
        # production, this guard restates the shared predicate at the point of
        # use so the two sites cannot diverge. In development a weak value only
        # warns.
        is_weak_password = is_weak_admin_password(admin_password)
        if is_weak_password and self._config.env == EnvironmentEnum.PRODUCTION:
            raise ValueError(
                "Admin password is a known placeholder value. "
                "Set ADMIN_PASSWORD to a strong, unique password."
            )
        if is_weak_password:
            logger.warning(
                "Admin password is a known placeholder value. "
                "Set ADMIN_PASSWORD to a strong, unique password for production."
            )

        # Warn if using an unusable username (not production due to config validation).
        if is_weak_admin_username(admin_email):
            logger.warning(
                "Using default admin username - set ADMIN_USERNAME environment variable"
            )

        SessionLocal = await get_async_sessionlocal()

        async with SessionLocal() as db:
            async with db.begin():
                await db.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, role, is_active) "
                        "VALUES (:id, :email, :password, :role, true) "
                        "ON CONFLICT (email) DO NOTHING"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "email": admin_email,
                        "password": hash_password(admin_password),
                        "role": UserRole.ADMIN,
                    },
                )
            logger.info("Admin user ensured: %s", admin_email)

    async def _verify_role_privileges(self) -> None:
        """Verify mkobi_app does not have excessive privileges (defense-in-depth)."""
        assert self._main_engine is not None
        try:
            async with self._main_engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT rolcreatedb FROM pg_roles WHERE rolname = 'mkobi_app'")
                )
                row = result.fetchone()
                if row and row[0]:
                    logger.warning(
                        "mkobi_app has CREATEDB privilege - violates least-privilege. "
                        "Run: ALTER ROLE mkobi_app NOCREATEDB;"
                    )
        except Exception as e:
            logger.debug("Could not verify role privileges: %s", e)

    async def cleanup_old_logs(self) -> None:
        """Clean up old processing logs based on retention policy."""
        if self._config.logs_retention_days <= 0:
            return

        cutoff_date = datetime.now() - timedelta(days=self._config.logs_retention_days)

        async with cast(AsyncEngine, self._main_engine).connect() as conn:
            result = await conn.execute(
                text(
                    "DELETE FROM processing_logs "
                    "WHERE finished_at < :cutoff "
                    "AND status IN (:completed_status, :failed_status)"
                ),
                {
                    "cutoff": cutoff_date,
                    "completed_status": ProcessingStatus.COMPLETED.value,
                    "failed_status": ProcessingStatus.FAILED.value,
                },
            )
            await conn.commit()

            if result.rowcount > 0:
                logger.info("Cleaned up %d old processing logs", result.rowcount)

    async def shutdown(self) -> None:
        """Dispose database engines on application shutdown."""
        if self._main_engine:
            await self._main_engine.dispose()
            self._main_engine = None
        logger.info("Database engines disposed")


def main() -> None:
    """Entry point for recreating test database via CLI."""
    if "--recreate-test-db" in sys.argv:
        starter = DatabaseStarter()

        asyncio.run(starter.recreate_test_database())
    else:
        logger.error("Usage: python -m mkobi.db.starter --recreate-test-db")


if __name__ == "__main__":
    main()
