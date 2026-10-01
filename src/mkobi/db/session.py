from collections.abc import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager

from mkobi.config import get_config
from mkobi.db.base import Base

logger = logging.getLogger(__name__)

# Global engine and sessionmaker (initialized once)
_engine = None
_SessionLocal = None


async def get_async_engine() -> AsyncEngine:
    """Return initialized SQLAlchemy async engine (creates on first call).

    Returns:
        AsyncEngine: SQLAlchemy async engine for database operations.
    """
    global _engine
    if _engine is None:
        config = get_config()
        DATABASE_URL = config.DATABASE_URL

        if DATABASE_URL is None:
            raise ValueError(
                "DATABASE_URL is not configured. "
                "Set DATABASE__PASSWORD environment variable for production "
                "or ensure database password is configured for development."
            )

        # Replace postgresql:// with postgresql+asyncpg://
        if DATABASE_URL.startswith("postgresql://"):
            DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

        logger.info("Initializing async engine for %s", DATABASE_URL.split("@")[-1])
        _engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
        )
    return _engine


async def get_async_sessionlocal() -> async_sessionmaker[AsyncSession]:
    """Return initialized async_sessionmaker (creates on first call).

    Returns:
        async_sessionmaker: Configured factory for async sessions.
    """
    global _SessionLocal
    if _SessionLocal is None:
        engine = await get_async_engine()
        _SessionLocal = async_sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _SessionLocal


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions.

    Creates a new async session and ensures it is closed after use. It ends no
    transaction: leaving the context closes the session but does not commit.

    Example:
        ```python
        async with get_session() as db:
            result = await db.execute(select(User))
        ```

    Yields:
        AsyncSession: SQLAlchemy async session.
    """
    SessionLocal = await get_async_sessionlocal()
    async with SessionLocal() as db:
        yield db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Generator for async sessions to be used in FastAPI dependencies.

    Yields:
        AsyncSession: SQLAlchemy async session.
    """
    async with get_session() as db:
        yield db


async def init_db() -> None:
    """Create all tables defined in the models.

    Note:
        In production, it is preferable to use migrations (e.g., Alembic)
        instead of automatic table creation.
    """
    logger.info("Initializing database tables...")
    engine = await get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized.")


async def drop_db() -> None:
    """Drop all tables defined in the models.

    Warning:
        Destructive operation! Use only for tests
        or when completely reinitializing the database.
    """
    logger.warning("Dropping all database tables!")
    engine = await get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def dispose_engine() -> None:
    """Dispose the global database engine on application shutdown.

    This function safely disposes the async engine connection pool,
    releasing all database connections. Safe to call multiple times.
    """
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Database engine disposed cleanly")
