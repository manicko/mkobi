"""Access control and permission checking module.

Provides functions and dependencies for checking user access rights
to dashboards and operations in the BI Dashboard system.

Role hierarchy:
    admin > editor > viewer

Where admin has all rights, editor can read and write,
viewer can only read.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import DashboardPermission, UserRole

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
    required_permission: DashboardPermission = DashboardPermission.VIEW,
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

    # Validate required permission. ``DashboardPermission`` is a ``StrEnum``, so
    # a bare string compares equal to its member and this guard is well-typed.
    if required_permission not in [e.value for e in DashboardPermission]:
        raise ValueError(f"Allowed values: {[e.value for e in DashboardPermission]}")

    return await _check_access_with_session(
        user_id, dashboard_id, required_permission, db
    )


async def _check_access_with_session(
    user_id: UUID,
    dashboard_id: UUID,
    required_permission: DashboardPermission,
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

        # Permission hierarchy: admin > edit > view, on the single ladder.
        has_access = (
            PERMISSION_LEVELS[permission] >= PERMISSION_LEVELS[required_permission]
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