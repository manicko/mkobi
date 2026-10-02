"""Access control and permission checking module.

Provides functions and dependencies for checking user access rights
to dashboards and operations in the BI Dashboard system.

Role hierarchy:
    admin > editor > viewer

Where admin has all rights, editor can read and write,
viewer can only read.
"""

import logging
from typing import Any
from uuid import UUID

from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from mkobi.core.security import decode_token, is_token_revoked, is_user_tokens_revoked
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import DashboardPermission, UserRole
from mkobi.models.user import UserRead

logger = logging.getLogger(__name__)


# --- Constants ---


# Role hierarchy (from junior to senior)
ROLE_HIERARCHY: list[UserRole] = [UserRole.VIEWER, UserRole.EDITOR, UserRole.ADMIN]

# Access levels - use DashboardPermission
PERMISSION_LEVELS: dict[DashboardPermission, int] = {
    DashboardPermission.VIEW: 1,
    DashboardPermission.EDIT: 2,
    DashboardPermission.ADMIN: 3,
}
# For backward compatibility also accept "read" as "view" and "write" as "edit"


# --- Exceptions ---


class DashboardPermissionError(Exception):
    """Exception raised when access rights are insufficient."""

    pass


class AuthenticationError(Exception):
    """Exception raised on authentication error."""

    pass


# --- Helper functions ---


def _get_role_level(role: UserRole) -> int:
    """Get role index in hierarchy.

    Args:
        role: User role (UserRole).

    Returns:
        int: Role index in hierarchy (higher = more rights).

    Raises:
        ValueError: If role is unknown.
    """
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError as err:
        logger.error("Unknown role: %s", role)
        raise ValueError(f"Unknown role: '{role}'") from err


# --- Main permission check functions ---


def check_role(user_role: UserRole, required_role: UserRole) -> bool:
    """Check if user role is sufficient for the operation.

    Compares user role level with required level.
    Uses hierarchy: admin > editor > viewer.

    Args:
        user_role: User's role (UserRole).
        required_role: Minimum required role (UserRole).

    Returns:
        bool: True if user role is sufficient, False otherwise.

    Example:
        >>> check_role(UserRole.ADMIN, UserRole.VIEWER)
        True
        >>> check_role(UserRole.EDITOR, UserRole.ADMIN)
        False
        >>> check_role(UserRole.VIEWER, UserRole.VIEWER)
        True
    """
    try:
        user_level = _get_role_level(user_role)
        required_level = _get_role_level(required_role)
        has_access = user_level >= required_level
        logger.debug(
            "Role check: user_role=%s (level %d), required_role=%s (level %d) -> %s",
            user_role,
            user_level,
            required_role,
            required_level,
            has_access,
        )
        return has_access
    except ValueError as e:
        logger.error("Error checking role: %s", e)
        return False


async def check_dashboard_access(
    user_id: UUID,
    dashboard_id: UUID,
    db: AsyncSession,
    required_permission: str = "view",
) -> bool:
    """Check if user has access to dashboard.

    Args:
        user_id: User identifier.
        dashboard_id: Dashboard identifier.
        db: Async database session.
        required_permission: Required access level (view/edit/admin).

    Returns:
        True if access exists, False otherwise.
    """
    logger.info(
        "Checking access: user_id=%s, dashboard_id=%s, required=%s",
        user_id,
        dashboard_id,
        required_permission,
    )

    # Validate required permission
    if required_permission not in [e.value for e in DashboardPermission]:
        raise ValueError(f"Allowed values: {[e.value for e in DashboardPermission]}")

    return await _check_access_with_session(
        user_id, dashboard_id, required_permission, db
    )


async def _check_access_with_session(
    user_id: UUID,
    dashboard_id: UUID,
    required_permission: str,
    db: AsyncSession,
) -> bool:
    """Internal function to check access using session.

    Args:
        user_id: User identifier.
        dashboard_id: Dashboard identifier.
        required_permission: Required access level.
        db: Async database session.

    Returns:
        True if access exists, False otherwise.
    """
    try:
        # Admin bypass: admins can access any dashboard
        user_repo = UserRepository()
        user = await user_repo.get(id=user_id, db=db)
        if user and user.role == UserRole.ADMIN:
            logger.info(
                "Dashboard access granted by admin bypass: user_id=%s, dashboard_id=%s",
                user_id,
                dashboard_id,
            )
            return True

        # Get user access level
        access_repo = AccessRepository()
        permission = await access_repo.check_access(
            user_id=user_id,
            dashboard_id=dashboard_id,
            db=db,
        )

        if permission is None:
            logger.warning(
                "Access not found: user_id=%s, dashboard_id=%s",
                user_id,
                dashboard_id,
            )
            return False

        # Permission hierarchy: admin > edit > view
        # Normalize names for compatibility (read->view, write->edit)
        perm_map = {
            DashboardPermission.VIEW.value: DashboardPermission.VIEW.value,
            DashboardPermission.EDIT.value: DashboardPermission.EDIT.value,
            DashboardPermission.ADMIN.value: DashboardPermission.ADMIN.value,
            "read": DashboardPermission.VIEW.value,
            "write": DashboardPermission.EDIT.value,
        }
        permission_normalized = perm_map.get(permission, permission)
        required_normalized = perm_map.get(required_permission, required_permission)

        permission_levels = {
            DashboardPermission.VIEW.value: 1,
            DashboardPermission.EDIT.value: 2,
            DashboardPermission.ADMIN.value: 3,
        }
        has_access = (
            permission_levels[permission_normalized]
            >= permission_levels[required_normalized]
        )

        logger.info(
            "Access check: user_id=%s, dashboard_id=%s, "
            "permission=%s, required=%s -> %s",
            user_id,
            dashboard_id,
            permission,
            required_permission,
            has_access,
        )

        return has_access

    except Exception as e:
        logger.warning(
            "Dashboard access check failed: user_id=%s, dashboard_id=%s, required=%s: %s",
            user_id,
            dashboard_id,
            required_permission,
            e,
            exc_info=True,
        )
        return False


def _decode_token_cached(token: str) -> dict[str, Any] | None:
    """Decode JWT token without caching.

    Caching removed to ensure token revocation checks always run.
    This function now delegates directly to decode_token.

    Args:
        token: JWT token.

    Returns:
        dict[str, Any] | None: Decoded token data or None.
    """
    result: dict[str, Any] | None = decode_token(token)
    return result


async def get_current_user(
    token: str,
    db: AsyncSession,
    redis_client: aioredis.Redis | None = None,
) -> UserRead:
    """Get current user by token.

    Decodes JWT token, extracts user_id and gets
    user data from database. Checks token blacklist for revocation
    if Redis client is provided.

    Args:
        token: JWT access token.
        db: Async database session.
        redis_client: Optional async Redis client for token revocation checks.
            If not provided, revocation checks are skipped (not recommended for production).

    Returns:
        UserRead: User model with data from database (without password hash).

    Raises:
        AuthenticationError: If token is invalid, revoked, or user not found.
    """
    return await _get_current_user_with_session(token, db, redis_client)


async def _get_current_user_with_session(
    token: str,
    db: AsyncSession,
    redis_client: aioredis.Redis | None = None,
) -> UserRead:
    """Internal function to get user using session.

    Args:
        token: JWT access token.
        db: Async database session.
        redis_client: Optional async Redis client for token revocation checks.

    Returns:
        UserRead: User model (without password hash).

    Raises:
        AuthenticationError: If token is invalid, revoked, or user not found.
    """
    try:
        # Decode token (without caching to ensure revocation checks always run)
        payload = _decode_token_cached(token)
        if payload is None:
            logger.warning("Invalid token")
            raise AuthenticationError("Invalid token")

        user_id_raw = payload.get("user_id")
        if user_id_raw is None:
            logger.warning("Token missing user_id")
            raise AuthenticationError("Invalid token")

        user_id: UUID = UUID(str(user_id_raw))

        # Check if token is revoked (requires Redis client)
        jti = payload.get("jti")
        if redis_client is not None and jti:
            if await is_token_revoked(redis_client, jti):
                logger.warning("Revoked token used: jti=%s", jti)
                raise AuthenticationError("Token has been revoked")

        # Reject credentials issued at or before the user's revocation marker.
        # This path has no production caller (see the module note); the iat is
        # passed for signature consistency with the dependency in api/deps.py.
        if redis_client is not None:
            issued_at = payload.get("iat")
            if await is_user_tokens_revoked(
                redis_client,
                user_id,
                issued_at if isinstance(issued_at, int) else None,
            ):
                logger.warning("User tokens revoked: user_id=%s", user_id)
                raise AuthenticationError("Token has been revoked")

        # Get user from database
        repo = UserRepository()
        user = await repo.get(id=user_id, db=db)
        if user is None:
            logger.warning("User not found: user_id=%s", user_id)
            raise AuthenticationError("User not found")

        logger.info("User authenticated: user_id=%s", user_id)
        # repo.get() already returns UserRead, so just return it
        return user

    except JWTError as e:
        logger.error("JWT decode error: %s", e)
        raise AuthenticationError("Token decode error") from e
    except Exception as e:
        if not isinstance(e, AuthenticationError):
            logger.error("Error getting user: %s", e)
        raise