"""FastAPI dependencies for API routes.

This module provides ready-to-use FastAPI dependencies for use in API routes,
including authentication, authorization and access checks.

Typical usage scenarios:
    - Protect endpoints with authentication
    - Check user roles
    - Check dashboard access
    - Get current user
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any, cast

from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import ExpiredSignatureError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

if TYPE_CHECKING:
    from mkobi.db.repositories.access_repo import AccessRepository
    from mkobi.db.repositories.aggregated_data_repo import AggregatedDataRepository
    from mkobi.db.repositories.dashboard_filter_repo import DashboardFilterRepository
    from mkobi.db.repositories.dashboard_repo import DashboardRepository
    from mkobi.db.repositories.filter_repo import FilterRepository
    from mkobi.db.repositories.graph_repo import GraphRepository
    from mkobi.db.repositories.layout_repo import LayoutRepository
    from mkobi.db.repositories.processing_config_repo import ProcessingConfigRepository
    from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository
    from mkobi.db.repositories.registration_request_repo import RegistrationRequestRepository
    from mkobi.services.auth_service import AuthService
    from mkobi.services.dashboard_service import DashboardService
    from mkobi.services.data_service import DataService
    from mkobi.services.filter_service import FilterService
    from mkobi.services.filter_values_service import FilterValuesService
    from mkobi.services.graph_service import GraphService
    from mkobi.services.layout_service import LayoutService
    from mkobi.services.processing_config_service import ProcessingConfigService
    from mkobi.services.processing_log_service import ProcessingLogService
    from mkobi.services.user_service import UserService

from mkobi.core.permissions import (
    check_dashboard_access,
    check_role,
    AuthenticationError,
)
from mkobi.core.redis_client import get_async_redis_client
from mkobi.core.security import (
    RevocationStoreUnavailableError,
    are_tokens_revoked,
    decode_token,
)
from mkobi.interfaces.repository_interfaces import IDashboardFilterValuesRepository
from mkobi.core.temp_password_store import TempPasswordStore
from mkobi.db.session import get_db, get_session  # noqa: F401
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import DashboardPermission, ErrorCode, UserRole
from mkobi.models.user import UserRead
from mkobi.services.auth_service import AuthService
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

# Explicitly define exports for mypy
__all__ = [
    "get_db",
    "get_session",
    "get_current_user_dependency",
    "get_db_dependency",
    "is_password_change_completion_path",
    "require_admin_role",
    "require_editor_role",
    "require_viewer_role",
    "require_role_dependency",
    "require_dashboard_read_access",
    "require_dashboard_write_access",
    "require_dashboard_admin_access",
    "get_dashboard_service",
    "CurrentUser",
    "AdminUser",
    "EditorUser",
    "ViewerUser",
    "get_dashboard_permissions",
    "get_accessible_dashboard_ids",
    "get_user_repository",
    "get_registration_request_repository",
    "get_dashboard_repository",
    "get_access_repository",
    "get_aggregated_data_repository",
    "get_layout_repository",
    "get_filter_repository",
    "get_dashboard_filter_repository",
    "get_dashboard_filter_values_repository",
    "get_processing_config_repository",
    "get_processing_log_repository",
    "get_graph_repository",
    "get_auth_service",
    "get_temp_password_store",
    "get_user_service",
    "get_filter_service",
    "get_filter_values_service",
    "get_layout_service",
    "get_graph_service",
    "get_data_service",
    "get_processing_config_service",
    "get_processing_log_service",
    "get_token_from_header",
    "check_dashboard_access",
    "get_redis_client_dependency",
]


# --- Base dependencies ---


security = HTTPBearer()


async def get_db_dependency() -> AsyncSession:
    """Database session dependency for FastAPI routes.

    Creates a new session for each request and closes it after completion. It
    does not commit and does not roll back: closing the session is not a
    transaction boundary. The request's unit of work belongs to the service
    layer, whose write methods commit their own transactions.

    Yields:
        AsyncSession: SQLAlchemy async session.

    Example:
        @app.get("/users/")
        async def get_users(db: AsyncSession = Depends(get_db_dependency)):
            result = await db.execute(select(User))
            return result.scalars().all()
    """
    async with get_session() as db:
        yield db


# --- Redis dependency ---


async def get_redis_client_dependency() -> Any:
    """Async Redis client dependency for FastAPI routes.

    Returns:
        aioredis.Redis: Asynchronous Redis client instance.
    """
    return get_async_redis_client()


# --- TempPasswordStore dependency ---


def get_temp_password_store() -> TempPasswordStore:
    """DI factory for TempPasswordStore.

    Returns:
        TempPasswordStore: Configured with async Redis client and TTL from settings.
    """
    from mkobi.config import get_config

    config = get_config()
    return TempPasswordStore(
        redis_client=get_async_redis_client(),
        ttl_seconds=config.temp_password_ttl_seconds,
    )


# --- Dependency Injection for repositories ---


def get_user_repository() -> UserRepository:
    """DI factory for user repository.

    Args:
        db: Async database session.

    Returns:
        IUserRepository: User repository implementation.
    """
    from mkobi.db.repositories.user_repo import UserRepository
    return UserRepository()


def get_dashboard_repository() -> DashboardRepository:
    """DI factory for dashboard repository.

    Returns:
        DashboardRepository: Dashboard repository implementation.
    """
    from mkobi.db.repositories.dashboard_repo import DashboardRepository
    return DashboardRepository()


def get_access_repository() -> AccessRepository:
    """DI factory for access repository.

    Returns:
        AccessRepository: Access repository implementation.
    """
    from mkobi.db.repositories.access_repo import AccessRepository
    return AccessRepository()


def get_aggregated_data_repository() -> AggregatedDataRepository:
    """DI factory for aggregated data repository.

    Returns:
        AggregatedDataRepository: Aggregated data repository implementation.
    """
    from mkobi.db.repositories.aggregated_data_repo import AggregatedDataRepository
    return AggregatedDataRepository()


def get_layout_repository() -> LayoutRepository:
    """DI factory for layout repository.

    Returns:
        LayoutRepository: Layout repository implementation.
    """
    from mkobi.db.repositories.layout_repo import LayoutRepository
    return LayoutRepository()


def get_filter_repository() -> FilterRepository:
    """DI factory for filter repository.

    Returns:
        FilterRepository: Filter repository implementation.
    """
    from mkobi.db.repositories.filter_repo import FilterRepository
    return FilterRepository()


def get_dashboard_filter_repository() -> DashboardFilterRepository:
    """DI factory for dashboard filter repository.

    Returns:
        DashboardFilterRepository: Dashboard filter repository implementation.
    """
    from mkobi.db.repositories.dashboard_filter_repo import DashboardFilterRepository
    return DashboardFilterRepository()


def get_processing_config_repository() -> ProcessingConfigRepository:
    """DI factory for processing config repository.

    Returns:
        ProcessingConfigRepository: Processing config repository implementation.
    """
    from mkobi.db.repositories.processing_config_repo import ProcessingConfigRepository
    return ProcessingConfigRepository()


def get_processing_log_repository() -> ProcessingLogRepository:
    """DI factory for processing log repository.

    Returns:
        ProcessingLogRepository: Processing log repository implementation.
    """
    from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository
    return ProcessingLogRepository()


def get_registration_request_repository() -> RegistrationRequestRepository:
    """DI factory for registration request repository.

    Returns:
        RegistrationRequestRepository: Registration request repository implementation.
    """
    from mkobi.db.repositories.registration_request_repo import RegistrationRequestRepository
    return RegistrationRequestRepository()


def get_graph_repository() -> GraphRepository:
    """DI factory for graph repository.

    Returns:
        GraphRepository: Graph repository implementation.
    """
    from mkobi.db.repositories.graph_repo import GraphRepository
    return GraphRepository()


def get_dashboard_filter_values_repository() -> IDashboardFilterValuesRepository:
    """DI factory for dashboard filter values repository.

    Returns:
        DashboardFilterValuesRepository: Dashboard filter values repository implementation.
    """
    from mkobi.db.repositories.dashboard_filter_values_repo import (
        DashboardFilterValuesRepository,
    )
    return DashboardFilterValuesRepository()


# --- Dependency Injection for services ---


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    reg_request_repo: RegistrationRequestRepository = Depends(get_registration_request_repository),
    temp_password_store: TempPasswordStore | None = Depends(get_temp_password_store),
) -> AuthService:
    """DI factory for authentication service.

    Args:
        user_repo: Injected user repository.
        reg_request_repo: Injected registration request repository.
        temp_password_store: Optional temp password store for retrieval tokens.

    Returns:
        AuthService: Authentication service implementation.
    """
    from mkobi.services.auth_service import AuthService
    return AuthService(user_repo, reg_request_repo, temp_password_store=temp_password_store)


def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    """DI factory for user service.

    Args:
        user_repo: Injected user repository.

    Returns:
        UserService: User service implementation.
    """
    from mkobi.services.user_service import UserService

    return UserService(user_repo)


def get_dashboard_service(
    dashboard_repo: DashboardRepository = Depends(get_dashboard_repository),
    access_repo: AccessRepository = Depends(get_access_repository),
) -> DashboardService:
    """DI factory for dashboard service.

    Args:
        dashboard_repo: Injected dashboard repository.
        access_repo: Injected access repository.

    Returns:
        DashboardService: Dashboard service implementation.
    """
    from mkobi.services.dashboard_service import DashboardService
    return DashboardService(dashboard_repo, access_repo)


def get_filter_service(
    filter_repo: FilterRepository = Depends(get_filter_repository),
) -> FilterService:
    """DI factory for filter service.

    Args:
        filter_repo: Injected filter repository.

    Returns:
        FilterService: Filter service implementation.
    """
    from mkobi.services.filter_service import FilterService
    return FilterService(filter_repo)


def get_layout_service(
    layout_repo: LayoutRepository = Depends(get_layout_repository),
) -> LayoutService:
    """DI factory for layout service.

    Args:
        layout_repo: Injected layout repository.

    Returns:
        LayoutService: Layout service implementation.
    """
    from mkobi.services.layout_service import LayoutService
    return LayoutService(layout_repo)


def get_graph_service(
    graph_repo: GraphRepository = Depends(get_graph_repository),
) -> GraphService:
    """DI factory for graph service.

    Args:
        graph_repo: Injected graph repository.

    Returns:
        GraphService: Graph service implementation.
    """
    from mkobi.services.graph_service import GraphService
    return GraphService(graph_repo)


def get_filter_values_service(
    filter_values_repo: IDashboardFilterValuesRepository = Depends(get_dashboard_filter_values_repository),
) -> FilterValuesService:
    """DI factory for filter values service.

    Args:
        filter_values_repo: Injected dashboard filter values repository.

    Returns:
        FilterValuesService: Filter values service implementation.
    """
    from mkobi.services.filter_values_service import FilterValuesService
    return FilterValuesService(repo=filter_values_repo)


def get_processing_config_service(
    config_repo: ProcessingConfigRepository = Depends(get_processing_config_repository),
) -> ProcessingConfigService:
    """DI factory for processing config service.

    Args:
        config_repo: Injected processing config repository.

    Returns:
        ProcessingConfigService: Processing config service implementation.
    """
    from mkobi.services.processing_config_service import ProcessingConfigService
    return ProcessingConfigService(config_repo)


def get_processing_log_service(
    log_repo: ProcessingLogRepository = Depends(get_processing_log_repository),
) -> ProcessingLogService:
    """DI factory for processing log service.

    Args:
        log_repo: Injected processing log repository.

    Returns:
        ProcessingLogService: Processing log service implementation.
    """
    from mkobi.services.processing_log_service import ProcessingLogService
    return ProcessingLogService(log_repo)


def get_data_service(
    agg_repo: AggregatedDataRepository = Depends(get_aggregated_data_repository),
    log_repo: ProcessingLogRepository = Depends(get_processing_log_repository),
    graph_repo: GraphRepository = Depends(get_graph_repository),
    config_service: ProcessingConfigService = Depends(get_processing_config_service),
    dashboard_repo: DashboardRepository = Depends(get_dashboard_repository),
) -> DataService:
    """DI factory for data service.

    Args:
        agg_repo: Injected aggregated data repository.
        log_repo: Injected processing log repository.
        graph_repo: Injected graph repository.
        config_service: Injected processing config service.
        dashboard_repo: Injected dashboard repository for existence checks.

    Returns:
        DataService: Data service implementation.
    """
    from mkobi.services.data_service import DataService
    return DataService(agg_repo, log_repo, graph_repo, config_service, dashboard_repo)


# --- Authentication ---


def get_token_from_header(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Extract token from Authorization header.

    Args:
        credentials: Credentials from header.

    Returns:
        str: JWT token.

    Raises:
        AppException: If header is missing or incorrect.
    """
    if credentials.scheme.lower() != "bearer":
        logger.warning("Invalid authentication scheme: %s", credentials.scheme)
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return str(credentials.credentials)


# Paths that stay reachable while a user is under a forced password change.
# Completing the change, refreshing the silent session, logging out, and reading
# the flag that drives the redirect must all survive the gate below; blocking
# any of them would trap the user or break the mechanism the gate depends on.
# These are the full mounted paths, including the /api/v1 prefix that app.py
# applies when it registers the auth router.
_PASSWORD_CHANGE_EXEMPT_PATHS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/auth/change-password"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/v1/auth/me"),
    }
)


def is_password_change_completion_path(method: str, path: str) -> bool:
    """Return True when the request may proceed despite a forced password change.

    The allow-list is enumerated from ``api/routes/auth.py`` rather than inferred.
    It is keyed by HTTP method and full path because ``POST /auth/change-password``
    is the only way to complete the change, ``POST /auth/refresh`` keeps the silent
    refresh alive, ``POST /auth/logout`` lets a trapped user leave, and
    ``GET /auth/me`` is what carries ``force_password_change`` to the SPA so it
    can perform the redirect. The method and path are taken directly rather than
    the whole request so the predicate is callable with no HTTP pipeline.

    Args:
        method: HTTP method of the request.
        path: Request path including the API prefix, for example
            ``/api/v1/auth/me``.

    Returns:
        bool: True if the route is exempt from the forced-change gate.
    """
    return (method, path) in _PASSWORD_CHANGE_EXEMPT_PATHS


async def get_current_user_dependency(
    request: Request,
    token: str = Depends(get_token_from_header),
    db: AsyncSession = Depends(get_db_dependency),
    redis_client: Any = Depends(get_redis_client_dependency),
) -> UserRead:
    """Get current authenticated user.

    Decodes JWT token, extracts user_id and retrieves user
    data from database. Checks token blacklist for revocation.

    Args:
        token: JWT access token.
        db: Database session.
        redis_client: Async Redis client for token blacklist check.
        request: Incoming request, used to apply the forced password change gate.

    Returns:
        UserRead: Current user data.

    Raises:
        AppException: If token is invalid, revoked, user not found, or the user
            must complete a forced password change on a non-exempt route.
    """
    try:
        payload = decode_token(token)
        if payload is None:
            logger.warning("Invalid token")
            raise AppException(
                code=ErrorCode.INVALID_TOKEN,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check the per-token blacklist and the per-user revocation marker in
        # one pipelined round trip. The verdict semantics are unchanged: a
        # truthy token entry is revoked, and a marker at or after the token's
        # ``iat`` is revoked.
        jti = payload.get("jti")

        user_id_raw = payload.get("user_id")
        if user_id_raw is None:
            logger.warning("Token missing user_id")
            raise AppException(
                code=ErrorCode.INVALID_TOKEN,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = UUID(str(user_id_raw))

        # Reject credentials issued at or before the user's revocation marker.
        # Tokens issued after it (for example, after re-login) are allowed.
        issued_at = payload.get("iat")
        if await are_tokens_revoked(
            redis_client,
            str(jti) if jti else None,
            user_id,
            issued_at if isinstance(issued_at, int) else None,
        ):
            logger.warning("Revoked token used: user_id=%s, jti=%s", user_id, jti)
            raise AppException(
                code=ErrorCode.TOKEN_REVOKED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

        repo = UserRepository()
        user = await repo.get(id=user_id, db=db)
        if user is None:
            logger.warning("User not found: user_id=%s", user_id)
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            logger.warning("User account deactivated: user_id=%s", user_id)
            raise AppException(
                code=ErrorCode.AUTHENTICATION_FAILED,
                detail="User account is deactivated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Server-side enforcement of the forced password change. The flag is
        # already on the loaded UserRead, so this adds no query. A refused user
        # receives 403 PERMISSION_DENIED rather than 401: the SPA's axios
        # interceptor answers any 401 with a silent refresh and, on failure,
        # signs the user out through the login page, which would turn a refusal
        # into a redirect loop. The allow-list keeps the completion path, the
        # silent refresh, logout, and the flag-carrying /auth/me reachable.
        if user.force_password_change and not is_password_change_completion_path(
            request.method, request.url.path
        ):
            logger.warning(
                "Password change required: user_id=%s path=%s",
                user_id,
                request.url.path,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="Password change required",
            )

        logger.info("User authenticated: user_id=%s", user_id)
        return cast(UserRead, UserRead.model_validate(user))
    except AppException:
        raise
    except ExpiredSignatureError as e:
        logger.warning("Token expired")
        raise AppException(
            code=ErrorCode.TOKEN_EXPIRED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except AuthenticationError as e:
        logger.warning("Authentication error: %s", e)
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except RevocationStoreUnavailableError as e:
        # A store fault is a dependency outage, not a credential verdict. It must
        # sit above the blanket arm below so a Redis degradation does not surface
        # as a mass 401 sign-out on every request.
        logger.error("Revocation store unavailable: %s", e)
        raise AppException(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
        ) from e
    except Exception as e:
        logger.error("Error getting current user: %s", e, exc_info=True)
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# --- Role checks ---


def require_admin_role(
    user: UserRead = Depends(get_current_user_dependency),
) -> UserRead:
    """Require admin role.

    Args:
        user: Current authenticated user.

    Returns:
        UserRead: User if has admin role.

    Raises:
        AppException: If user is not admin.
    """
    if not check_role(user.role, UserRole.ADMIN):
        logger.warning(
            "Admin access denied: user_id=%s, role=%s",
            user.id,
            user.role,
        )
        raise AppException(
            code=ErrorCode.INSUFFICIENT_PERMISSIONS,
            detail="Admin access required",
        )
    return user


def require_editor_role(
    user: UserRead = Depends(get_current_user_dependency),
) -> UserRead:
    """Require editor role or higher.

    Args:
        user: Current authenticated user.

    Returns:
        UserRead: User if has editor role or higher.

    Raises:
        AppException: If user has insufficient permissions.
    """
    if not check_role(user.role, UserRole.EDITOR):
        logger.warning(
            "Editor access denied: user_id=%s, role=%s",
            user.id,
            user.role,
        )
        raise AppException(
            code=ErrorCode.INSUFFICIENT_PERMISSIONS,
            detail="Editor access required",
        )
    return user


def require_viewer_role(
    user: UserRead = Depends(get_current_user_dependency),
) -> UserRead:
    """Require viewer role or higher (any authenticated user).

    Args:
        user: Current authenticated user.

    Returns:
        UserRead: User if authenticated.

    Raises:
        AppException: If user is not authenticated.
    """
    # All authenticated users have at least viewer role
    return user


def require_role_dependency(
    required_role: UserRole,
) -> (AsyncSession | UserRead) | None:
    """Create dependency for checking specific role.

    Universal dependency for checking any role.

    Args:
        required_role: Required role (viewer, editor, admin).

    Returns:
        Callable: FastAPI dependency function.

    Raises:
        AppException: If user has insufficient permissions.

    Example:
        @app.get("/admin-only")
        async def admin_only(
            user: UserRead = Depends(require_role_dependency(UserRole.ADMIN)),
        ):
            return {"message": "Access granted"}
    """

    async def role_checker(
        user: UserRead = Depends(get_current_user_dependency),
    ) -> UserRead:
        if not check_role(user.role, required_role):
            logger.warning(
                "Role check failed: user_id=%s, role=%s, required=%s",
                user.id,
                user.role,
                required_role,
            )
            raise AppException(
                code=ErrorCode.INSUFFICIENT_PERMISSIONS,
                detail=f"Role {required_role} or higher required",
            )
        return user

    return role_checker


# --- Dashboard access checks ---


async def require_dashboard_read_access(
    dashboard_id: UUID,
    user: UserRead = Depends(get_current_user_dependency),
    db: AsyncSession = Depends(get_db_dependency),
) -> UserRead:
    """Require read access to dashboard.

    Args:
        dashboard_id: Dashboard ID (from path).
        user: User (obtained via get_current_user_dependency).
        db: Async database session.

    Returns:
        UserRead: User if has access.

    Raises:
        AppException: If user has no read access.

    Example:
        @app.get("/dashboards/{dashboard_id}")
        async def get_dashboard(
            dashboard_id: UUID,
            user: UserRead = Depends(require_dashboard_read_access),
        ):
            return {"message": "Dashboard data"}
    """
    if not await check_dashboard_access(
        user_id=user.id,
        dashboard_id=dashboard_id,
        required_permission=DashboardPermission.VIEW,
        db=db,
    ):
        logger.warning(
            "Read access denied: user_id=%s, dashboard_id=%s",
            user.id,
            dashboard_id,
        )
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="You do not have read access to this dashboard",
        )
    return user


async def require_dashboard_write_access(
    dashboard_id: UUID,
    user: UserRead = Depends(get_current_user_dependency),
    db: AsyncSession = Depends(get_db_dependency),
) -> UserRead:
    """Require write (edit) access to dashboard.

    Args:
        dashboard_id: Dashboard ID (from path).
        user: User (obtained via get_current_user_dependency).
        db: Async database session.

    Returns:
        UserRead: User if has write access.

    Raises:
        AppException: If user has no write access.

    Example:
        @app.put("/dashboards/{dashboard_id}")
        async def update_dashboard(
            dashboard_id: UUID,
            user: UserRead = Depends(require_dashboard_write_access),
        ):
            return {"message": "Update allowed"}
    """
    if not await check_dashboard_access(
        user_id=user.id,
        dashboard_id=dashboard_id,
        required_permission=DashboardPermission.EDIT,
        db=db,
    ):
        logger.warning(
            "Write access denied: user_id=%s, dashboard_id=%s",
            user.id,
            dashboard_id,
        )
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="You do not have write access to this dashboard",
        )
    return user


async def require_dashboard_admin_access(
    dashboard_id: UUID,
    user: UserRead = Depends(get_current_user_dependency),
    db: AsyncSession = Depends(get_db_dependency),
) -> UserRead:
    """Require admin access to dashboard.

    Args:
        dashboard_id: Dashboard ID (from path).
        user: User (obtained via get_current_user_dependency).
        db: Async database session.

    Returns:
        UserRead: User if has admin access.

    Raises:
        AppException: If user has no admin access.

    Example:
        @app.delete("/dashboards/{dashboard_id}")
        async def delete_dashboard(
            dashboard_id: UUID,
            user: UserRead = Depends(require_dashboard_admin_access),
        ):
            return {"message": "Delete allowed"}
    """
    if not await check_dashboard_access(
        user_id=user.id,
        dashboard_id=dashboard_id,
        required_permission=DashboardPermission.ADMIN,
        db=db,
    ):
        logger.warning(
            "Admin access denied: user_id=%s, dashboard_id=%s",
            user.id,
            dashboard_id,
        )
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="You do not have admin access to this dashboard",
        )
    return user


async def get_accessible_dashboard_ids(
    user: UserRead = Depends(get_current_user_dependency),
    db: AsyncSession = Depends(get_db_dependency),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> list[UUID] | None:
    """Resolve the dashboard filter a collection route must apply.

    A collection route has no ``dashboard_id`` to bind, so it cannot
    resolve ``require_dashboard_read_access`` or ``check_dashboard_access``:
    both answer a per-dashboard question. This dependency answers the
    set-shaped one, and it is the only place the collection rule is
    written.

    The admin bypass lives here rather than arriving through
    ``check_dashboard_access``, because a collection route never reaches
    ``_check_access_with_session``.

    Args:
        user: Current authenticated user.
        db: Async database session.
        dashboard_service: Injected dashboard service.

    Returns:
        ``None`` when no dashboard filter applies, meaning the caller
        holds the ``admin`` role and is unrestricted. Otherwise the ids of
        the dashboards the caller may see; an empty list means no grant,
        which is an empty collection and not an error.
    """
    if user.role == UserRole.ADMIN:
        logger.info(
            "Accessible dashboards unrestricted by admin bypass: user_id=%s",
            user.id,
        )
        return None

    dashboards = await dashboard_service.get_user_dashboards(
        user_id=user.id,
        user_role=user.role,
        db=db,
    )
    return [dashboard.id for dashboard in dashboards]


# --- Combined dependencies ---


# Typed aliases for convenience
CurrentUser = Annotated[UserRead, Depends(get_current_user_dependency)]
AdminUser = Annotated[UserRead, Depends(require_admin_role)]
EditorUser = Annotated[UserRead, Depends(require_editor_role)]
ViewerUser = Annotated[UserRead, Depends(require_viewer_role)]


async def get_dashboard_permissions(
    dashboard_id: UUID,
    user: UserRead = Depends(get_current_user_dependency),
    db: AsyncSession = Depends(get_db_dependency),
    access_repo: Any = Depends(get_access_repository),
) -> dict[str, Any]:
    """Get user's access permissions for dashboard.

    Args:
        dashboard_id: Dashboard ID.
        user: User.
        db: Async database session.
        access_repo: Access repository.

    Returns:
        dict: Dictionary with access permission info.
    """
    permission = await access_repo.check_access(
        user_id=user.id,
        dashboard_id=dashboard_id,
        db=db,
    )

    return {
        "user_id": user.id,
        "dashboard_id": dashboard_id,
        "permission": permission,
        "can_read": await check_dashboard_access(
            user_id=user.id,
            dashboard_id=dashboard_id,
            required_permission=DashboardPermission.VIEW,
            db=db,
        ),
        "can_write": await check_dashboard_access(
            user_id=user.id,
            dashboard_id=dashboard_id,
            required_permission=DashboardPermission.EDIT,
            db=db,
        ),
        "can_admin": await check_dashboard_access(
            user_id=user.id,
            dashboard_id=dashboard_id,
            required_permission=DashboardPermission.ADMIN,
            db=db,
        ),
    }