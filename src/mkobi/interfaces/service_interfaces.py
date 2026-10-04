"""Abstract interfaces for services.

Defines contracts for all services in the system.
"""

import abc
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.models.dashboard import DashboardRead, DashboardSummary
from mkobi.models.data import ProcessingResultData, ProcessingResult, ProcessingStatusResponse, UploadResponse
from mkobi.models.enums import UploadMode, UserRole, DashboardPermission
from mkobi.models.filters import FilterRead, FilterUpdate
from mkobi.models.graph import GraphRead
from mkobi.models.layout import LayoutRead, LayoutUpdate
from mkobi.models.processing_configs import ProcessingConfigRead
from mkobi.models.processing_logs import ProcessingLogRead
from mkobi.models.types import (
    FilterConfigDict,
    ProcessingSettingsModel,
)
from mkobi.models.user import UserRead


class IAuthService(abc.ABC):
    """Authentication service interface."""

    @abc.abstractmethod
    async def register_user(
        self, email: str, password: str, db: AsyncSession, role: str = "viewer"
    ) -> UserRead:
        """Register new user."""
        pass

    @abc.abstractmethod
    async def authenticate_user(
        self, email: str, password: str, db: AsyncSession
    ) -> UserRead | None:
        """Authenticate user and return data."""
        pass

    @abc.abstractmethod
    async def login_user(
        self, email: str, password: str, db: AsyncSession
    ) -> dict[str, Any] | None:
        """Perform login and return JWT token."""
        pass

    @abc.abstractmethod
    async def refresh_token(
        self, user_id: UUID, email: str, role: str
    ) -> dict[str, Any]:
        """Refresh JWT token."""
        pass

    @abc.abstractmethod
    async def reset_password_admin(
        self,
        user_id: UUID,
        admin_user_id: UUID,
        db: AsyncSession,
    ) -> dict[str, Any] | None:
        """Admin-triggered password reset. Generates temp password and returns retrieval token."""
        pass

    @abc.abstractmethod
    def create_access_token(self, user_id: UUID, role: str) -> str:
        """Create access token for user."""
        pass

    @abc.abstractmethod
    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify JWT token and return data."""
        pass

    @abc.abstractmethod
    def validate_refresh_token(self, token: str) -> dict[str, Any] | None:
        """Validate refresh token and return user data if valid."""
        pass

    @abc.abstractmethod
    async def register_request(
        self, email: str, ip: str | None, db: AsyncSession
    ) -> dict[str, Any]:
        """Create registration request."""
        pass

    @abc.abstractmethod
    async def get_user_by_id(
        self, user_id: UUID, db: AsyncSession
    ) -> UserRead | None:
        """Get user by ID."""
        pass

    @abc.abstractmethod
    async def get_user_by_email(
        self, email: str, db: AsyncSession
    ) -> UserRead | None:
        """Get user by email."""
        pass

    @abc.abstractmethod
    async def approve_registration_request(
        self,
        request_id: UUID,
        admin_user_id: UUID,
        db: AsyncSession,
    ) -> dict[str, Any] | None:
        """Approve a pending registration request.

        Creates the user, sets the force-password-change flag, marks the request
        approved, commits, and only then stores the temporary password so the
        credential never becomes durable before the user exists.

        Returns:
            dict with user_id, retrieval_token and credential_stored on success.
            ``credential_stored`` is ``False`` when the post-commit Redis write of
            the temporary password faulted or no store was wired, in which case
            the returned ``retrieval_token`` is not a working handle.
            None if the request does not exist.
        """
        pass


class IUserService(abc.ABC):
    """User service interface.

    Transaction ownership: write methods own their unit of work. On success a
    write method commits, so the write is durable when the method returns; on
    failure nothing is committed and the session is left usable. A method
    returning ``None`` because the entity does not exist commits nothing. Read
    methods never commit. Callers must not add a commit of their own, and must
    not assume the session teardown is a transaction boundary.
    """

    @abc.abstractmethod
    async def create_user(
        self, email: str, password: str, role: UserRole, db: AsyncSession
    ) -> UserRead:
        """Create new user.

        On success commits, and only then returns, so the user row is durable
        when this method returns. A duplicate email — whether caught by the
        pre-check or by the users.email unique index — raises ``ValueError`` and
        therefore maps to 422.
        """
        pass

    @abc.abstractmethod
    async def get_user_by_id(self, user_id: UUID, db: AsyncSession) -> UserRead | None:
        """Get user by ID."""
        pass

    @abc.abstractmethod
    async def get_user_by_email(self, email: str, db: AsyncSession) -> UserRead | None:
        """Get user by email."""
        pass

    @abc.abstractmethod
    async def update_user_role(
        self, user_id: UUID, role: UserRole, db: AsyncSession
    ) -> UserRead | None:
        """Update user role.

        On success commits, and only then returns, so the new role is durable
        when this method returns. Returns ``None`` without committing when the
        user does not exist.
        """
        pass

    @abc.abstractmethod
    async def delete_user(self, user_id: UUID, db: AsyncSession) -> bool:
        """Delete user.

        On success commits, and only then returns, so the deletion is durable
        when this method returns. Returns ``False`` without committing when the
        user does not exist.
        """
        pass

    @abc.abstractmethod
    async def update_user_active_status(
        self, user_id: UUID, is_active: bool, db: AsyncSession
    ) -> UserRead | None:
        """Update user active status (deactivate/reactivate user).

        On success commits, and only then returns, so the new active status is
        durable when this method returns. Returns ``None`` without committing
        when the user does not exist.
        """
        pass

    @abc.abstractmethod
    async def get_all_users(
        self, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[UserRead]:
        """Get users, optionally bounded."""
        pass


class IDashboardService(abc.ABC):
    """Dashboard service interface."""

    @abc.abstractmethod
    async def create_dashboard(
        self,
        name: str,
        config: dict[str, Any],
        owner_id: UUID,
        db: AsyncSession,
        description: str | None = None,
        layout_id: UUID | None = None,
    ) -> DashboardRead:
        """Create new dashboard."""
        pass

    @abc.abstractmethod
    async def get_dashboard(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        db: AsyncSession,
        user_role: str | None = None,
    ) -> DashboardRead | None:
        """Get dashboard by ID with access check."""
        pass

    @abc.abstractmethod
    async def get_dashboard_by_name(
        self,
        name: str,
        db: AsyncSession,
    ) -> DashboardRead | None:
        """Get dashboard by name."""
        pass

    @abc.abstractmethod
    async def get_user_dashboards(
        self,
        user_id: UUID,
        db: AsyncSession,
        user_role: str | None = None,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[DashboardSummary]:
        """Get user dashboards with permission, optionally bounded."""
        pass

    @abc.abstractmethod
    async def update_dashboard(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
        update_data: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        permission: DashboardPermission | None = None,
    ) -> DashboardRead | None:
        """Update dashboard."""
        pass

    @abc.abstractmethod
    async def delete_dashboard(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Delete dashboard."""
        pass

    @abc.abstractmethod
    async def get_all_dashboards(
        self,
        db: AsyncSession,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[DashboardRead]:
        """Get dashboards, optionally bounded."""
        pass

    @abc.abstractmethod
    async def grant_access(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        permission: DashboardPermission,
        db: AsyncSession,
    ) -> bool:
        """Grant access to dashboard."""
        pass

    @abc.abstractmethod
    async def revoke_access(
        self,
        dashboard_id: UUID,
        user_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Revoke access to dashboard."""
        pass

    @abc.abstractmethod
    async def get_dashboard_access_list(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        """Get access list for dashboard, optionally bounded."""
        pass


class IGraphService(abc.ABC):
    """Graph service interface."""

    @abc.abstractmethod
    async def create_graph(
        self,
        dashboard_id: UUID,
        name: str,
        type_: str,
        config: dict[str, Any],
        db: AsyncSession,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
    ) -> GraphRead:
        """Create new graph."""
        pass

    @abc.abstractmethod
    async def get_graph_by_id(
        self,
        graph_id: UUID,
        db: AsyncSession,
    ) -> GraphRead | None:
        """Get graph by ID."""
        pass

    @abc.abstractmethod
    async def get_graph_by_name_and_dashboard(
        self,
        name: str,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> GraphRead | None:
        """Get graph by name and dashboard ID."""
        pass

    @abc.abstractmethod
    async def get_graphs_by_dashboard(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[GraphRead]:
        """Get graphs by dashboard ID, optionally bounded."""
        pass

    @abc.abstractmethod
    async def update_graph(
        self,
        graph_id: UUID,
        db: AsyncSession,
        name: str | None = None,
        type_: str | None = None,
        config: dict[str, Any] | None = None,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
    ) -> GraphRead | None:
        """Update graph."""
        pass

    @abc.abstractmethod
    async def delete_graph(
        self,
        graph_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Delete graph."""
        pass


class IFilterService(abc.ABC):
    """Filter service interface."""

    @abc.abstractmethod
    async def create_filter(
        self,
        name: str,
        type_: str,
        config: FilterConfigDict,
        db: AsyncSession,
    ) -> FilterRead:
        """Create new filter."""
        pass

    @abc.abstractmethod
    async def get_filter_by_id(
        self,
        filter_id: UUID,
        db: AsyncSession,
    ) -> FilterRead | None:
        """Get filter by ID."""
        pass

    @abc.abstractmethod
    async def get_filter_by_name(
        self,
        name: str,
        db: AsyncSession,
    ) -> FilterRead | None:
        """Get filter by name."""
        pass

    @abc.abstractmethod
    async def update_filter(
        self,
        filter_id: UUID,
        updates: FilterUpdate,
        db: AsyncSession,
    ) -> FilterRead | None:
        """Update filter."""
        pass

    @abc.abstractmethod
    async def delete_filter(
        self,
        filter_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Delete filter."""
        pass

    @abc.abstractmethod
    async def get_all_filters(
        self,
        db: AsyncSession,
    ) -> list[FilterRead]:
        """Get all filters."""
        pass


class IDataService(abc.ABC):
    """Data service interface."""

    @abc.abstractmethod
    async def process_upload(
        self,
        file_path: str | Path,
        dashboard_id: UUID,
        db: AsyncSession,
        user_id: UUID | None = None,
        filename: str | None = None,
        content_type: str | None = None,
        mode: UploadMode = UploadMode.OVERWRITE,
    ) -> UploadResponse:
        """Process uploaded file and save aggregates."""
        pass

    @abc.abstractmethod
    async def get_processing_status(
        self,
        task_id: UUID,
        user_id: UUID,
        db: AsyncSession,
    ) -> ProcessingStatusResponse:
        """Get processing status."""
        pass

    @abc.abstractmethod
    async def get_processing_result(
        self,
        task_id: UUID,
        user_id: UUID,
        db: AsyncSession,
    ) -> ProcessingResult:
        """Get processing result."""
        pass

    @abc.abstractmethod
    async def get_aggregated_data(
        self,
        dashboard_id: UUID,
        graph_id: UUID,
        db: AsyncSession,
        filters: dict[str, Any] | None = None,
    ) -> list[ProcessingResultData]:
        """Get aggregated data for graph."""
        pass

    @abc.abstractmethod
    async def get_bounded_aggregated_data(
        self,
        dashboard_id: UUID,
        graph_id: UUID,
        db: AsyncSession,
        max_rows: int,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[ProcessingResultData], int]:
        """Get bounded aggregate rows plus the true total."""
        pass

    @abc.abstractmethod
    async def count_dashboard_aggregated_data(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> int:
        """Return the dashboard-wide true aggregate row count."""
        pass

    @abc.abstractmethod
    async def get_available_metrics(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> list[str]:
        """Get available metrics for dashboard."""
        pass

    @abc.abstractmethod
    async def get_available_dimensions(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> list[str]:
        """Get available dimensions for dashboard."""
        pass


class IProcessingConfigService(abc.ABC):
    """Processing config service interface."""

    @abc.abstractmethod
    async def create_processing_config(
        self,
        dashboard_id: UUID,
        settings: ProcessingSettingsModel,
        db: AsyncSession,
    ) -> ProcessingConfigRead:
        """Create processing config for dashboard."""
        pass

    @abc.abstractmethod
    async def get_processing_config_by_dashboard(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> ProcessingConfigRead | None:
        """Get processing config by dashboard ID."""
        pass

    @abc.abstractmethod
    async def update_processing_config(
        self,
        dashboard_id: UUID,
        settings: ProcessingSettingsModel,
        db: AsyncSession,
    ) -> ProcessingConfigRead | None:
        """Update processing config."""
        pass

    @abc.abstractmethod
    async def delete_processing_config(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Delete processing config."""
        pass


class IProcessingLogService(abc.ABC):
    """Processing log service interface."""

    @abc.abstractmethod
    async def create_processing_log(
        self,
        dashboard_id: UUID,
        status: str,
        db: AsyncSession,
        message: str | None = None,
    ) -> ProcessingLogRead:
        """Create processing log entry."""
        pass

    @abc.abstractmethod
    async def get_processing_logs_by_dashboard(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> list[ProcessingLogRead]:
        """Get processing logs by dashboard ID."""
        pass

    @abc.abstractmethod
    async def get_processing_logs_by_status(
        self,
        status: str,
        db: AsyncSession,
    ) -> list[ProcessingLogRead]:
        """Get processing logs by status."""
        pass

    @abc.abstractmethod
    async def update_processing_log(
        self,
        log_id: UUID,
        status: str | None,
        message: str | None,
        finished_at: str | None,
        db: AsyncSession,
    ) -> ProcessingLogRead | None:
        """Update processing log entry."""
        pass

    @abc.abstractmethod
    async def delete_processing_log(
        self,
        log_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Delete processing log entry."""
        pass


class ILayoutService(abc.ABC):
    """Layout service interface."""

    @abc.abstractmethod
    async def create_layout(
        self,
        name: str,
        definition: dict[str, Any],
        db: AsyncSession,
    ) -> LayoutRead:
        """Create new layout."""
        pass

    @abc.abstractmethod
    async def get_layout(
        self, layout_id: UUID, db: AsyncSession
    ) -> LayoutRead | None:
        """Get layout by ID."""
        pass

    @abc.abstractmethod
    async def get_all_layouts(
        self, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[LayoutRead]:
        """Get layouts, optionally bounded."""
        pass

    @abc.abstractmethod
    async def update_layout(
        self,
        layout_id: UUID,
        update_data: LayoutUpdate,
        db: AsyncSession,
    ) -> LayoutRead | None:
        """Update layout."""
        pass

    @abc.abstractmethod
    async def delete_layout(
        self, layout_id: UUID, db: AsyncSession
    ) -> bool:
        """Delete layout."""
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
        self, dashboard_ids: list[UUID], db: AsyncSession,
        limit: int | None = None, skip: int = 0,
    ) -> list[LayoutRead]:
        """Get layouts by dashboard IDs, optionally bounded.

        Args:
            dashboard_ids: List of dashboard IDs.
            db: Async database session.
            limit: Optional maximum number of rows.
            skip: Number of rows to skip (offset).

        Returns:
            List of layout models.
        """
        pass
