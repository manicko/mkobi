"""Routes for processing log operations.

Provides endpoints for viewing data processing logs.
Complies with SPEC.md section 14.4 and task 011_processing_logs.md.
"""

from datetime import datetime
from uuid import UUID
from typing import cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    get_db_dependency,
    get_processing_log_repository,
    get_processing_log_service,
    require_admin_role,
)
from mkobi.api.schemas.responses import admin_responses
from mkobi.core.logging_config import get_logger
from mkobi.models.enums import ErrorCode, ProcessingStatus
from mkobi.models.processing_logs import ProcessingLogFilter, ProcessingLogRead
from mkobi.models.user import UserRead
from mkobi.services.processing_log_service import ProcessingLogService
from mkobi.utils.exceptions import AppException

router = APIRouter(prefix="/admin/logs", tags=["admin", "processing_logs"])

logger = get_logger(__name__)


@router.get(
    "/",
    response_model=list[ProcessingLogRead],
    summary="Get processing logs",
    description="Returns list of processing logs with filtering and pagination. Admin only.",
    responses=admin_responses,
)
async def get_logs_endpoint(
    dashboard_id: UUID | None = Query(
        None,
        description="Filter by dashboard ID",
    ),
    status_filter: ProcessingStatus | None = Query(
        None,
        description="Filter by status (STARTED, UPLOADED, PROCESSING, SUCCESS, FAILED)",
    ),
    date_from: datetime | None = Query(
        None,
        description="Filter by start date (started_at)",
    ),
    date_to: datetime | None = Query(
        None,
        description="Filter by end date (started_at)",
    ),
    skip: int = Query(
        0,
        ge=0,
        description="Number of records to skip for pagination",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of records (max. 1000)",
    ),
    _current_user: UserRead = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_dependency),
    log_service: ProcessingLogService = Depends(get_processing_log_service),
) -> list[ProcessingLogRead]:
    """Get list of processing logs with filtering.

    Admin-only operation.
    Supports filtering by dashboard_id, status, date range.
    Sorted by started_at DESC.
    """
    try:
        filters = ProcessingLogFilter(
            dashboard_id=dashboard_id,
            status=status_filter,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )
        logs: list[ProcessingLogRead] = await log_service.get_filtered(
            filters=filters, db=db
        )
        return logs
    except Exception as e:
        logger.error("Error getting log list: %s", e, exc_info=True)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting log list",
        ) from e


@router.get(
    "/{log_id}",
    response_model=ProcessingLogRead,
    summary="Get log by ID",
    description="Returns processing log details by ID. Admin only.",
    responses=admin_responses,
)
async def get_log_endpoint(
    log_id: UUID,
    _current_user: UserRead = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_dependency),
) -> ProcessingLogRead:
    """Get processing log by ID.

    Admin-only operation.
    """
    try:
        repo = get_processing_log_repository()
        log = await repo.get_by_id(log_id, db)
        if log is None:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                detail="Processing log not found",
            )
        return cast(ProcessingLogRead, ProcessingLogRead.model_validate(log))
    except AppException:
        raise
    except Exception as e:
        logger.error("Error getting log id=%s: %s", log_id, e, exc_info=True)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting log",
        ) from e