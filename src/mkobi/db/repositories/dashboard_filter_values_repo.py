"""Repository for dashboard filter values operations.

Provides CRUD methods for DashboardFilterValue model.
All methods use contextual session management and handle errors.
"""

import logging
from typing import cast
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models.dashboard_filter_values import DashboardFilterValue
from mkobi.interfaces.repository_interfaces import IDashboardFilterValuesRepository

logger = logging.getLogger(__name__)


class DashboardFilterValuesRepository(IDashboardFilterValuesRepository):
    """Repository for dashboard filter values operations.

    Provides methods for retrieving, saving and clearing filter values
    in the database. All operations are performed within a separate session
    with automatic transaction management.
    Implements IDashboardFilterValuesRepository interface.
    """

    async def get_filter_values(
        self, dashboard_id: UUID, filter_name: str, db: AsyncSession
    ) -> list[str]:
        """Get filter values by dashboard ID and filter name.

        Args:
            dashboard_id: Dashboard identifier (UUID).
            filter_name: Name of the filter.
            db: Async database session.

        Returns:
            List of filter_value strings, ordered by filter_value.
        """
        try:
            result = await db.execute(
                select(DashboardFilterValue.filter_value)
                .where(
                    DashboardFilterValue.dashboard_id == dashboard_id,
                    DashboardFilterValue.filter_name == filter_name,
                )
                .order_by(DashboardFilterValue.filter_value)
            )
            values = cast(list[str], result.scalars().all())
            logger.info(
                "Filter values retrieved: dashboard_id=%s, filter_name=%s, count=%s",
                dashboard_id,
                filter_name,
                len(values),
            )
            return values
        except SQLAlchemyError as e:
            logger.error(
                "Error getting filter values: dashboard_id=%s, filter_name=%s: %s",
                dashboard_id,
                filter_name,
                e,
            )
            raise

    async def save_filter_values(
        self, dashboard_id: UUID, filter_name: str, values: list[str], db: AsyncSession
    ) -> int:
        """Save filter values (clear-then-insert for idempotency).

        Residual annotation gap (PB-3 / DP-005), answered "no": this method does
        not coerce ``values`` itself, and the ``list[str]`` annotation is not a
        runtime guard. The single owner of the coercion is
        ``workers/data_worker.py::_store_aggregates``, which does
        ``str_values = [str(value) for value in fvalues]`` before each call.
        That boundary is the only place a native Polars scalar (``int`` /
        ``float`` / ``bool``) can be turned into text before ``asyncpg`` binding,
        which refuses a non-``str`` at parameter binding *before* SQLAlchemy or
        PostgreSQL coercion.

        Coercing here as well would create a second owner for one contract and
        hide the gap rather than record it. What would break this: a future
        caller that reaches this method without going through
        ``_store_aggregates`` and passes native scalars. ``mypy`` cannot detect
        that case for the worker's own calls, because ``asyncio.to_thread``
        erases the argument types, so the ``list[str]`` signature is the only
        guard and a bypassing caller would lose the coercion with nothing to
        catch it. Any such caller must coerce before calling this method.

        Args:
            dashboard_id: Dashboard identifier (UUID).
            filter_name: Name of the filter.
            values: List of filter values to save.
            db: Async database session.

        Returns:
            Count of inserted values.
        """
        try:
            # Clear existing values for this (dashboard_id, filter_name) combination
            await self._clear_filter_values(
                dashboard_id, filter_name, db
            )

            # Bulk insert new values using SQLAlchemy Core
            if values:
                insert_data = [
                    {
                        "dashboard_id": dashboard_id,
                        "filter_name": filter_name,
                        "filter_value": value,
                    }
                    for value in values
                ]
                await db.execute(
                    insert(DashboardFilterValue),
                    insert_data,
                )

            logger.info(
                "Filter values saved: dashboard_id=%s, filter_name=%s, count=%s",
                dashboard_id,
                filter_name,
                len(values),
            )
            return len(values)
        except SQLAlchemyError as e:
            logger.error(
                "Error saving filter values: dashboard_id=%s, filter_name=%s: %s",
                dashboard_id,
                filter_name,
                e,
            )
            raise

    async def _clear_filter_values(
        self, dashboard_id: UUID, filter_name: str, db: AsyncSession
    ) -> int:
        """Clear filter values for specific filter.

        Args:
            dashboard_id: Dashboard identifier (UUID).
            filter_name: Name of the filter.
            db: Async database session.

        Returns:
            Count of deleted rows.
        """
        result = await db.execute(
            delete(DashboardFilterValue).where(
                DashboardFilterValue.dashboard_id == dashboard_id,
                DashboardFilterValue.filter_name == filter_name,
            )
        )
        return result.rowcount or 0

    async def clear_dashboard_values(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> int:
        """Clear all filter values for a dashboard.

        Args:
            dashboard_id: Dashboard identifier (UUID).
            db: Async database session.

        Returns:
            Count of deleted rows.
        """
        try:
            result = await db.execute(
                delete(DashboardFilterValue).where(
                    DashboardFilterValue.dashboard_id == dashboard_id
                )
            )
            deleted_count = result.rowcount or 0
            logger.info(
                "Dashboard filter values cleared: dashboard_id=%s, count=%s",
                dashboard_id,
                deleted_count,
            )
            return deleted_count
        except SQLAlchemyError as e:
            logger.error(
                "Error clearing dashboard filter values: dashboard_id=%s: %s",
                dashboard_id,
                e,
            )
            raise