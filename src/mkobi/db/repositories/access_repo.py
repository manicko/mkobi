"""Repository for access control operations.

Provides methods for managing user access to dashboards.
All methods use contextual session management and handle errors.
"""

import logging
from uuid import UUID
from typing import cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Insert as PGInsert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models import access as access_model
from mkobi.db.models import dashboard as dashboard_model
from mkobi.interfaces.repository_interfaces import IAccessRepository

logger = logging.getLogger(__name__)


def _conflict_tolerant_access_insert(
    user_id: UUID, dashboard_id: UUID, permission: str
) -> PGInsert:
    """Build the conflict-tolerant INSERT for one dashboard_access row.

    The composite primary key on (user_id, dashboard_id) is what enforces
    "one grant per pair"; naming those two columns in index_elements means the
    conflict action applies to *that* constraint only, so any other integrity
    violation still raises instead of being silently absorbed.
    """
    return (
        pg_insert(access_model.DashboardAccess)
        .values(
            user_id=user_id,
            dashboard_id=dashboard_id,
            permission=permission,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "dashboard_id"])
        .returning(
            access_model.DashboardAccess.user_id,
            access_model.DashboardAccess.dashboard_id,
            access_model.DashboardAccess.permission,
        )
    )


class AccessRepository(IAccessRepository):
    """Repository for access control operations.

    Provides methods for managing user access to dashboards.
    All operations are performed within a separate database session
    with automatic transaction management.
    Implements IAccessRepository interface.
    """

    async def grant_access(
        self,
        db: AsyncSession,
        user_id: UUID,
        dashboard_id: UUID,
        permission: str = "view",
    ) -> access_model.DashboardAccess | None:
        """Grant user access to dashboard.

        Args:
            user_id: User identifier (UUID).
            dashboard_id: Dashboard identifier (UUID).
            permission: Access level (view/edit/admin).
            db: Async database session.

        Returns:
            DashboardAccess representing the desired state: the row this call
            inserted, or the existing row when the pair already had one. A
            re-grant is a no-op that writes nothing and returns the existing
            row unchanged. ``None`` only when no row could be read back.
        """
        try:
            # Fast path only, never the correctness mechanism: a concurrent
            # winner's uncommitted row is invisible to this SELECT, which is
            # exactly the window that used to yield a unique-violation 500.
            result = await db.execute(
                select(access_model.DashboardAccess).where(
                    access_model.DashboardAccess.user_id == user_id,
                    access_model.DashboardAccess.dashboard_id == dashboard_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                logger.warning(
                    "Access already exists: user_id=%s, dashboard_id=%s",
                    user_id,
                    dashboard_id,
                )
                return cast(access_model.DashboardAccess | None, existing)

            insert_result = await db.execute(
                _conflict_tolerant_access_insert(user_id, dashboard_id, permission)
            )
            inserted = insert_result.first()
            if inserted is not None:
                logger.info(
                    "Access granted: user_id=%s, dashboard_id=%s, permission=%s",
                    user_id,
                    dashboard_id,
                    permission,
                )
            else:
                # The conflict was absorbed, so our INSERT produced no row.
                # PostgreSQL runs the conflict action only once the conflicting
                # transaction has ended: had the winner rolled back, our INSERT
                # would have proceeded and RETURNING would have yielded a row.
                # Reaching this branch therefore means the winner committed, and
                # under READ COMMITTED the next statement takes a fresh snapshot
                # and sees it.
                logger.warning(
                    "Access already exists: user_id=%s, dashboard_id=%s",
                    user_id,
                    dashboard_id,
                )

            # Re-read on both branches so the method has one return type: a
            # DashboardAccess, whether this call inserted it or absorbed it.
            reread = await db.execute(
                select(access_model.DashboardAccess).where(
                    access_model.DashboardAccess.user_id == user_id,
                    access_model.DashboardAccess.dashboard_id == dashboard_id,
                )
            )
            persisted = reread.scalar_one_or_none()
            if persisted is None:
                logger.error(
                    "Access grant could not be read back: user_id=%s, dashboard_id=%s",
                    user_id,
                    dashboard_id,
                )
                return None
            return cast(access_model.DashboardAccess | None, persisted)
        except SQLAlchemyError as e:
            logger.error(
                "Error granting access user_id=%s, dashboard_id=%s: %s",
                user_id,
                dashboard_id,
                e,
            )
            raise

    async def revoke_access(self, user_id: UUID, dashboard_id: UUID, db: AsyncSession) -> bool:
        """Revoke user access to dashboard.

        Args:
            user_id: User identifier (UUID).
            dashboard_id: Dashboard identifier (UUID).
            db: Async database session.

        Returns:
            True if access revoked, False if not found.
        """
        try:
            result = await db.execute(
                select(access_model.DashboardAccess).where(
                    access_model.DashboardAccess.user_id == user_id,
                    access_model.DashboardAccess.dashboard_id == dashboard_id,
                )
            )
            access_obj = result.scalar_one_or_none()
            if not access_obj:
                logger.warning(
                    "Access not found for revocation: user_id=%s, dashboard_id=%s",
                    user_id,
                    dashboard_id,
                )
                return False
            await db.delete(access_obj)
            await db.flush()
            logger.info(
                "Access revoked: user_id=%s, dashboard_id=%s",
                user_id,
                dashboard_id,
            )
            return True
        except SQLAlchemyError as e:
            logger.error(
                "Error revoking access user_id=%s, dashboard_id=%s: %s",
                user_id,
                dashboard_id,
                e,
            )
            raise

    async def check_access(
        self, user_id: UUID, dashboard_id: UUID, db: AsyncSession
    ) -> str | None:
        """Check user access level to dashboard.

        Args:
            user_id: User identifier (UUID).
            dashboard_id: Dashboard identifier (UUID).
            db: Async database session.

        Returns:
            Access level (view/edit/admin) or None if no access.
        """
        try:
            result = await db.execute(
                select(access_model.DashboardAccess).where(
                    access_model.DashboardAccess.user_id == user_id,
                    access_model.DashboardAccess.dashboard_id == dashboard_id,
                )
            )
            access_obj = result.scalar_one_or_none()
            if access_obj:
                permission: str = access_obj.permission
                logger.info(
                    "Access checked: user_id=%s, dashboard_id=%s, permission=%s",
                    user_id,
                    dashboard_id,
                    permission,
                )
                return permission
            logger.warning(
                "No access: user_id=%s, dashboard_id=%s",
                user_id,
                dashboard_id,
            )
            return None
        except SQLAlchemyError as e:
            logger.error(
                "Error checking access user_id=%s, dashboard_id=%s: %s",
                user_id,
                dashboard_id,
                e,
            )
            raise

    async def get_user_dashboards(
        self, user_id: UUID, db: AsyncSession
    ) -> list[dashboard_model.Dashboard]:
        """Get all dashboards available to user.

        Args:
            user_id: User identifier (UUID).
            db: Async database session.

        Returns:
            List of dashboards available to user.
        """
        try:
            result = await db.execute(
                select(dashboard_model.Dashboard)
                .join(access_model.DashboardAccess)
                .where(access_model.DashboardAccess.user_id == user_id)
            )
            dashboards = list(result.scalars().all())
            logger.info(
                "Dashboards retrieved for user id=%s, count: %s",
                user_id,
                len(dashboards),
            )
            return dashboards
        except SQLAlchemyError as e:
            logger.error(
                "Error getting dashboards for user id=%s: %s",
                user_id,
                e,
            )
            raise

    async def get_all(self, db: AsyncSession) -> list[access_model.DashboardAccess]:
        """Get all access records.

        Args:
            db: Async database session.

        Returns:
            List of all access records.
        """
        try:
            result = await db.execute(select(access_model.DashboardAccess))
            access_list = list(result.scalars().all())
            logger.info("Access list retrieved, count: %s", len(access_list))
            return access_list
        except SQLAlchemyError as e:
            logger.error("Error getting access list: %s", e)
            raise

    async def get_by_dashboard(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> list[access_model.DashboardAccess]:
        """Get all access records for a dashboard.

        Args:
            dashboard_id: Dashboard identifier (UUID).
            db: Async database session.

        Returns:
            List of access records for the dashboard.
        """
        try:
            result = await db.execute(
                select(access_model.DashboardAccess).where(
                    access_model.DashboardAccess.dashboard_id == dashboard_id
                )
            )
            access_list = list(result.scalars().all())
            logger.info(
                "Access list retrieved for dashboard id=%s, count: %s",
                dashboard_id,
                len(access_list),
            )
            return access_list
        except SQLAlchemyError as e:
            logger.error(
                "Error getting access list for dashboard id=%s: %s",
                dashboard_id,
                e,
            )
            raise
