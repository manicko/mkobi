import asyncio
import logging
import os
from logging.config import fileConfig

from sqlalchemy import Connection, pool, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models to ensure they're registered with Base metadata
from mkobi.db.models import (  # noqa: F401, E402
    AggregatedData,
    Dashboard,
    DashboardAccess,
    DashboardFilterValue,
    Filter,
    Graph,
    Layout,
    ProcessingConfig,
    ProcessingLog,
    RegistrationRequest,
    User,
)
from mkobi.db.base import Base  # noqa: E402
from mkobi.db.migration_lock import (  # noqa: E402
    MIGRATION_ADVISORY_LOCK_KEY,
    MIGRATION_LOCK_MAX_ATTEMPTS,
    MIGRATION_LOCK_RETRY_INTERVAL_SECONDS,
    retry_migration_lock_acquisition,
)

target_metadata = Base.metadata

# Get database URL from alembic config first (set by _apply_migrations)
# If not set, fall back to environment or app config
db_url = config.get_main_option("sqlalchemy.url")
if db_url is None:
    db_url = os.environ.get("DATABASE_URL")
if db_url is None:
    from mkobi.config import get_config

    app_config = get_config()
    db_url = app_config.DATABASE_URL

if db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

logger = logging.getLogger("alembic.env")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(sync_connection: Connection) -> None:
    """Sync wrapper to run migrations using a sync connection proxy."""
    context.configure(
        connection=sync_connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' async mode.

    The run is guarded by a **session-scoped** ``pg_try_advisory_lock``, released
    when the connection closes or the backend exits and explicitly released in a
    ``finally``. The wait for the lock is **bounded** (30 attempts at a fixed 10.0 s
    interval, ~4 m 50 s), no backoff, and **every refusal is logged**. A lock that
    cannot be acquired in that window is a **refusal to migrate**: this function
    raises and the process exits non-zero, rather than running migrations without
    exclusion.

    The lock guards the **migration run only**. It does **not** cover anything
    ``DatabaseStarter.startup`` does *after* ``alembic upgrade head`` returns: the
    admin user upsert, the development seeders, orphan temp-file cleanup, old-log
    cleanup, and test-database recreation (drop/create plus a second migration run).
    Those steps are idempotent today, which is why no exclusion is required for
    them yet; this is not a design claim that they are safe.
    """
    db_url = config.get_main_option("sqlalchemy.url")
    if db_url is None:
        raise ValueError("Database URL is not configured in alembic.ini or env.py")
    connectable: AsyncEngine = create_async_engine(
        db_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:

        async def _try_acquire() -> bool:
            """One non-blocking attempt at the session-scoped migration lock."""
            result = await connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": MIGRATION_ADVISORY_LOCK_KEY},
            )
            return bool(result.scalar())

        acquired = await retry_migration_lock_acquisition(_try_acquire)

        # Raised before the try/finally below, so a refusal never issues an unlock
        # for a lock this session never took.
        if not acquired:
            raise RuntimeError(
                "Could not acquire migration advisory lock "
                f"{MIGRATION_ADVISORY_LOCK_KEY} after "
                f"{MIGRATION_LOCK_MAX_ATTEMPTS} attempts "
                f"({MIGRATION_LOCK_RETRY_INTERVAL_SECONDS * (MIGRATION_LOCK_MAX_ATTEMPTS - 1)}s "
                "waited); refusing to migrate without exclusion"
            )

        logger.info("Acquired migration advisory lock %s", MIGRATION_ADVISORY_LOCK_KEY)

        try:
            await connection.run_sync(do_run_migrations)
        finally:
            # Exactly one unlock, on both the success path and every migration
            # failure. Its own failure is logged, not raised: the lock is
            # session-scoped, so the connection closing immediately after releases
            # it anyway, and an exception here would replace the migration's own
            # (more informative) exception.
            try:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": MIGRATION_ADVISORY_LOCK_KEY},
                )
                await connection.commit()
            except Exception as exc:
                logger.warning(
                    "Failed to release migration advisory lock %s: %s; the session is "
                    "closing and PostgreSQL releases session-scoped locks with it",
                    MIGRATION_ADVISORY_LOCK_KEY,
                    exc,
                )
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (async wrapper)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
