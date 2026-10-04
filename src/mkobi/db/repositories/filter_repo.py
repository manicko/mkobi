"""Repository for filter operations.

Provides CRUD methods for Filter model.
All methods use contextual session management and handle errors.
"""

import logging
from uuid import UUID
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models import filters as filter_model
from mkobi.interfaces.repository_interfaces import IFilterRepository

logger = logging.getLogger(__name__)


class FilterRepository(IFilterRepository):
    """Repository for filter operations.

    Provides methods for creating, reading, updating and deleting
    filters in the database. All operations are performed within a
    separate database session with automatic transaction management.
    Implements IFilterRepository interface.
    """
    async def get(self, id: UUID, db: AsyncSession) -> filter_model.Filter | None:
        """Get filter by ID.

        Args:
            id: Filter identifier (UUID).
            db: Async database session.

        Returns:
            Filter model or None if not found.
        """
        try:
            result = await db.execute(
                select(filter_model.Filter).where(
                    filter_model.Filter.id == id
                )
            )
            filter_obj = result.scalar_one_or_none()
            if filter_obj:
                logger.info("Filter retrieved: id=%s", id)
            else:
                logger.warning("Filter not found: id=%s", id)
            return cast(filter_model.Filter | None, filter_obj)
        except SQLAlchemyError as e:
            logger.error("Error getting filter id=%s: %s", id, e)
            raise
    async def get_by_name(
        self, name: str, db: AsyncSession
    ) -> filter_model.Filter | None:
        """Get filter by name.

        Args:
            name: Filter name.
            db: Async database session.

        Returns:
            Filter model or None if not found.
        """
        try:
            result = await db.execute(
                select(filter_model.Filter).where(
                    filter_model.Filter.name == name
                )
            )
            filter_obj = result.scalar_one_or_none()
            if filter_obj:
                logger.info("Filter retrieved by name: %s", name)
            else:
                logger.warning("Filter not found by name: %s", name)
            return cast(filter_model.Filter | None, filter_obj)
        except SQLAlchemyError as e:
            logger.error("Error getting filter name=%s: %s", name, e)
            raise
    async def create(self, db: AsyncSession, **kwargs: Any) -> filter_model.Filter | None:
        """Create new filter.

        Args:
            db: Async database session.
            **kwargs: Filter parameters (name, type, config).

        Returns:
            Created filter model with ID or None on error.
        """
        try:
            filter_obj = filter_model.Filter(**kwargs)
            db.add(filter_obj)
            await db.flush()
            await db.refresh(filter_obj)
            logger.info(
                "Filter created: id=%s, name=%s", filter_obj.id, filter_obj.name
            )
            return cast(filter_model.Filter | None, filter_obj)
        except SQLAlchemyError as e:
            logger.error("Error creating filter: %s", e)
            raise
    async def update(
        self, id: UUID, db: AsyncSession, **kwargs: Any
    ) -> filter_model.Filter | None:
        """Update filter data.

        Args:
            id: Filter identifier (UUID).
            db: Async database session.
            **kwargs: Fields to update.

        Returns:
            Updated filter model or None if not found.
        """
        try:
            result = await db.execute(
                select(filter_model.Filter).where(
                    filter_model.Filter.id == id
                )
            )
            filter_obj = result.scalar_one_or_none()
            if not filter_obj:
                logger.warning("Filter not found for update: id=%s", id)
                return None
            for key, value in kwargs.items():
                if hasattr(filter_obj, key):
                    setattr(filter_obj, key, value)
            await db.flush()
            await db.refresh(filter_obj)
            logger.info("Filter updated: id=%s", id)
            return cast(filter_model.Filter | None, filter_obj)
        except SQLAlchemyError as e:
            logger.error("Error updating filter id=%s: %s", id, e)
            raise
    async def delete(self, id: UUID, db: AsyncSession) -> bool:
        """Delete filter.

        Args:
            id: Filter identifier (UUID).
            db: Async database session.

        Returns:
            True if deletion successful, False if filter not found.
        """
        try:
            result = await db.execute(
                select(filter_model.Filter).where(
                    filter_model.Filter.id == id
                )
            )
            filter_obj = result.scalar_one_or_none()
            if not filter_obj:
                logger.warning("Filter not found for deletion: id=%s", id)
                return False
            await db.delete(filter_obj)
            await db.flush()
            logger.info("Filter deleted: id=%s", id)
            return True
        except SQLAlchemyError as e:
            logger.error("Error deleting filter id=%s: %s", id, e)
            raise
    async def get_all(
        self, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[filter_model.Filter]:
        """Get filters, optionally bounded.

        Args:
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of filters.
        """
        try:
            query = select(filter_model.Filter)
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            filters = list(result.scalars().all())
            logger.info("Filters list retrieved, count: %s", len(filters))
            return filters
        except SQLAlchemyError as e:
            logger.error("Error getting filters list: %s", e)
            raise
