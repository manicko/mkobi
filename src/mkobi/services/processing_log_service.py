"""Processing log service.

Provides business logic for creating, updating and reading processing logs.

All methods are async and comply with task 011_processing_logs.md requirements.
"""

import logging
from datetime import datetime, UTC, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.interfaces.repository_interfaces import IProcessingLogRepository
from mkobi.interfaces.service_interfaces import IProcessingLogService
from mkobi.models.enums import ErrorCode, ProcessingStatus
from mkobi.models.processing_logs import ProcessingLogFilter, ProcessingLogRead
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)


def _validate_transition(current: ProcessingStatus, new: ProcessingStatus) -> None:
    """Validate that a status transition is allowed.

    Args:
        current: Current processing status.
        new: Target processing status.

    Raises:
        AppException: If the transition is invalid.
    """
    if current == new:
        return
    allowed = ProcessingStatus.valid_transitions().get(current, set())
    if new not in allowed:
        raise AppException(
            code=ErrorCode.INVALID_TRANSITION,
            detail=(
                f"Invalid status transition: {current.value} -> {new.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            ),
        )


class ProcessingLogService(IProcessingLogService):
    """Service for processing log business logic.

    Provides methods for managing processing log lifecycle.
    Called from data_worker at each processing stage.
    """

    def __init__(self, log_repo: IProcessingLogRepository) -> None:
        """Initialize service with injected repository.

        Args:
            log_repo: Processing log repository instance.
        """
        self.log_repo = log_repo
        logger.info("ProcessingLogService initialized with injected repository")

    async def create_processing_log(
        self,
        dashboard_id: UUID,
        status: str,
        db: AsyncSession,
        message: str | None = None,
    ) -> ProcessingLogRead:
        """Create processing log entry."""
        log = await self.log_repo.create_log(
            dashboard_id, ProcessingStatus(status), message, db
        )
        return cast(ProcessingLogRead, ProcessingLogRead.model_validate(log))

    async def get_processing_logs_by_dashboard(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> list[ProcessingLogRead]:
        """Get processing logs by dashboard ID."""
        return await self.log_repo.get_by_dashboard(dashboard_id, db)

    async def get_processing_logs_by_status(
        self, status: str, db: AsyncSession
    ) -> list[ProcessingLogRead]:
        """Get processing logs by status."""
        filters = ProcessingLogFilter(status=ProcessingStatus(status))
        return await self.log_repo.get_filtered(filters, db)

    async def update_processing_log(
        self,
        log_id: UUID,
        status: str | None,
        message: str | None,
        finished_at: str | None,
        db: AsyncSession,
    ) -> ProcessingLogRead | None:
        """Update processing log entry."""
        # Get current log to validate transition
        current_log = await self.log_repo.get_by_id(log_id, db)
        if current_log is None:
            return None

        new_status = ProcessingStatus(status) if status else ProcessingStatus.STARTED
        _validate_transition(current_log.status, new_status)

        parsed_finished_at = None
        if finished_at is not None:
            try:
                parsed_finished_at = datetime.fromisoformat(finished_at)
            except ValueError:
                logger.warning(
                    "Invalid finished_at format: %s, using None", finished_at
                )

        await self.log_repo.update_status(
            log_id,
            new_status,
            message,
            db,
            finished_at=parsed_finished_at,
        )

        log = await self.log_repo.get_by_id(log_id, db)
        return log  # Already returns ProcessingLogRead | None

    async def delete_processing_log(self, log_id: UUID, db: AsyncSession) -> bool:
        """Delete processing log entry."""

        # Get the log first to find its dashboard_id
        log = await self.log_repo.get_by_id(log_id, db)
        if log is None:
            return False

        # Ensure dashboard_id exists before attempting deletion
        if log.dashboard_id is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                detail="Processing log has no associated dashboard — cannot delete by dashboard_id",
            )

        # Delete all logs for the dashboard
        result: bool = await self.log_repo.delete(log.dashboard_id, db)
        return result

    async def create_started_log(
        self, dashboard_id: UUID | None, db: AsyncSession
    ) -> ProcessingLogRead:
        """Create log with STARTED status."""
        logger.info("Creating STARTED log: dashboard_id=%s", dashboard_id)
        log = await self.log_repo.create_log(
            dashboard_id, ProcessingStatus.STARTED, "Processing started", db
        )
        return cast(ProcessingLogRead, ProcessingLogRead.model_validate(log))

    async def update_to_uploaded(
        self, log_id: UUID, db: AsyncSession
    ) -> ProcessingLogRead | None:
        """Update log status to UPLOADED."""
        logger.info("Updating log to UPLOADED: log_id=%s", log_id)
        current_log = await self.log_repo.get_by_id(log_id, db)
        if current_log is not None:
            _validate_transition(current_log.status, ProcessingStatus.UPLOADED)
        await self.log_repo.update_status(
            log_id, ProcessingStatus.UPLOADED, "File uploaded successfully", db
        )
        log = await self.log_repo.get_by_id(log_id, db)
        return log

    async def update_to_processing(
        self, log_id: UUID, db: AsyncSession
    ) -> ProcessingLogRead | None:
        """Update log status to PROCESSING."""
        logger.info("Updating log to PROCESSING: log_id=%s", log_id)
        current_log = await self.log_repo.get_by_id(log_id, db)
        if current_log is not None:
            _validate_transition(current_log.status, ProcessingStatus.PROCESSING)
        await self.log_repo.update_status(
            log_id, ProcessingStatus.PROCESSING, "Processing data", db
        )
        log = await self.log_repo.get_by_id(log_id, db)
        return log

    async def update_to_completed(
        self, log_id: UUID, message: str | None, db: AsyncSession
    ) -> ProcessingLogRead | None:
        """Update log status to COMPLETED."""
        logger.info("Updating log to COMPLETED: log_id=%s", log_id)
        current_log = await self.log_repo.get_by_id(log_id, db)
        if current_log is not None:
            _validate_transition(current_log.status, ProcessingStatus.COMPLETED)
        await self.log_repo.update_status(
            log_id,
            ProcessingStatus.COMPLETED,
            message or "Processing completed successfully",
            db,
        )
        log = await self.log_repo.get_by_id(log_id, db)
        return log

    async def update_to_success(
        self, log_id: UUID, message: str | None, db: AsyncSession
    ) -> ProcessingLogRead | None:
        """Update log status to SUCCESS (deprecated: use update_to_completed)."""
        logger.info("Updating log to SUCCESS (deprecated): log_id=%s", log_id)
        return await self.update_to_completed(log_id, message, db)

    async def update_to_failed(
        self, log_id: UUID, error: str, db: AsyncSession
    ) -> ProcessingLogRead | None:
        """Update log status to FAILED."""
        logger.error("Updating log to FAILED: log_id=%s, error=%s", log_id, error)
        current_log = await self.log_repo.get_by_id(log_id, db)
        if current_log is not None:
            _validate_transition(current_log.status, ProcessingStatus.FAILED)
        await self.log_repo.update_status(log_id, ProcessingStatus.FAILED, error, db)
        log = await self.log_repo.get_by_id(log_id, db)
        return log

    async def get_filtered(
        self, filters: ProcessingLogFilter, db: AsyncSession
    ) -> list[ProcessingLogRead]:
        """Get filtered processing logs."""
        logger.info("Getting filtered logs: filters=%s", filters)
        return await self.log_repo.get_filtered(filters, db)

    async def delete_old_logs(
        self, retention_days: int | None = None, db: AsyncSession | None = None
    ) -> int:
        """Delete processing logs in terminal states older than retention period.

        Args:
            retention_days: Number of days to keep logs. If None, uses the configured
                logs_retention_days setting (default 30 days).
            db: Optional database session. If None, creates a new session.

        Returns:
            int: Number of deleted log entries.
        """
        from mkobi.config import get_config
        from mkobi.db.session import get_session

        config = get_config()
        days = (
            retention_days if retention_days is not None else config.logs_retention_days
        )
        cutoff = datetime.now(UTC) - timedelta(days=days)

        if db is not None:
            # Use provided session (test mode)
            count = await self.log_repo.delete_old_logs(cutoff, db)
            return count

        # Production mode - create new session
        async with get_session() as session:
            async with session.begin():
                count = await self.log_repo.delete_old_logs(cutoff, session)
                return count
