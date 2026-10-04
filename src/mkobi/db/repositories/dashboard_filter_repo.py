"""Repository for managing dashboard-filter relationships.

This module provides methods to bind/unbind filters to dashboards
using the dashboard_filters many-to-many table.
"""

import logging
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import SQLAlchemyError

from mkobi.db.models.filters import dashboard_filters
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DashboardFilterRepository:
    """Repository for dashboard-filter binding operations.

    Provides methods to manage the many-to-many relationship
    between dashboards and filters.
    """
    async def bind_filter(
        self, dashboard_id: UUID, filter_id: UUID, db: AsyncSession
    ) -> bool:
        """Bind a filter to a dashboard.

        Args:
            dashboard_id: Dashboard ID (UUID).
            filter_id: Filter ID (UUID).
            db: Async database session.

        Returns:
            True if binding was successful, False if already exists.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            # Check if binding already exists
            result = await db.execute(
                select(dashboard_filters).where(
                    dashboard_filters.c.dashboard_id == dashboard_id,
                    dashboard_filters.c.filter_id == filter_id,
                )
            )
            existing = result.first()
            if existing:
                logger.warning(
                    "Filter already bound: dashboard_id=%s, filter_id=%s",
                    dashboard_id,
                    filter_id,
                )
                return False

            # Insert new binding
            await db.execute(
                insert(dashboard_filters).values(
                    dashboard_id=dashboard_id,
                    filter_id=filter_id,
                )
            )
            await db.flush()
            logger.info(
                "Filter bound to dashboard: dashboard_id=%s, filter_id=%s",
                dashboard_id,
                filter_id,
            )
            return True
        except SQLAlchemyError as e:
            logger.error(
                "Error binding filter to dashboard: dashboard_id=%s, filter_id=%s, error=%s",
                dashboard_id,
                filter_id,
                e,
            )
            raise
    async def unbind_filter(
        self, dashboard_id: UUID, filter_id: UUID, db: AsyncSession
    ) -> bool:
        """Unbind a filter from a dashboard.

        Args:
            dashboard_id: Dashboard ID (UUID).
            filter_id: Filter ID (UUID).
            db: Async database session.

        Returns:
            True if unbinding was successful, False if binding not found.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await db.execute(
                delete(dashboard_filters).where(
                    dashboard_filters.c.dashboard_id == dashboard_id,
                    dashboard_filters.c.filter_id == filter_id,
                )
            )
            if result.rowcount == 0:
                logger.warning(
                    "Filter binding not found: dashboard_id=%s, filter_id=%s",
                    dashboard_id,
                    filter_id,
                )
                return False

            await db.flush()
            logger.info(
                "Filter unbound from dashboard: dashboard_id=%s, filter_id=%s",
                dashboard_id,
                filter_id,
            )
            return True
        except SQLAlchemyError as e:
            logger.error(
                "Error unbinding filter from dashboard: dashboard_id=%s, filter_id=%s, error=%s",
                dashboard_id,
                filter_id,
                e,
            )
            raise
    async def get_dashboard_filters(
        self, dashboard_id: UUID, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[UUID]:
        """Get filter IDs bound to a dashboard, optionally bounded.

        Args:
            dashboard_id: Dashboard ID (UUID).
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of filter IDs.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            query = select(dashboard_filters.c.filter_id).where(
                dashboard_filters.c.dashboard_id == dashboard_id
            )
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            filter_ids = [row[0] for row in result.all()]
            logger.info(
                "Got filters for dashboard: dashboard_id=%s, count=%s",
                dashboard_id,
                len(filter_ids),
            )
            return filter_ids
        except SQLAlchemyError as e:
            logger.error(
                "Error getting filters for dashboard: dashboard_id=%s, error=%s",
                dashboard_id,
                e,
            )
            raise
    async def get_filter_dashboards(
        self, filter_id: UUID, db: AsyncSession
    ) -> list[UUID]:
        """Get all dashboard IDs that have a specific filter bound.

        Args:
            filter_id: Filter ID (UUID).
            db: Async database session.

        Returns:
            List of dashboard IDs.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await db.execute(
                select(dashboard_filters.c.dashboard_id).where(
                    dashboard_filters.c.filter_id == filter_id
                )
            )
            dashboard_ids = [row[0] for row in result.all()]
            logger.info(
                "Got dashboards for filter: filter_id=%s, count=%s",
                filter_id,
                len(dashboard_ids),
            )
            return dashboard_ids
        except SQLAlchemyError as e:
            logger.error(
                "Error getting dashboards for filter: filter_id=%s, error=%s",
                filter_id,
                e,
            )
            raise
