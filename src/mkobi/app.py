"""Factory for FastAPI application.

This module provides the create_app() function to create
a FastAPI instance using the factory pattern.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
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
from mkobi.core.redis_client import get_async_redis_client
from mkobi.core.reconciler_lease import (
    DEFAULT_LEASE_TTL_SECONDS,
    ReconcilerLease,
    ReconcilerStatus,
)
from mkobi.models.enums import EnvironmentEnum, LeaseAcquisitionResult, ReconcilerLeaseState
from mkobi.db.session import get_session
from mkobi.db.starter import (
    DatabaseStarter,
    DatabaseStarterConfig,
    DatabaseNotFoundError,
    SchemaNotFoundError,
)
from mkobi.workers.data_worker import start_stale_processing_cleanup_task
from mkobi.db.session import dispose_engine

# Get configuration and setup logging
config = get_config()
setup_logging(
    log_level=config.log_level,
    log_file=config.log_file,
    json_logging=config.logging.json_logging,
)

logger = logging.getLogger(__name__)


def build_security_headers() -> dict[str, str]:
    """Return the baseline security headers stamped on every response.

    The single definition both the ``SecurityHeadersMiddleware`` and the
    unhandled-500 handler in ``mkobi.utils.exceptions`` read. The middleware
    adds the two production-only headers (HSTS and CSP) on top; the three
    returned here apply in every environment, so an unhandled 500 that never
    traverses the middleware still carries them (SECB-3).

    Returns:
        dict[str, str]: Header name to value for the environment-independent set.
    """
    return {
        "X-Content-Type-Options": "nosniff",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }


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
        for header_name, header_value in build_security_headers().items():
            response.headers[header_name] = header_value

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

    # Shared observable state for the stale-processing reconciler. Published on
    # /health/detailed so a loop that has died is distinguishable from an idle
    # one.
    reconciler_status = ReconcilerStatus()
    app.state.reconciler_status = reconciler_status

    # One lease client per process, created once and closed on shutdown. The TTL
    # is bounded by a third of the configured sweep interval, so a dead holder is
    # replaced within one interval.
    lease: ReconcilerLease | None = None
    lease_client: Any = None

    # Background task for stale processing cleanup
    cleanup_task: asyncio.Task[None] | None = None

    try:
        logger.info("Initializing application...")
        await starter.startup()
        logger.info("Application initialized successfully")

        lease_client = get_async_redis_client()
        lease = ReconcilerLease(
            lease_client, ttl_seconds=min(DEFAULT_LEASE_TTL_SECONDS, config.stale_processing_cleanup_interval_seconds // 3)
        )

        # Elect the reconciler holder at boot. The boot path never raises on
        # lease trouble - an unreachable Redis still boots (fail open). The
        # orphan reclamation is NOT run here: it rides the lease-guarded periodic
        # loop below, so a stranded row recovers on a tick rather than waiting
        # for a restart. Acquiring here still seeds ``holding`` so the loop does
        # not have to re-elect on its first tick.
        boot_outcome = await lease.acquire()
        if boot_outcome == LeaseAcquisitionResult.ACQUIRED:
            reconciler_status.lease_state = ReconcilerLeaseState.HOLDER
            logger.info("This replica holds the reconciler lease")
        elif boot_outcome == LeaseAcquisitionResult.NOT_ACQUIRED:
            reconciler_status.lease_state = ReconcilerLeaseState.NOT_HOLDER
            logger.info(
                "Another replica holds the reconciler lease; this replica will not sweep"
            )
        else:
            reconciler_status.lease_state = ReconcilerLeaseState.UNPROTECTED
            logger.critical(
                "Reconciler lease unreachable at startup; will sweep unprotected"
            )

        # Start background cleanup task for stale processing logs
        cleanup_task = asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=config.stale_processing_cleanup_interval_seconds,
                timeout_minutes=config.stale_processing_timeout_minutes,
                lease=lease,
                status=reconciler_status,
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

        # Every teardown step below runs to completion even if an earlier one
        # fails: a single failure must not skip the remaining releases. Each
        # step is wrapped and logged, never swallowed silently.

        # Cancel background cleanup task
        if cleanup_task is not None and not cleanup_task.done():
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("Cleanup task raised during shutdown: %s", e)
            logger.info("Stale processing cleanup task cancelled")

        # Best-effort, owner-checked lease release so a restart does not wait a
        # full TTL. The owning lease closes its own Redis client, so both the
        # release and the client close cannot break the finally chain and skip
        # the engine disposal and starter shutdown below.
        if lease is not None:
            try:
                released = await lease.release()
                if released:
                    logger.info("Released reconciler lease")
            except Exception as e:
                logger.warning("Failed to release reconciler lease: %s", e)
            try:
                await lease.aclose()
            except Exception as e:
                logger.warning("Failed to close reconciler lease client: %s", e)
        elif lease_client is not None:
            # A lease was never constructed (a failure between client creation
            # and lease construction): close the bare client directly.
            try:
                await lease_client.aclose()
            except Exception as e:
                logger.warning("Failed to close reconciler lease client: %s", e)

        # Dispose the main application engine
        try:
            await dispose_engine()
        except Exception as e:
            logger.warning("Failed to dispose database engine: %s", e)

        try:
            await starter.shutdown()
        except Exception as e:
            logger.warning("Failed to shut down database starter: %s", e)


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

    # The three document URLs are gated together in the production tier. They
    # share one condition so the machine-readable /openapi.json cannot be left
    # served while /docs and /redoc are closed. In the shipped production
    # topology this is defence in depth only: nginx proxies /api and the health
    # paths, and serves the SPA for everything else, so it never asks the
    # application for these paths (hand-over HO-4).
    documents_enabled = config.environment != EnvironmentEnum.PRODUCTION

    # Slash handling runs ahead of route resolution and therefore ahead of every
    # Depends. With the default (True), a declared path ending in "/" requested
    # without its slash answers an anonymous 307 before any credential is
    # examined, which is an existence oracle over the four collection paths
    # (EB-4 / EXT-006). Disabling it makes the no-slash variant 404 instead. It
    # must be set here, on the application router: the redirect is decided by the
    # top-level router on the full path, so the per-router redirect_slashes flags
    # elsewhere cannot suppress it (phase 08's D-08-7 deletes those; the ones in
    # this tree are inert for this direction and left untouched). Re-declaring
    # the four routes on "" would only move the oracle to the slash direction.
    application = FastAPI(
        title=config.app.name,
        description="BI Dashboard System API",
        version=config.app.version,
        debug=config.debug,
        docs_url="/docs" if documents_enabled else None,
        redoc_url="/redoc" if documents_enabled else None,
        openapi_url="/openapi.json" if documents_enabled else None,
        redirect_slashes=False,
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
    async def detailed_health_check(request: Request) -> dict[str, Any]:
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

        # Check if static files are mounted. The path and the verdict come from
        # the one helper the mount itself uses, so this component can never
        # report a directory the mount does not serve (ART-007).
        bundle_dir, bundle_available = resolve_frontend_bundle()
        components["static_files"] = {
            "status": "available" if bundle_available else "unavailable",
            "path": str(bundle_dir),
        }

        # Check Redis connectivity. Redis is a hard dependency of every
        # authenticated request (revocation reads fail closed), so its outage has
        # to be observable - but it must never move the overall status or the
        # status code. /health stays database-only, and the anonymous /health
        # body must not grow a Redis key (DP-1, 2026-10-03; DP-2 closed). The
        # factory is not lru_cached and builds a fresh ConnectionPool per call,
        # so the client built here is closed in the finally below - a health poll
        # must not leak a pool.
        redis_client = None
        try:
            redis_client = get_async_redis_client()
            await redis_client.ping()
            components["redis"] = {
                "status": "connected",
                "type": "redis",
            }
        except Exception as e:
            # warning, not error: Redis is degraded here, not a hard dependency
            # failure like the database. The asymmetry is deliberate.
            logger.warning("Redis health check failed: %s", e)
            components["redis"] = {
                "status": "disconnected",
                "type": "redis",
                "error": str(e),
            }
        finally:
            if redis_client is not None:
                try:
                    await redis_client.aclose()
                except Exception as e:
                    logger.warning("Failed to close health check Redis client: %s", e)

        # Report the stale-processing reconciler's liveness and lease state. A
        # dead loop is visible here as a frozen last_success_at; a Redis outage is
        # visible as lease_state "unprotected". This component never changes the
        # overall status - the production healthcheck and nginx gate on /health,
        # which must keep meaning "database reachable".
        status_snapshot = getattr(request.app.state, "reconciler_status", None)
        if status_snapshot is None:
            components["stale_processing_reconciler"] = {
                "status": "not_started",
                "lease_state": ReconcilerLeaseState.UNKNOWN.value,
                "last_success_at": None,
            }
        else:
            last_success = status_snapshot.last_success_at
            components["stale_processing_reconciler"] = {
                "status": "ok" if last_success is not None else "starting",
                "lease_state": status_snapshot.lease_state.value,
                "last_success_at": last_success.isoformat() if last_success is not None else None,
                "last_swept_count": status_snapshot.last_swept_count,
                "sweep_count": status_snapshot.sweep_count,
                "unprotected_ticks": status_snapshot.unprotected_ticks,
            }

        health_status["components"] = components
        return health_status

    # Register exception handlers before static files
    from mkobi.utils.exceptions import add_exception_handlers
    add_exception_handlers(application)

    # Setup static files for React SPA (after all health endpoints)
    _setup_static_files(application)

    return application


def resolve_frontend_bundle() -> tuple[Path, bool]:
    """Resolve the configured SPA bundle directory and its servability.

    The single source of truth for where the built frontend lives and whether it
    can be served. The directory is the configured ``FRONTEND__DIST_DIR``
    (default ``frontend/dist``) resolved to an absolute path, so the reported
    location is meaningful regardless of the process working directory. The
    bundle is servable only when the directory exists *and* carries an
    ``index.html``, which is exactly the condition the catch-all mount below
    requires.

    Both the mount in :func:`_setup_static_files` and the ``static_files``
    component of ``/health/detailed`` call this one helper, so the route table
    and the health verdict cannot drift apart (ART-007).

    Returns:
        tuple[Path, bool]: The resolved bundle directory and whether it is
            servable.
    """
    static_dir = Path(get_config().frontend.dist_dir).resolve()
    index_path = static_dir / "index.html"
    return static_dir, static_dir.is_dir() and index_path.is_file()


def _setup_static_files(application: FastAPI) -> None:
    """Sets up static file serving for React SPA.

    Mounts static files from the configured frontend bundle with SPA fallback
    enabled, but only when the shared bundle predicate reports the bundle
    servable. Uses custom SPAStaticFiles class to serve index.html for
    non-existent paths, enabling proper client-side routing for the React
    application.
    """
    from starlette.staticfiles import StaticFiles as BaseStaticFiles
    from starlette.responses import FileResponse
    from starlette.exceptions import HTTPException

    static_dir, bundle_available = resolve_frontend_bundle()
    index_path = static_dir / "index.html"

    # Only register static files and SPA fallback when the shared predicate
    # reports the bundle servable - the same predicate /health/detailed reports.
    if bundle_available:
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
