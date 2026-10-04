"""Abstract interfaces for repositories.

Defines contracts for all repositories in the system.
Used for dependency injection and breaking cyclic imports.
"""

import abc
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.models.enums import DashboardPermission, ProcessingStatus
from mkobi.models.processing_logs import ProcessingLogFilter, ProcessingLogRead


class IRepository(abc.ABC):
    """Base repository interface."""

    @abc.abstractmethod
    async def get(self, id: UUID, db: AsyncSession) -> Any | None:
        """Get object by ID."""
        pass

    @abc.abstractmethod
    async def get_all(self, db: AsyncSession) -> list[Any]:
        """Get all objects."""
        pass

    @abc.abstractmethod
    async def create(self, db: AsyncSession, **kwargs) -> Any | None:
        """Create new object."""
        pass

    @abc.abstractmethod
    async def update(self, id: UUID, db: AsyncSession, **kwargs) -> Any | None:
        """Update object."""
        pass

    @abc.abstractmethod
    async def delete(self, id: UUID, db: AsyncSession) -> bool:
        """Delete object."""
        pass


class IUserRepository(IRepository):
    """User repository interface."""

    @abc.abstractmethod
    async def get_by_email(self, email: str, db: AsyncSession) -> Any | None:
        """Get user by email."""
        pass

    @abc.abstractmethod
    async def get_by_email_with_hash(self, email: str, db: AsyncSession) -> Any | None:
        """Get user by email with password hash."""
        pass

    @abc.abstractmethod
    async def get_with_hash(self, id: UUID, db: AsyncSession) -> Any | None:
        """Get user by ID with password hash."""
        pass


class IDashboardRepository(IRepository):
    """Dashboard repository interface."""

    @abc.abstractmethod
    async def get_by_user(
        self, user_id: UUID, db: AsyncSession, is_admin: bool = False
    ) -> list[tuple[Any, str | None]]:
        """Get dashboards by user (dashboards available to user) with permission."""
        pass

    @abc.abstractmethod
    async def get_by_name(self, name: str, db: AsyncSession) -> Any | None:
        """Get dashboard by name."""
        pass


class IAccessRepository(abc.ABC):
    """Access repository interface."""

    @abc.abstractmethod
    async def grant_access(
        self,
        db: AsyncSession,
        user_id: UUID,
        dashboard_id: UUID,
        permission: DashboardPermission = DashboardPermission.VIEW,
    ) -> Any | None:
        """Grant user access to dashboard.

        Returns the ``DashboardAccess`` row reflecting the requested grant. A
        grant for a ``(user_id, dashboard_id)`` pair that already has one
        applies the requested permission and returns the stored row as written:
        the conflict is absorbed by ``ON CONFLICT DO UPDATE`` on the pair's
        primary key, so two concurrent grants of the same pair cannot fail.
        ``None`` means no row could be read back, which the caller is not
        expected to distinguish. Note that ``pyproject.toml`` sets
        ``ignore_errors = true`` for ``mkobi.interfaces.*``, so the type checker
        does not verify this declaration; the repository-level tests are the
        substitute evidence.
        """
        pass

    @abc.abstractmethod
    async def revoke_access(
        self, user_id: UUID, dashboard_id: UUID, db: AsyncSession
    ) -> bool:
        """Revoke user access to dashboard."""
        pass

    @abc.abstractmethod
    async def check_access(
        self, user_id: UUID, dashboard_id: UUID, db: AsyncSession
    ) -> DashboardPermission | None:
        """Check user access level to dashboard."""
        pass

    @abc.abstractmethod
    async def get_user_dashboards(self, user_id: UUID, db: AsyncSession) -> list[Any]:
        """Get all dashboards available to user."""
        pass

    @abc.abstractmethod
    async def get_all(self, db: AsyncSession) -> list[Any]:
        """Get all access records."""
        pass

    @abc.abstractmethod
    async def get_by_dashboard(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> list[Any]:
        """Get all access records for a dashboard."""
        pass


class IRegistrationRequestRepository(abc.ABC):
    """Registration request repository interface."""

    @abc.abstractmethod
    async def create(
        self, email: str, ip: str | None, db: AsyncSession
    ) -> Any | None:
        """Create new registration request."""
        pass

    @abc.abstractmethod
    async def get_by_id(self, request_id: UUID, db: AsyncSession) -> Any | None:
        """Get registration request by ID."""
        pass

    @abc.abstractmethod
    async def get_by_email(self, email: str, db: AsyncSession) -> Any | None:
        """Get registration request by email."""
        pass

    @abc.abstractmethod
    async def get_all(self, db: AsyncSession) -> list[Any]:
        """Get all registration requests."""
        pass

    @abc.abstractmethod
    async def update_status(
        self, request_id: UUID, status: str, db: AsyncSession, reviewed_by: UUID | None = None
    ) -> Any | None:
        """Update registration request status."""
        pass

    @abc.abstractmethod
    async def delete(self, request_id: UUID, db: AsyncSession) -> bool:
        """Delete registration request."""
        pass


class IAggregatedDataRepository(abc.ABC):
    """Aggregated data repository interface."""

    @abc.abstractmethod
    async def bulk_insert(
        self,
        db: AsyncSession,
        dashboard_id: UUID,
        records: list[dict[str, Any]],
        clear_old: bool = True,
    ) -> int:
        """Perform batch insert of aggregated data."""
        pass

    @abc.abstractmethod
    async def get_by_dashboard_id(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> list[Any]:
        """Get aggregated data for dashboard."""
        pass

    @abc.abstractmethod
    async def get_by_graph_id(
        self,
        graph_id: UUID,
        db: AsyncSession,
        dashboard_id: UUID | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Get aggregated data for graph."""
        pass

    @abc.abstractmethod
    async def delete_by_graph_id(
        self,
        graph_id: UUID,
        db: AsyncSession,
    ) -> int:
        """Delete aggregated data for graph."""
        pass

    @abc.abstractmethod
    async def delete_by_dashboard_id(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> int:
        """Delete all aggregated data for dashboard."""
        pass

    @abc.abstractmethod
    async def get_dims_values(
        self,
        graph_id: UUID,
        dim_name: str,
        db: AsyncSession,
    ) -> list[str]:
        """Get unique dimension values for graph."""
        pass


class ILayoutRepository(IRepository):
    """Layout repository interface."""

    @abc.abstractmethod
    async def get_by_name(self, name: str, db: AsyncSession) -> Any | None:
        """Get layout by name."""
        pass

    @abc.abstractmethod
    async def get_dashboard_id_for_layout(
        self, layout_id: UUID, db: AsyncSession
    ) -> UUID | None:
        """Get first dashboard ID associated with layout.

        Args:
            layout_id: Layout identifier.
            db: Async database session.

        Returns:
            Dashboard ID if layout has associated dashboard, None otherwise.
        """
        pass

    @abc.abstractmethod
    async def get_layouts_by_dashboard_ids(
        self, dashboard_ids: list[UUID], db: AsyncSession
    ) -> list[Any]:
        """Get layouts by dashboard IDs.

        Args:
            dashboard_ids: List of dashboard IDs.
            db: Async database session.

        Returns:
            List of layout models.
        """
        pass


class IFilterRepository(IRepository):
    """Filter repository interface."""

    @abc.abstractmethod
    async def get_by_name(self, name: str, db: AsyncSession) -> Any | None:
        """Get filter by name."""
        pass


class IGraphRepository(IRepository):
    """Graph repository interface."""

    @abc.abstractmethod
    async def get_by_dashboard_id(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> list[Any]:
        """Get graphs by dashboard ID."""
        pass

    @abc.abstractmethod
    async def get_by_dashboard_ids(
        self, dashboard_ids: list[UUID], db: AsyncSession
    ) -> list[Any]:
        """Get graphs by multiple dashboard IDs."""
        pass

    @abc.abstractmethod
    async def get_by_name_and_dashboard(
        self, name: str, dashboard_id: UUID, db: AsyncSession
    ) -> Any | None:
        """Get graph by name and dashboard ID."""
        pass


class IDashboardFilterValuesRepository(abc.ABC):
    """Dashboard filter values repository interface."""

    @abc.abstractmethod
    async def get_filter_values(
        self, dashboard_id: UUID, filter_name: str, db: AsyncSession
    ) -> list[str]:
        """Get filter values by dashboard ID and filter name."""
        pass

    @abc.abstractmethod
    async def save_filter_values(
        self, dashboard_id: UUID, filter_name: str, values: list[str], db: AsyncSession
    ) -> int:
        """Save filter values (clear-then-insert for idempotency)."""
        pass

    @abc.abstractmethod
    async def clear_dashboard_values(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> int:
        """Clear all filter values for a dashboard."""
        pass


class IProcessingConfigRepository(IRepository):
    """Processing config repository interface."""

    # Inherits get(id, db), get_all(db), create(db, **kwargs), update(id, db, **kwargs), delete(id, db)
    # Processing configs are retrieved via get(id) where id is dashboard_id


class IProcessingLogRepository(abc.ABC):
    """Processing log repository interface."""

    @abc.abstractmethod
    async def create_log(
        self,
        dashboard_id: UUID | None,
        status: ProcessingStatus,
        message: str | None,
        db: AsyncSession,
    ) -> Any:
        """Create new processing log."""
        pass

    @abc.abstractmethod
    async def update_status(
        self,
        log_id: UUID,
        status: ProcessingStatus,
        message: str | None,
        db: AsyncSession,
        finished_at: datetime | None = None,
        error_code: str | None = None,
    ) -> None:
        """Update processing log status."""
        pass

    @abc.abstractmethod
    async def get_by_dashboard(
        self,
        dashboard_id: UUID | None,
        db: AsyncSession,
    ) -> list[ProcessingLogRead]:
        """Get all processing logs for dashboard."""
        pass

    @abc.abstractmethod
    async def get_filtered(
        self,
        filters: ProcessingLogFilter,
        db: AsyncSession,
    ) -> list[ProcessingLogRead]:
        """Get processing logs with filtering."""
        pass

    @abc.abstractmethod
    async def get_latest_by_dashboard(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> ProcessingLogRead | None:
        """Get latest processing log for dashboard."""
        pass

    @abc.abstractmethod
    async def get_by_id(
        self,
        log_id: UUID,
        db: AsyncSession,
    ) -> ProcessingLogRead | None:
        """Get log by ID."""
        pass

    @abc.abstractmethod
    async def delete(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Delete processing logs by dashboard ID."""
        pass

    @abc.abstractmethod
    async def delete_old_logs(
        self,
        cutoff: datetime,
        db: AsyncSession,
    ) -> int:
        """Delete processing logs in terminal states older than cutoff.

        Args:
            cutoff: Datetime cutoff - logs with finished_at before this are deleted.
            db: Async database session.

        Returns:
            int: Number of deleted log entries.
        """
        pass
