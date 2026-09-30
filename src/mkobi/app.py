"""Factory for FastAPI application.

This module provides the create_app() function to create
a FastAPI instance using the factory pattern.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from mkobi.api import routes
from mkobi.config import get_config
from mkobi.core.logging_config import setup_logging
from mkobi.models.enums import EnvironmentEnum
from mkobi.db.session import get_session
from mkobi.db.starter import (
    DatabaseStarter,
    DatabaseStarterConfig,
    DatabaseNotFoundError,
    SchemaNotFoundError,
)
from mkobi.workers.data_worker import (
    start_stale_processing_cleanup_task,
    mark_orphaned_uploaded_logs_failed,
)
from mkobi.db.session import dispose_engine

# Get configuration and setup logging
config = get_config()
setup_logging(
    log_level=config.log_level,
    log_file=config.log_file,
    json_logging=config.logging.json_logging,
)

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses.

    Sets security headers at the application layer. Nginx proxies handle X-Frame-Options
    (SAMEORIGIN for iframe compatibility during Dash migration) and other baseline headers.

    Headers include:
    - X-Content-Type-Options: Prevents MIME type sniffing (all environments)
    - X-XSS-Protection: Enables browser XSS filter (all environments)
    - Referrer-Policy: Controls referrer information (all environments)
    - Strict-Transport-Security: Enforces HTTPS connections (HSTS) - production only
    - Content-Security-Policy: Prevents XSS and injection attacks (CSP) - production only
    """

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        """Add security headers to response.

        Args:
            request: The incoming HTTP request.
            call_next: The next handler in the middleware chain.

        Returns:
            Response with security headers added.
        """
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        config = get_config()
        if config.environment == EnvironmentEnum.PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = "default-src 'self'"

        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Application lifecycle manager.
    
    Handles startup and shutdown events with proper error handling.
    Logs all errors with context and ensures clean shutdown on startup failure.
    """
    config = get_config()
    starter_config = DatabaseStarterConfig(
        env=config.environment,
        main_database_url=config.DATABASE_URL,
        test_database_url=config.TEST_DATABASE_URL,
        test_admin_database_url=config.TEST_ADMIN_DATABASE_URL,
        auto_migrate=config.auto_migrate,
        migration_script_path=config.migration_script_path,
        alembic_ini_path=config.alembic_ini_path,
        recreate_test_db=config.recreate_test_db,
        logs_retention_days=config.logs_retention_days,
    )
    starter = DatabaseStarter(starter_config)

    # Background task for stale processing cleanup
    cleanup_task: asyncio.Task[None] | None = None

    try:
        logger.info("Initializing application...")
        await starter.startup()
        logger.info("Application initialized successfully")

        # Mark orphaned UPLOADED entries as FAILED on startup
        await mark_orphaned_uploaded_logs_failed()
        logger.info("Checked for orphaned UPLOADED entries")

        # Start background cleanup task for stale processing logs
        cleanup_task = asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=config.stale_processing_cleanup_interval_seconds,
                timeout_minutes=config.stale_processing_timeout_minutes,
            )
        )
        logger.info("Started stale processing cleanup background task")

        yield
    except DatabaseNotFoundError as e:
        logger.error("Database not found: %s", e)
        raise
    except SchemaNotFoundError as e:
        logger.error("Database schema not initialized: %s", e)
        raise
    except Exception as e:
        logger.error("Failed to initialize application: %s", e, exc_info=True)
        raise
    finally:
        logger.info("Shutting down application...")

        # Cancel background cleanup task
        if cleanup_task is not None and not cleanup_task.done():
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Stale processing cleanup task cancelled")

        # Dispose the main application engine
        await dispose_engine()

        await starter.shutdown()


def create_app() -> FastAPI:
    """Creates and configures the FastAPI application.

    Creates a FastAPI instance using the factory pattern,
    configures middleware, error handlers, and registers routes.

    Returns:
        FastAPI: Configured FastAPI application.
    """
    # Create application
    config = get_config()

    # Validate JWT secret key is configured
    if not config.jwt.secret_key:
        logger.error("JWT secret key is not configured. Set JWT__SECRET_KEY environment variable.")
        raise ValueError("JWT_SECRET_KEY must be set")

    # Validate CORS configuration for production
    if config.environment == EnvironmentEnum.PRODUCTION:
        if not config.cors_origins:
            logger.error("CORS origins must be set in production environment")
            raise ValueError("CORS origins must be configured for production")

    application = FastAPI(
        title=config.app.name,
        description="BI Dashboard System API",
        version=config.app.version,
        debug=config.debug,
        docs_url=None if config.environment == EnvironmentEnum.PRODUCTION else "/docs",
        redoc_url=None if config.environment == EnvironmentEnum.PRODUCTION else "/redoc",
        lifespan=lifespan,
    )

    # Configure CORS middleware
    logger.info("Configuring CORS with allowed origins: %s", config.cors_origins)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    # Configure GZip middleware
    application.add_middleware(
        GZipMiddleware,
        minimum_size=1000,
    )

    # Configure security headers middleware
    application.add_middleware(SecurityHeadersMiddleware)

    # Register routers with /api/v1 prefix
    application.include_router(routes.auth.router, prefix="/api/v1")
    application.include_router(routes.users.router, prefix="/api/v1")
    application.include_router(routes.dashboards.router, prefix="/api/v1")
    application.include_router(routes.graphs.router, prefix="/api/v1")
    application.include_router(routes.layouts.router, prefix="/api/v1")
    application.include_router(routes.upload.router, prefix="/api/v1")
    application.include_router(routes.data.router, prefix="/api/v1")
    application.include_router(routes.client_errors.router, prefix="/api/v1")
    application.include_router(routes.processing_configs.router, prefix="/api/v1")
    application.include_router(routes.processing_logs.router, prefix="/api/v1")
    application.include_router(routes.admin.router, prefix="/api/v1")

    @application.get("/health", tags=["health"])
    async def health_check() -> Response:
        """Application health check endpoint.

        Verifies database connectivity by executing a simple query.
        Returns 503 if database is not accessible.
        """
        try:
            # Quick DB connectivity check
            async with get_session() as db:
                await db.execute(text("SELECT 1"))
            return JSONResponse(
                content={"status": "healthy", "database": "connected"}
            )
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "database": "disconnected"},
            )

    @application.get("/health/detailed", tags=["health"])
    async def detailed_health_check() -> dict[str, Any]:
        """Detailed health check with component status.

        Checks database connectivity and returns detailed status information.
        This endpoint is intended for admin use and monitoring systems.
        """
        health_status: dict[str, Any] = {
            "status": "healthy",
            "components": {},
        }

        components: dict[str, Any] = {}

        # Check database connectivity
        try:
            async with get_session() as db:
                await db.execute(text("SELECT 1"))
            components["database"] = {
                "status": "connected",
                "type": "postgresql",
            }
        except Exception as e:
            logger.error("Database health check failed: %s", e)
            health_status["status"] = "unhealthy"
            components["database"] = {
                "status": "disconnected",
                "error": str(e),
            }

        # Check if static files are mounted
        import os
        components["static_files"] = {
            "status": "available" if os.path.isdir("frontend/dist") else "unavailable",
            "path": "frontend/dist",
        }

        health_status["components"] = components
        return health_status

    # Register exception handlers before static files
    from mkobi.utils.exceptions import add_exception_handlers
    add_exception_handlers(application)

    # Setup static files for React SPA (after all health endpoints)
    _setup_static_files(application)

    return application


def _setup_static_files(application: FastAPI) -> None:
    """Sets up static file serving for React SPA.

    Mounts static files from frontend/dist with SPA fallback enabled.
    Uses custom SPAStaticFiles class to serve index.html for non-existent
    paths, enabling proper client-side routing for the React application.
    """
    from pathlib import Path
    from starlette.staticfiles import StaticFiles as BaseStaticFiles
    from starlette.responses import FileResponse
    from starlette.exceptions import HTTPException

    static_dir = Path("frontend/dist")
    index_path = static_dir / "index.html"

    # Only register static files and SPA fallback when frontend build exists
    if static_dir.exists() and index_path.exists():
        logger.info("Mounting static files from %s", static_dir)

        # Set of API prefixes for robust path checking
        # Paths in StaticFiles context come without leading slash
        API_PREFIXES = frozenset({"api/"})

        # Custom StaticFiles that falls back to index.html for non-existent files
        class SPAStaticFiles(BaseStaticFiles):
            """StaticFiles subclass that serves index.html for non-existent paths.

            This enables proper SPA routing where the React router handles
            client-side navigation after the initial index.html is served.

            Note: API routes (/api/*) should not trigger SPA fallback - they return 404.
            """

            async def get_response(self, path: str, scope: dict[str, Any]) -> Any:
                """Override to serve index.html for non-existent files.

                Args:
                    path: Requested file path.
                    scope: ASGI scope dictionary.

                Returns:
                    Response for the requested path or index.html for SPA routes.
                """
                # Check if path starts with any API prefix to avoid intercepting API routes
                # Note: paths in StaticFiles context come without leading slash
                is_api_route = any(path.startswith(prefix) for prefix in API_PREFIXES)

                if not is_api_route:
                    try:
                        return await super().get_response(path, scope)
                    except HTTPException as exc:
                        if exc.status_code == 404:
                            # File not found - serve index.html for SPA routing
                            return FileResponse(str(index_path))
                        raise
                # For API routes, return 404 to let FastAPI's exception handler format it
                # This prevents SPA fallback for API routes
                raise HTTPException(status_code=404, detail="Not found")

        application.mount(
            "/",
            SPAStaticFiles(directory=str(static_dir), html=True),
            name="static",
        )
    else:
        logger.warning(
            "Static directory '%s' not found or missing index.html. "
            "React SPA will not be served. Run 'cd frontend && npm run build' first.",
            static_dir,
        )