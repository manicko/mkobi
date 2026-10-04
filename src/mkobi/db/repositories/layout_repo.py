"""Repository for layouts.

Provides CRUD methods for Layout model.
All methods use async session and handle errors.
"""

import logging
from uuid import UUID
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from mkobi.db.models import layout as layout_model
from mkobi.interfaces.repository_interfaces import ILayoutRepository
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class LayoutRepository(ILayoutRepository):
    """Repository for layout operations.

    Provides methods for creating, reading, updating and deleting
    layouts in the database. All operations are performed within an
    async session with error handling.
    """

    async def get(self, layout_id: UUID, db: AsyncSession) -> layout_model.Layout | None:
        """Get layout by ID.

        Args:
            layout_id: Layout identifier (UUID).
            db: Async database session.

        Returns:
            Layout model or None if not found.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await db.execute(
                select(layout_model.Layout).where(layout_model.Layout.id == layout_id)
            )
            layout = result.scalar_one_or_none()
            if layout:
                logger.info("Layout retrieved: id=%s", layout_id)
            else:
                logger.warning("Layout not found: id=%s", layout_id)
            return cast(layout_model.Layout | None, layout)
        except SQLAlchemyError as e:
            logger.error("Error getting layout id=%s: %s", layout_id, e)
            raise

    async def get_by_name(self, name: str, db: AsyncSession) -> layout_model.Layout | None:
        """Get layout by name.

        Args:
            name: Layout name.
            db: Async database session.

        Returns:
            Layout model or None if not found.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await db.execute(
                select(layout_model.Layout).where(layout_model.Layout.name == name)
            )
            layout = result.scalar_one_or_none()
            if layout:
                logger.info("Layout found by name: name=%s", name)
            else:
                logger.warning("Layout not found by name: name=%s", name)
            return cast(layout_model.Layout | None, layout)
        except SQLAlchemyError as e:
            logger.error("Error getting layout by name %s: %s", name, e)
            raise

    async def get_all(
        self, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[layout_model.Layout]:
        """Get layouts, optionally bounded.

        Args:
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of layouts.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            query = select(layout_model.Layout)
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            layouts = list(result.scalars().all())
            logger.info("Layouts list retrieved, count: %s", len(layouts))
            return layouts
        except SQLAlchemyError as e:
            logger.error("Error getting layouts list: %s", e)
            raise

    async def create(
        self, db: AsyncSession, **kwargs: Any
    ) -> layout_model.Layout | None:
        """Create new layout.

        Args:
            db: Async database session.
            **kwargs: Layout parameters (name, definition).

        Returns:
            Created layout model with ID or None on error.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            layout_obj = layout_model.Layout(**kwargs)
            db.add(layout_obj)
            await db.flush()
            await db.refresh(layout_obj)
            logger.info("Layout created: id=%s, name=%s", layout_obj.id, layout_obj.name)
            return cast(layout_model.Layout | None, layout_obj)
        except SQLAlchemyError as e:
            logger.error("Error creating layout: %s", e)
            raise

    async def update(
        self, id: UUID, db: AsyncSession, **kwargs: Any
    ) -> layout_model.Layout | None:
        """Update layout data.

        Args:
            id: Layout identifier (UUID).
            db: Async database session.
            **kwargs: Fields to update.

        Returns:
            Updated layout model or None if not found.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await db.execute(
                select(layout_model.Layout).where(layout_model.Layout.id == id)
            )
            layout_obj = result.scalar_one_or_none()
            if not layout_obj:
                logger.warning("Layout not found for update: id=%s", id)
                return None
            for key, value in kwargs.items():
                if hasattr(layout_obj, key):
                    setattr(layout_obj, key, value)
            await db.flush()
            await db.refresh(layout_obj)
            logger.info("Layout updated: id=%s", id)
            return cast(layout_model.Layout | None, layout_obj)
        except SQLAlchemyError as e:
            logger.error("Error updating layout id=%s: %s", id, e)
            raise

    async def delete(self, id: UUID, db: AsyncSession) -> bool:
        """Delete layout.

        Args:
            id: Layout identifier (UUID).
            db: Async database session.

        Returns:
            True if deletion successful, False if layout not found.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await db.execute(
                select(layout_model.Layout).where(layout_model.Layout.id == id)
            )
            layout_obj = result.scalar_one_or_none()
            if not layout_obj:
                logger.warning("Layout not found for deletion: id=%s", id)
                return False
            await db.delete(layout_obj)
            await db.flush()
            logger.info("Layout deleted: id=%s", id)
            return True
        except SQLAlchemyError as e:
            logger.error("Error deleting layout id=%s: %s", id, e)
            raise

    async def get_dashboard_id_for_layout(
        self, layout_id: UUID, db: AsyncSession
    ) -> UUID | None:
        """Get first dashboard ID associated with layout.

        Args:
            layout_id: Layout identifier (UUID).
            db: Async database session.

        Returns:
            Dashboard ID if layout has associated dashboard, None otherwise.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            from mkobi.db.models.dashboard import Dashboard
            result = await db.execute(
                select(Dashboard.id)
                .where(Dashboard.layout_id == layout_id)
                .limit(1)
            )
            dashboard_id_raw = result.scalar_one_or_none()
            if dashboard_id_raw:
                logger.info(
                    "Dashboard found for layout: layout_id=%s, dashboard_id=%s",
                    layout_id,
                    dashboard_id_raw,
                )
                return cast(UUID | None, dashboard_id_raw)
            logger.debug("No dashboard found for layout: id=%s", layout_id)
            return None
        except SQLAlchemyError as e:
            logger.error(
                "Error getting dashboard for layout id=%s: %s", layout_id, e
            )
            raise

    async def get_layouts_by_dashboard_ids(
        self, dashboard_ids: list[UUID], db: AsyncSession,
        limit: int | None = None, skip: int = 0,
    ) -> list[layout_model.Layout]:
        """Get layouts by dashboard IDs, optionally bounded.

        Args:
            dashboard_ids: List of dashboard IDs.
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of layout models.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            from mkobi.db.models.dashboard import Dashboard
            query = (
                select(layout_model.Layout)
                .join(Dashboard, layout_model.Layout.id == Dashboard.layout_id)
                .where(Dashboard.id.in_(dashboard_ids))
            )
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            layouts = list(result.scalars().all())
            logger.info(
                "Layouts retrieved for dashboards: count=%s", len(layouts)
            )
            return layouts
        except SQLAlchemyError as e:
            logger.error("Error getting layouts by dashboard ids: %s", e)
            raise
