"""Dashboard management service.

Provides business logic for CRUD operations with dashboards.

All operations are performed through injected repositories with validation,
permission checking, and logging.

Implements IDashboardService interface for dependency injection.
"""

import logging
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models import dashboard as dashboard_model
from mkobi.interfaces.service_interfaces import IDashboardService
from mkobi.interfaces.repository_interfaces import (
    IDashboardRepository,
    IAccessRepository,
)
from mkobi.models.dashboard import (
    DashboardConfig,
    DashboardRead,
    DashboardSummary,
)
from mkobi.models.enums import DashboardPermission, ErrorCode, UserRole
from mkobi.models.layout import LayoutRead
from mkobi.utils.exceptions import AppException, PermissionDeniedException

logger = logging.getLogger(__name__)


def _resolve_permission(permission: DashboardPermission | str) -> DashboardPermission:
    """Normalise and validate a dashboard permission name.

    Accepts either a :class:`DashboardPermission` member or the stored string.
    The string is normalised (``strip()`` + ``lower()``) and resolved against
    the enum. An unrecognised name **fails loudly** with :class:`AppException`
    and ``VALIDATION_ERROR`` rather than being silently accepted under the
    requested name.

    Args:
        permission: Access level as an enum member or a string.

    Returns:
        The matching DashboardPermission member.

    Raises:
        AppException: If the name is not a member of DashboardPermission.
    """
    if isinstance(permission, DashboardPermission):
        return permission
    normalised = str(permission).strip().lower()
    try:
        return DashboardPermission(normalised)
    except ValueError:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=f"Invalid access level: '{permission}'",
        ) from None


class DashboardService(IDashboardService):
    """Dashboard service class."""

    def __init__(
        self,
        dashboard_repo: IDashboardRepository,
        access_repo: IAccessRepository,
    ) -> None:
        """Initialize service with injected repositories.

        Args:
            dashboard_repo: Dashboard repository instance.
            access_repo: Access repository instance.
        """
        self.dashboard_repo = dashboard_repo
        self.access_repo = access_repo
        logger.debug("DashboardService initialized with injected repositories")

    async def create_dashboard(
        self,
        name: str,
        config: dict[str, Any],
        owner_id: UUID,
        db: AsyncSession,
        description: str | None = None,
        layout_id: UUID | None = None,
    ) -> DashboardRead:
        """Create new dashboard.

        Args:
            name: Dashboard name.
            config: Dashboard configuration in JSON-compatible dict format.
            owner_id: Owner user identifier.
            db: Async database session.
            description: Optional dashboard description.
            layout_id: Optional layout identifier.

        Returns:
            DashboardRead: Created dashboard model.

        Raises:
            ValueError: If configuration is incorrect.
            SQLAlchemyError: On database error.
        """
        config_obj = DashboardConfig(**config)
        self._validate_config(config_obj)

        try:
            # Create dashboard through repository
            dashboard_obj = await self.dashboard_repo.create(
                db=db,
                name=name,
                config=config_obj.model_dump(),
                created_by=owner_id,
                description=description,
                layout_id=layout_id,
            )

            if dashboard_obj is None:
                raise ValueError("Failed to create dashboard")

            logger.info(
                "Dashboard created: id=%s, name=%s",
                dashboard_obj.id,
                dashboard_obj.name,
            )

            # Grant admin permission to owner if access_repo is available
            if self.access_repo is not None:
                await self.access_repo.grant_access(
                    db=db,
                    user_id=owner_id,
                    dashboard_id=dashboard_obj.id,
                    permission=DashboardPermission.ADMIN,
                )

            logger.info(
                "Admin access granted: user_id=%s, dashboard_id=%s",
                owner_id,
                dashboard_obj.id,
            )

            # Convert to Pydantic model with layout data
            return await self._dashboard_to_read(dashboard_obj, db, DashboardPermission.ADMIN)

        except ValueError:
            # Validation errors don't require rollback (transaction not started)
            raise
        except Exception as e:
            await db.rollback()
            logger.error(
                "Error creating dashboard name=%s, owner_id=%s: %s",
                name,
                owner_id,
                e,
            )
            raise

    async def get_dashboard(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        db: AsyncSession,
        user_role: str | None = None,
    ) -> DashboardRead | None:
        """Get a dashboard by ID with access control.

        Args:
            dashboard_id: UUID of the dashboard to retrieve.
            user_id: UUID of the requesting user.
            db: Async database session.
            user_role: Role of the requesting user (for admin bypass).

        Returns:
            DashboardRead if the dashboard exists and access is allowed.
            None if the dashboard does not exist.

        Raises:
            PermissionDeniedException: If the dashboard exists but the user
                does not have access to it.
        """
        # Check dashboard existence
        dashboard_obj = await self.dashboard_repo.get(dashboard_id, db)
        if dashboard_obj is None:
            logger.warning("Dashboard not found: id=%s", dashboard_id)
            return None

        # Admin bypass: admins can access any dashboard
        if user_role == UserRole.ADMIN:
            logger.info(
                "Dashboard accessed by admin: id=%s, user_id=%s",
                dashboard_id,
                user_id,
            )
            return await self._dashboard_to_read(dashboard_obj, db, DashboardPermission.ADMIN)

        # Check user access if access_repo is available
        permission = None
        if self.access_repo is not None:
            permission = await self.access_repo.check_access(user_id, dashboard_id, db)

        if permission is None:
            logger.warning(
                "Access denied: user_id=%s, dashboard_id=%s",
                user_id,
                dashboard_id,
            )
            raise PermissionDeniedException("Access denied")

        logger.info(
            "Dashboard accessed: id=%s, user_id=%s, permission=%s",
            dashboard_id,
            user_id,
            permission,
        )

        # Convert to Pydantic model with layout data
        try:
            dashboard_read = await self._dashboard_to_read(
                dashboard_obj, db, permission
            )
            return dashboard_read
        except Exception as e:
            logger.error(
                "Error in get_dashboard for dashboard_id=%s: %s",
                dashboard_obj.id,
                e,
                exc_info=True,
            )
            raise

    async def get_dashboard_by_name(
        self,
        name: str,
        db: AsyncSession,
    ) -> DashboardRead | None:
        """Get dashboard by name.

        Args:
            name: Dashboard name.
            db: Async database session.

        Returns:
            DashboardRead or None if not found.
        """
        dashboard = await self.dashboard_repo.get_by_name(name, db)
        if dashboard is None:
            return None
        return await self._dashboard_to_read(dashboard, db, DashboardPermission.VIEW)

    async def get_user_dashboards(
        self,
        user_id: UUID,
        db: AsyncSession,
        user_role: str | None = None,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[DashboardSummary]:
        """Get user dashboards with their access permission.

        Args:
            user_id: User ID.
            db: Async database session.
            user_role: User role (for admin bypass).
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            list[DashboardSummary]: List of user dashboards with permission.
        """
        is_admin = user_role == UserRole.ADMIN

        dashboards_with_permission = await self.dashboard_repo.get_by_user(
            user_id, db, is_admin=is_admin, limit=limit, skip=skip
        )
        result: list[DashboardSummary] = []
        for dashboard, permission in dashboards_with_permission:
            # For admin bypass, use VIEW as default permission
            # (admin has full access to all dashboards)
            perm_value = permission if permission else DashboardPermission.VIEW
            result.append(
                DashboardSummary(
                    id=dashboard.id,
                    name=dashboard.name,
                    description=dashboard.description,
                    permission=DashboardPermission(perm_value),
                    created_at=dashboard.created_at,
                )
            )
        return result

    async def update_dashboard(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
        update_data: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        permission: DashboardPermission | None = None,
    ) -> DashboardRead | None:
        """Update dashboard.

        Args:
            dashboard_id: Dashboard ID.
            db: Async database session.
            update_data: Data for update (config, layout_id, etc.).
            config: Configuration (optional, for backward compatibility).
            permission: User's permission level for response (optional).

        Returns:
            DashboardRead or None if not found.
        """
        if update_data is None:
            data = {}
        elif hasattr(update_data, "model_dump"):
            data = update_data.model_dump(exclude_unset=True)
        elif hasattr(update_data, "dict"):
            data = update_data.dict(exclude_unset=True)
        else:
            data = dict(update_data)

        # Handle config parameter if provided
        if config is not None:
            data["config"] = config

        if not data:
            logger.warning(
                "No data for dashboard update: dashboard_id=%s", dashboard_id
            )
            return None

        # Validate configuration if provided
        config_to_validate = data.get("config")
        if config_to_validate:
            if isinstance(config_to_validate, dict):
                config_to_validate = DashboardConfig(**config_to_validate)
            self._validate_config(config_to_validate)

        updated = await self.dashboard_repo.update(
            dashboard_id,
            db,
            **data,
        )
        if updated is None:
            return None
        await db.commit()

        perm = permission if permission is not None else DashboardPermission.VIEW
        return await self._dashboard_to_read(updated, db, perm)

    async def delete_dashboard(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Delete dashboard.

        Args:
            dashboard_id: Dashboard ID.
            db: Async database session.

        Returns:
            bool: True if deletion successful.
        """
        result = await self.dashboard_repo.delete(dashboard_id, db)
        await db.commit()
        return bool(result)

    async def get_all_dashboards(
        self,
        db: AsyncSession,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[DashboardRead]:
        """Get dashboards, optionally bounded.

        Args:
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            list[DashboardRead]: List of dashboards.
        """
        dashboards = await self.dashboard_repo.get_all(db, limit=limit, skip=skip)
        result = []
        for dashboard in dashboards:
            result.append(await self._dashboard_to_read(dashboard, db, DashboardPermission.VIEW))
        return result

    async def grant_access(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        permission: DashboardPermission,
        db: AsyncSession,
    ) -> bool:
        """Grant user access to dashboard.

        Args:
            dashboard_id: Dashboard ID.
            user_id: User ID.
            permission: Access level (``DashboardPermission`` member).
            db: Async database session.

        Returns:
            bool: True if access granted.
        """
        resolved_permission = _resolve_permission(permission)

        # Check dashboard existence
        dashboard_obj = await self.dashboard_repo.get(dashboard_id, db)
        if dashboard_obj is None:
            raise ValueError(f"Dashboard with id={dashboard_id} not found")

        if self.access_repo is None:
            raise ValueError("access_repo is required for grant_access")

        # Grant access through repository
        await self.access_repo.grant_access(
            db=db,
            user_id=user_id,
            dashboard_id=dashboard_id,
            permission=resolved_permission,
        )

        await db.commit()

        logger.info(
            "Access granted: user_id=%s, dashboard_id=%s, permission=%s",
            user_id,
            dashboard_id,
            permission,
        )

        return True

    async def revoke_access(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Revoke user access to dashboard.

        Args:
            dashboard_id: Dashboard ID.
            user_id: User ID.
            db: Async database session.

        Returns:
            True if access was revoked, False if record not found.
        """
        if self.access_repo is None:
            raise ValueError("access_repo is required for revoke_access")

        result = await self.access_repo.revoke_access(
            user_id=user_id, dashboard_id=dashboard_id, db=db
        )

        if result:
            await db.commit()
            logger.info(
                "Access revoked: user_id=%s, dashboard_id=%s",
                user_id,
                dashboard_id,
            )
        else:
            logger.warning(
                "Access record not found for revocation: user_id=%s, dashboard_id=%s",
                user_id,
                dashboard_id,
            )

        return bool(result)

    async def get_dashboard_access_list(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        """Get access records for a dashboard, optionally bounded.

        Args:
            dashboard_id: Dashboard ID.
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of access records as dictionaries.
        """
        if self.access_repo is None:
            raise ValueError("access_repo is required for get_dashboard_access_list")

        try:
            access_records = await self.access_repo.get_by_dashboard(
                dashboard_id=dashboard_id, db=db, limit=limit, skip=skip
            )

            return [
                {
                    "user_id": str(record.user_id),
                    "dashboard_id": str(record.dashboard_id),
                    "permission": record.permission,
                }
                for record in access_records
            ]
        except Exception as e:
            logger.error(
                "Error getting access list for dashboard id=%s: %s",
                dashboard_id,
                e,
            )
            raise

    # --- Helper methods ---

    def _validate_config(self, config: DashboardConfig) -> None:
        """Validate dashboard configuration."""
        if not config.graph_types:
            logger.error("Dashboard configuration missing graph types")
            raise ValueError(
                "Dashboard configuration must contain at least one graph type"
            )

    async def _dashboard_to_read(
        self,
        dashboard_obj: dashboard_model.Dashboard,
        db: AsyncSession,
        permission: DashboardPermission | None = None,
    ) -> DashboardRead:
        """Convert dashboard ORM model to Pydantic DashboardRead model.

        This method injects the `permission` field into DashboardRead, which is NOT
        present in the database schema. The permission is determined at runtime based
        on the requesting user's access level and passed explicitly to this method.

        Args:
            dashboard_obj: Dashboard ORM model instance from database.
            db: Async database session (unused but kept for interface consistency).
            permission: User's permission level for this dashboard. If not provided,
                defaults to DashboardPermission.VIEW.

        Returns:
            DashboardRead: Pydantic model with permission injected.
        """
        # Handle config which might be None or empty dict
        config_data = dashboard_obj.config
        if config_data is None or config_data == {}:
            config = DashboardConfig(graph_types=["bar"])
        else:
            config = DashboardConfig(**config_data)

        # Use default permission if not provided
        perm_value = permission if permission is not None else DashboardPermission.VIEW

        dashboard_dict = {
            "id": dashboard_obj.id,
            "name": dashboard_obj.name,
            "description": dashboard_obj.description,
            "config": config,
            "permission": perm_value,
            "layout_id": dashboard_obj.layout_id,
            "created_at": dashboard_obj.created_at,
            "updated_at": dashboard_obj.updated_at,
        }
        # Add layout if present
        if dashboard_obj.layout:
            dashboard_dict["layout"] = LayoutRead.model_validate(dashboard_obj.layout)
        return cast(DashboardRead, DashboardRead.model_validate(dashboard_dict))
