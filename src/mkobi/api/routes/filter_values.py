"""Dashboard filter values routes.

This module provides endpoints for retrieving filter values for dashboards.
Read operations use dashboard access control (require_dashboard_read_access).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    get_db_dependency,
    require_dashboard_read_access,
    get_filter_values_service,
)
from mkobi.api.schemas.responses import (
    error_401,
    error_403,
    error_404,
    error_422,
    error_429,
    error_500,
)
from mkobi.models.data import FilterValuesResponse
from mkobi.models.enums import ErrorCode
from mkobi.models.user import UserRead
from mkobi.services.filter_values_service import FilterValuesService
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

# No prefix - this router is mounted under /dashboards
router = APIRouter(tags=["dashboards"])


@router.get(
    "/{dashboard_id}/filter-values",
    status_code=status.HTTP_200_OK,
    summary="Get filter values for a dashboard",
    description="Returns distinct filter values for a specified filter/dimension name.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def get_filter_values_endpoint(
    dashboard_id: UUID,
    filter_name: str = Query(..., description="Filter/dimension name"),
    current_user: UserRead = Depends(require_dashboard_read_access),
    db: AsyncSession = Depends(get_db_dependency),
    filter_values_service: FilterValuesService = Depends(get_filter_values_service),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of records (max. 1000)",
    ),
) -> FilterValuesResponse:
    """Get filter values for a dashboard.

    Args:
        dashboard_id: Dashboard identifier.
        filter_name: Name of the filter to get values for.
        current_user: Current authenticated user with read access.
        db: Database session.
        filter_values_service: Injected filter values service.
        skip: Number of values to skip (offset).
        limit: Maximum number of values.

    Returns:
        FilterValuesResponse with filter_name, values list and total_values.

    Raises:
        AppException 500: On database error.
    """
    logger.info(
        "Getting filter values for dashboard: dashboard_id=%s, filter_name=%s",
        dashboard_id,
        filter_name,
    )
    try:
        values, total_values = await filter_values_service.get_filter_values(
            dashboard_id=dashboard_id, filter_name=filter_name, db=db,
            limit=limit, skip=skip,
        )
        return FilterValuesResponse(
            filter_name=filter_name, values=values, total_values=total_values
        )
    except Exception:
        logger.error(
            "Error getting filter values: dashboard_id=%s, filter_name=%s",
            dashboard_id,
            filter_name,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting filter values",
        ) from None