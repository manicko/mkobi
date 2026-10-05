"""Data processing service.

Provides business logic for uploading, processing and tracking
data processing status for dashboards.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.config import get_config
from mkobi.core.logging_config import get_logger
from mkobi.core.permissions import check_dashboard_access, DashboardPermissionError
from mkobi.interfaces.repository_interfaces import (
    IAggregatedDataRepository,
    IDashboardRepository,
    IGraphRepository,
    IProcessingLogRepository,
)
from mkobi.interfaces.service_interfaces import IDataService, IProcessingConfigService
from mkobi.models.data import ProcessingResultData, ProcessingResult, ProcessingStatusResponse, UploadResponse
from mkobi.models.enums import DashboardPermission, ErrorCode, ProcessingStatus, UploadMode
from mkobi.services.file_processing import process_upload_with_session
from mkobi.utils.exceptions import AppException

logger = get_logger(__name__)


class _ServedRow(Protocol):
    """The two columns ``_served_row_keys`` reads off a stored aggregate row.

    The repository interface (``IAggregatedDataRepository``) declares its read
    methods as returning ``list[Any]`` -- it does not commit to the ORM entity
    -- so ``_served_row_keys`` cannot name ``AggregatedData`` without a blind
    cast. This structural protocol instead names exactly the two attributes the
    function touches: the writer's entity satisfies it, and a misspelt access
    such as ``record.mtric`` becomes a type error rather than a silent ``Any``.
    """

    metrics: dict[str, Any]
    dims: dict[str, Any]


def _served_row_keys(records: list[_ServedRow]) -> tuple[list[str], list[str]]:
    """Return the ``(metric_keys, dimension_keys)`` served on the rows.

    The keys are read directly off each record's ``metrics`` / ``dims`` columns
    -- the same columns the rows were merged from -- so every returned name is a
    key on a served row by construction. The union is taken in first-seen order
    over the whole page, never from ``records[0]`` alone: the route merges
    previews across the page, so a record whose keys were not first would
    otherwise drop them.
    """
    metric_keys: dict[str, None] = {}
    dimension_keys: dict[str, None] = {}
    for record in records:
        for key in record.metrics or {}:
            metric_keys.setdefault(key, None)
        for key in record.dims or {}:
            dimension_keys.setdefault(key, None)
    return list(metric_keys), list(dimension_keys)


class DataService(IDataService):
    """Data service class for processing data."""

    def __init__(
        self,
        agg_repo: IAggregatedDataRepository,
        log_repo: IProcessingLogRepository,
        graph_repo: IGraphRepository,
        config_service: IProcessingConfigService | None = None,
        dashboard_repo: IDashboardRepository | None = None,
    ) -> None:
        """Initialize service with injected repositories.

        Args:
            agg_repo: Aggregated data repository.
            log_repo: Processing log repository.
            graph_repo: Graph repository.
            config_service: Optional processing config service for fetching configs.
            dashboard_repo: Optional dashboard repository for existence checks.
        """
        self.agg_repo = agg_repo
        self.log_repo = log_repo
        self.graph_repo = graph_repo
        self.config_service = config_service
        self.dashboard_repo = dashboard_repo
        self._max_file_size = get_config().max_file_size

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
        """Process uploaded file and save aggregates.

        Args:
            file_path: Path to the uploaded file (already streamed to disk).
            dashboard_id: Target dashboard ID.
            db: Async database session.
            user_id: Optional user ID for permission check.
            filename: Original filename.
            content_type: MIME type of uploaded file.
            mode: Upload mode (OVERWRITE clears old data, APPEND keeps it).

        Returns:
            UploadResponse with task information.
        """
        file_path_obj = Path(file_path) if isinstance(file_path, str) else file_path
        return await self._execute_upload(
            file_path_obj, dashboard_id, user_id,
            filename, content_type, mode, db,
        )

    async def _execute_upload(
        self,
        file_path: Path,
        dashboard_id: UUID,
        user_id: UUID | None,
        filename: str | None,
        content_type: str | None,
        mode: UploadMode,
        db: AsyncSession,
    ) -> UploadResponse:
        """Execute upload with permission check and file processing."""
        # Check dashboard existence before access verification
        if self.dashboard_repo is not None:
            dashboard = await self.dashboard_repo.get(dashboard_id, db)
            if dashboard is None:
                logger.warning(
                    "Dashboard not found for upload: dashboard_id=%s",
                    dashboard_id,
                )
                raise AppException(
                    code=ErrorCode.DASHBOARD_NOT_FOUND,
                    detail="Dashboard not found",
                )

        if user_id:
            has_access = await check_dashboard_access(
                user_id=user_id,
                dashboard_id=dashboard_id,
                required_permission=DashboardPermission.EDIT,
                db=db,
            )
            if not has_access:
                logger.warning(
                    "Processing denied: user_id=%s, dashboard_id=%s",
                    user_id, dashboard_id,
                )
                raise DashboardPermissionError(
                    "No permission to process data for this dashboard"
                )

        # Fetch processing config if config_service is available
        processing_config: dict[str, Any] | None = None
        if self.config_service is not None:
            config_response = await self.config_service.get_processing_config_by_dashboard(
                dashboard_id, db
            )
            processing_config = dict(config_response.settings) if config_response else None
            if processing_config:
                logger.info(
                    "Processing config fetched for dashboard: dashboard_id=%s",
                    dashboard_id,
                )

        log_id = await process_upload_with_session(
            file_path=file_path,
            dashboard_id=dashboard_id,
            log_repo=self.log_repo,
            filename=filename,
            content_type=content_type,
            mode=mode,
            max_file_size=self._max_file_size,
            db=db,
            processing_config=processing_config,
        )

        return UploadResponse(
            task_id=log_id,
            filename=filename or "unknown",
            dashboard_id=dashboard_id,
            status=ProcessingStatus.UPLOADED,
            message="File uploaded successfully, processing queued",
            uploaded_at=datetime.now(),
        )

    async def get_aggregated_data(
        self,
        dashboard_id: UUID,
        graph_id: UUID,
        db: AsyncSession,
        filters: dict[str, Any] | None = None,
    ) -> list[ProcessingResultData]:
        """Get aggregated data for graph.

        Args:
            dashboard_id: Dashboard identifier.
            graph_id: Graph identifier.
            db: Async database session.
            filters: Optional filters for JSONB field dims.

        Returns:
            List of aggregated data for graph.
        """
        return await self._get_aggregated_data_with_session(
            dashboard_id, graph_id, db, filters,
        )

    async def _get_aggregated_data_with_session(
        self,
        dashboard_id: UUID,
        graph_id: UUID,
        db: AsyncSession,
        filters: dict[str, Any] | None = None,
    ) -> list[ProcessingResultData]:
        """Get aggregated data for a graph within a dashboard.

        Args:
            dashboard_id: Dashboard identifier.
            graph_id: Graph identifier.
            db: Async database session.
            filters: Optional filters for JSONB field dims (key-value pairs).

        Returns:
            List of aggregated data records.
        """
        records = await self.agg_repo.get_by_graph_id(
            graph_id, db, dashboard_id=dashboard_id, filters=filters,
        )
        # Build only what the endpoint keeps. The route reads ``preview`` and
        # discards ``columns`` and ``rows``, so the two list allocations that
        # built ``columns`` are dropped here rather than materialised per row
        # only to be thrown away.
        return [
            ProcessingResultData(
                dashboard_id=record.dashboard_id,
                preview=[{**record.dims, **record.metrics}],
            )
            for record in records
        ]

    async def get_bounded_aggregated_data(
        self,
        dashboard_id: UUID,
        graph_id: UUID,
        db: AsyncSession,
        max_rows: int,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[ProcessingResultData], int, list[str], list[str]]:
        """Get at most ``max_rows`` aggregate rows plus the true total.

        The rows are bounded by ``max_rows`` (order preserved), while the total
        is a separate ``COUNT(*)`` that reflects every stored row -- never the
        length of the bounded page. Both queries share one predicate set, so the
        count cannot disagree with the rows.

        Args:
            dashboard_id: Dashboard identifier.
            graph_id: Graph identifier.
            db: Async database session.
            max_rows: Hard ceiling on returned rows.
            filters: Optional filters for JSONB field dims.

        Returns:
            tuple[list[ProcessingResultData], int, list[str], list[str]]: the
            bounded records, the true untruncated row count, the served metric
            keys, and the served dimension keys -- in that order.
        """
        records = await self.agg_repo.get_by_graph_id_limited(
            graph_id, db, max_rows, dashboard_id=dashboard_id, filters=filters,
        )
        total_rows = await self.agg_repo.count_by_graph_id(
            graph_id, db, dashboard_id=dashboard_id, filters=filters,
        )
        results = [
            ProcessingResultData(
                dashboard_id=record.dashboard_id,
                preview=[{**record.dims, **record.metrics}],
            )
            for record in records
        ]
        metric_keys, dimension_keys = _served_row_keys(records)
        return results, total_rows, metric_keys, dimension_keys

    async def count_dashboard_aggregated_data(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> int:
        """Return the dashboard-wide true, untruncated aggregate row count."""
        return await self.agg_repo.count_by_dashboard_id(dashboard_id, db)

    async def get_available_metrics(
        self, dashboard_id: UUID, db: AsyncSession,
    ) -> list[str]:
        """Get available metrics for dashboard."""
        return await self._get_available_metrics_with_session(dashboard_id, db)

    async def _get_available_metrics_with_session(
        self, dashboard_id: UUID, db: AsyncSession,
    ) -> list[str]:
        """Collect metric names from all graphs in a dashboard."""
        graphs = await self.graph_repo.get_by_dashboard_id(dashboard_id, db)
        metrics: set[str] = set()
        for graph in graphs:
            if graph.metrics:
                metrics.update(graph.metrics)
        return list(metrics)

    async def get_available_dimensions(
        self, dashboard_id: UUID, db: AsyncSession,
    ) -> list[str]:
        """Get available dimensions for dashboard."""
        return await self._get_available_dimensions_with_session(dashboard_id, db)

    async def _get_available_dimensions_with_session(
        self, dashboard_id: UUID, db: AsyncSession,
    ) -> list[str]:
        """Collect dimension names from all graphs in a dashboard."""
        graphs = await self.graph_repo.get_by_dashboard_id(dashboard_id, db)
        dimensions: set[str] = set()
        for graph in graphs:
            if graph.dimensions:
                dimensions.update(graph.dimensions)
        return list(dimensions)

    async def get_processing_status(
        self,
        task_id: UUID,
        user_id: UUID,
        db: AsyncSession,
    ) -> ProcessingStatusResponse:
        """Get processing status."""
        log = await self.log_repo.get_by_id(task_id, db)
        if log is None:
            raise ValueError(f"Processing task {task_id} not found")
        if log.dashboard_id is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                detail="Processing log has no associated dashboard",
            )
        if user_id:
            has_access = await check_dashboard_access(
                user_id=user_id, dashboard_id=log.dashboard_id,
                required_permission=DashboardPermission.VIEW, db=db,
            )
            if not has_access:
                raise DashboardPermissionError("No permission to view this dashboard")
        return ProcessingStatusResponse(
            task_id=task_id,
            # Display-only: under D-06-A = (b) no durable filename exists, so this
            # best-effort text is derived from the log message and must never be
            # used to open or locate an artefact (see ProcessingStatusResponse).
            filename=log.message or "unknown",
            dashboard_id=log.dashboard_id,
            status=log.status,
            progress=50 if log.status == ProcessingStatus.PROCESSING else 100 if log.status == ProcessingStatus.COMPLETED else 0,
            message=log.message,
            started_at=log.started_at,
            finished_at=log.finished_at,
            error_code=log.error_code,
        )

    async def get_processing_result(
        self,
        task_id: UUID,
        user_id: UUID,
        db: AsyncSession,
    ) -> ProcessingResult:
        """Get processing result."""
        log = await self.log_repo.get_by_id(task_id, db)
        if log is None:
            raise ValueError(f"Processing task {task_id} not found")
        if log.dashboard_id is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                detail="Processing log has no associated dashboard",
            )
        if user_id:
            has_access = await check_dashboard_access(
                user_id=user_id, dashboard_id=log.dashboard_id,
                required_permission=DashboardPermission.VIEW, db=db,
            )
            if not has_access:
                raise DashboardPermissionError("No permission to view this dashboard")
        if log.status != ProcessingStatus.COMPLETED:
            return ProcessingResult(
                success=False, task_id=task_id,
                dashboard_id=log.dashboard_id, rows_processed=0,
                message=f"Processing not complete. Status: {log.status}",
            )
        graphs = await self.graph_repo.get_by_dashboard_id(log.dashboard_id, db)
        rows_processed = 0
        if graphs:
            agg_data = await self.agg_repo.get_by_graph_id(graphs[0].id, db)
            rows_processed = len(agg_data) if agg_data else 0
        return ProcessingResult(
            success=True, task_id=task_id,
            dashboard_id=log.dashboard_id, rows_processed=rows_processed,
            message="Processing completed successfully",
        )
