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
from mkobi.models.enums import DashboardPermission

logger = logging.getLogger(__name__)


def _conflict_tolerant_access_insert(
    user_id: UUID, dashboard_id: UUID, permission: DashboardPermission
) -> PGInsert:
    """Build the conflict-tolerant upsert for one dashboard_access row.

    The composite primary key on (user_id, dashboard_id), named
    ``dashboard_access_pkey``, is what enforces "one grant per pair"; naming
    those two columns in index_elements means the conflict action applies to
    *that* constraint only, so any other integrity violation still raises
    instead of being silently absorbed. The conflict action updates the stored
    permission to the requested one, so a re-grant applies the new value rather
    than being a no-op. The value is bound through the enum's ``.value`` by the
    column type's bind processor (``values_callable``), never ``.name``.
    """
    return (
        pg_insert(access_model.DashboardAccess)
        .values(
            user_id=user_id,
            dashboard_id=dashboard_id,
            permission=permission,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "dashboard_id"],
            set_={"permission": permission},
        )
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
        permission: DashboardPermission = DashboardPermission.VIEW,
    ) -> access_model.DashboardAccess | None:
        """Grant user access to dashboard.

        Args:
            user_id: User identifier (UUID).
            dashboard_id: Dashboard identifier (UUID).
            permission: Access level as a ``DashboardPermission`` member.
            db: Async database session.

        Returns:
            DashboardAccess reflecting the stored state after the write: the row
            this call inserted, or the existing row updated to the requested
            permission when the pair already had one. A re-grant therefore
            applies the requested permission rather than being a no-op.
            ``None`` only when no row could be read back.
        """
        try:
            # Probe only, never the correctness mechanism: a concurrent winner's
            # uncommitted row is invisible to this SELECT, and the upsert below
            # resolves the conflict regardless. Its result is intentionally
            # discarded; it runs first so callers that interleave a competing
            # commit observe a stable statement order.
            await db.execute(
                select(access_model.DashboardAccess).where(
                    access_model.DashboardAccess.user_id == user_id,
                    access_model.DashboardAccess.dashboard_id == dashboard_id,
                )
            )

            insert_result = await db.execute(
                _conflict_tolerant_access_insert(user_id, dashboard_id, permission)
            )
            if insert_result.first() is not None:
                logger.info(
                    "Access granted: user_id=%s, dashboard_id=%s, permission=%s",
                    user_id,
                    dashboard_id,
                    permission,
                )

            # Re-read so the method has one return type: a DashboardAccess
            # whether this call inserted it or updated it via the conflict
            # action. ``populate_existing=True`` is REQUIRED, not cosmetic: the
            # leading SELECT loaded the row into the session's identity map and
            # ``expire_on_commit=False`` keeps it there, while the Core upsert
            # changed the row in the database and not through the ORM -- without
            # the refresh this select would hand back the stale instance.
            reread = await db.execute(
                select(access_model.DashboardAccess)
                .where(
                    access_model.DashboardAccess.user_id == user_id,
                    access_model.DashboardAccess.dashboard_id == dashboard_id,
                )
                .execution_options(populate_existing=True)
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
    ) -> DashboardPermission | None:
        """Check user access level to dashboard.

        Args:
            user_id: User identifier (UUID).
            dashboard_id: Dashboard identifier (UUID).
            db: Async database session.

        Returns:
            The stored ``DashboardPermission`` member, or None if no access.
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
                permission: DashboardPermission = access_obj.permission
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
        self, user_id: UUID, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[dashboard_model.Dashboard]:
        """Get dashboards available to user, optionally bounded.

        Args:
            user_id: User identifier (UUID).
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of dashboards available to user.
        """
        try:
            query = (
                select(dashboard_model.Dashboard)
                .join(access_model.DashboardAccess)
                .where(access_model.DashboardAccess.user_id == user_id)
            )
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
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
        self, dashboard_id: UUID, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[access_model.DashboardAccess]:
        """Get access records for a dashboard, optionally bounded.

        Args:
            dashboard_id: Dashboard identifier (UUID).
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of access records for the dashboard.
        """
        try:
            query = select(access_model.DashboardAccess).where(
                access_model.DashboardAccess.dashboard_id == dashboard_id
            )
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
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
