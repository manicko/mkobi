"""Repository for working with dashboards.

Provides CRUD methods for Dashboard model.
All methods use contextual session management and handle errors.
"""

from uuid import UUID
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mkobi.core.logging_config import get_logger
from mkobi.db.models import access as access_model, dashboard as dashboard_model
from mkobi.interfaces.repository_interfaces import IDashboardRepository

logger = get_logger(__name__)


class DashboardRepository(IDashboardRepository):
    """Repository for operations with dashboards.

    Provides methods for creating, reading, updating and deleting
    dashboards in the database. All operations are performed within a
    separate database session with automatic transaction management.
    Implements IDashboardRepository interface.
    """

    async def get(self, id: UUID, db: AsyncSession) -> dashboard_model.Dashboard | None:
        """Get dashboard by ID.

        Args:
            id: Dashboard identifier (UUID).

        Returns:
            Dashboard model or None if not found.
        """
        try:
            result = await db.execute(
                select(dashboard_model.Dashboard)
                .where(dashboard_model.Dashboard.id == id)
                .options(selectinload(dashboard_model.Dashboard.layout))
            )
            dashboard = result.scalar_one_or_none()
            if dashboard:
                logger.info("Dashboard retrieved", extra={"id": str(id)})
            else:
                logger.warning("Dashboard not found", extra={"id": str(id)})
            return cast(dashboard_model.Dashboard | None, dashboard)
        except SQLAlchemyError as e:
            logger.error(
                "Error getting dashboard", extra={"id": str(id), "error": str(e)}
            )
            raise

    async def get_by_user(
        self,
        user_id: UUID,
        db: AsyncSession,
        is_admin: bool = False,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[tuple[dashboard_model.Dashboard, str | None]]:
        """Get dashboards available to user with their access permission.

        Args:
            user_id: User identifier (UUID).
            db: Async database session.
            is_admin: If True, returns all dashboards (admin bypass).
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of tuples (dashboard, permission) where permission is the user's
            access level or None for admin bypass.
        """
        try:
            if is_admin:
                # Admin bypass: return all dashboards without access check
                query = select(dashboard_model.Dashboard).options(
                    selectinload(dashboard_model.Dashboard.layout)
                )
                if limit is not None:
                    query = query.offset(skip).limit(limit)
                result = await db.execute(query)
                dashboards = list(result.scalars().all())
                logger.info(
                    "All dashboards retrieved for admin user",
                    extra={"user_id": str(user_id), "count": len(dashboards)},
                )
                # For admin, permission is None (admin bypass)
                return [(d, None) for d in dashboards]

            query = (
                select(dashboard_model.Dashboard, access_model.DashboardAccess.permission)
                .join(access_model.DashboardAccess)
                .where(access_model.DashboardAccess.user_id == user_id)
                .options(selectinload(dashboard_model.Dashboard.layout))
            )
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            results = result.all()
            dashboards = [(row[0], row[1]) for row in results]
            logger.info(
                "Dashboards retrieved for user",
                extra={"user_id": str(user_id), "count": len(dashboards)},
            )
            return dashboards
        except SQLAlchemyError as e:
            logger.error(
                "Error getting dashboards for user",
                extra={"user_id": str(user_id), "error": str(e)},
            )
            raise

    async def create(
        self, db: AsyncSession, **kwargs: Any
    ) -> dashboard_model.Dashboard | None:
        """Create new dashboard.

        Args:
            db: Async database session.
            **kwargs: Dashboard parameters (name, config).

        Returns:
            Created dashboard model with ID or None on error.
        """
        try:
            dashboard_obj = dashboard_model.Dashboard(**kwargs)
            db.add(dashboard_obj)
            await db.flush()
            await db.refresh(dashboard_obj)
            logger.info(
                "Dashboard created",
                extra={
                    "id": str(dashboard_obj.id),
                    "dashboard_name": dashboard_obj.name,
                },
            )
            return cast(dashboard_model.Dashboard | None, dashboard_obj)
        except SQLAlchemyError as e:
            logger.error("Error creating dashboard", extra={"error": str(e)})
            raise

    async def update(
        self, id: UUID, db: AsyncSession, **kwargs: Any
    ) -> dashboard_model.Dashboard | None:
        """Update dashboard data.

        Args:
            id: Dashboard identifier (UUID).
            db: Async database session.
            **kwargs: Fields to update.

        Returns:
            Updated dashboard model or None if not found.
        """
        try:
            result = await db.execute(
                select(dashboard_model.Dashboard).where(
                    dashboard_model.Dashboard.id == id
                )
            )
            dashboard_obj = result.scalar_one_or_none()
            if not dashboard_obj:
                logger.warning(
                    "Dashboard not found for update",
                    extra={"id": str(id)},
                )
                return None
            for key, value in kwargs.items():
                if hasattr(dashboard_obj, key):
                    setattr(dashboard_obj, key, value)
            await db.flush()
            await db.refresh(dashboard_obj)
            logger.info("Dashboard updated", extra={"id": str(id)})
            return cast(dashboard_model.Dashboard | None, dashboard_obj)
        except SQLAlchemyError as e:
            logger.error(
                "Error updating dashboard",
                extra={"id": str(id), "error": str(e)},
            )
            raise

    async def delete(self, id: UUID, db: AsyncSession) -> bool:
        """Delete dashboard.

        Args:
            id: Dashboard identifier (UUID).
            db: Async database session.

        Returns:
            True if deletion successful, False if dashboard not found.
        """
        try:
            result = await db.execute(
                select(dashboard_model.Dashboard).where(
                    dashboard_model.Dashboard.id == id
                )
            )
            dashboard_obj = result.scalar_one_or_none()
            if not dashboard_obj:
                logger.warning(
                    "Dashboard not found for deletion",
                    extra={"id": str(id)},
                )
                return False
            await db.delete(dashboard_obj)
            await db.flush()
            logger.info("Dashboard deleted", extra={"id": str(id)})
            return True
        except SQLAlchemyError as e:
            logger.error(
                "Error deleting dashboard",
                extra={"id": str(id), "error": str(e)},
            )
            raise

    async def get_all(
        self, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[dashboard_model.Dashboard]:
        """Get dashboards, optionally bounded.

        Args:
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of dashboards.
        """
        try:
            query = select(dashboard_model.Dashboard).options(
                selectinload(dashboard_model.Dashboard.layout)
            )
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            dashboards = list(result.scalars().all())
            logger.info(
                "Dashboards list retrieved",
                extra={"count": len(dashboards)},
            )
            return dashboards
        except SQLAlchemyError as e:
            logger.error(
                "Error getting dashboards list",
                extra={"error": str(e)},
            )
            raise

    async def get_by_name(
        self, name: str, db: AsyncSession
    ) -> dashboard_model.Dashboard | None:
        """Get dashboard by name.

        Args:
            name: Dashboard name.

        Returns:
            Dashboard model or None if not found.
        """
        try:
            result = await db.execute(
                select(dashboard_model.Dashboard)
                .where(dashboard_model.Dashboard.name == name)
                .options(selectinload(dashboard_model.Dashboard.layout))
            )
            dashboard = result.scalar_one_or_none()
            if dashboard:
                logger.info("Dashboard found by name", extra={"dashboard_name": name})
            else:
                logger.warning(
                    "Dashboard not found by name", extra={"dashboard_name": name}
                )
            return cast(dashboard_model.Dashboard | None, dashboard)
        except SQLAlchemyError as e:
            logger.error(
                "Error getting dashboard by name",
                extra={"dashboard_name": name, "error": str(e)},
            )
            raise
