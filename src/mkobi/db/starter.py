"""Database schema reproduction module.

Asynchronous database initialization and migration management.
Automatically checks database state on FastAPI startup
and applies Alembic migrations according to the environment.
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
    ADMIN_PASSWORD_MIN_LENGTH,
    WEAK_PASSWORDS,
    WEAK_USERNAMES,
    get_config,
    is_weak_credential,
)
from mkobi.core.security import hash_password
from mkobi.models.enums import EnvironmentEnum, ProcessingStatus, UserRole
from mkobi.services.file_cleanup import cleanup_stale_temp_files

logger = logging.getLogger(__name__)

# Timeout constants for DB operations
DB_CONNECT_TIMEOUT = 10.0
DB_HEALTH_CHECK_TIMEOUT = 5.0


class DatabaseNotFoundError(Exception):
    """Database not found."""


class SchemaNotFoundError(Exception):
    """Database schema not found."""


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

        # Create main engine with connection pool settings
        self._main_engine = create_async_engine(
            main_url,
            pool_pre_ping=True,
            pool_recycle=300,
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
        """Recreate test database from scratch."""
        test_url = self._config.test_database_url or get_config().test_database_url
        admin_url = self._config.test_admin_database_url or get_config().test_admin_database_url
        if not test_url:
            logger.warning("Test database URL not configured, skipping")
            return

        logger.info("Recreating test database...")

        # Parse the test URL to get the database name
        parsed_url = make_url(test_url)
        db_name = parsed_url.database

        # Validate database name against safe pattern to prevent SQL injection
        if not db_name or not re.match(r"^[a-zA-Z0-9_]+$", db_name):
            raise ValueError(f"Invalid database name: {db_name}")

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

            # Connect to the new DB to grant schema privileges
            test_admin_url = urlunparse((
                parsed_admin.scheme,
                parsed_admin.netloc,
                f"/{db_name}",
                None, None, None
            ))
            test_admin_engine = create_async_engine(test_admin_url, isolation_level="AUTOCOMMIT")
            try:
                async with test_admin_engine.connect() as conn:
                    # Grant schema privileges
                    await conn.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO mkobi_app"))
                    # Grant table and sequence privileges on existing objects
                    await conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mkobi_app"))
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
        # production, this guard restates the predicate at the point of use so the
        # two copies cannot diverge. In development a weak value only warns.
        is_weak_password = (
            is_weak_credential(admin_password, WEAK_PASSWORDS)
            or admin_password.lower().startswith("change_me")
            or not admin_password.strip()
            or len(admin_password) < ADMIN_PASSWORD_MIN_LENGTH
        )
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

        # Warn if using a known-weak username (not production due to config validation).
        if is_weak_credential(admin_email, WEAK_USERNAMES):
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