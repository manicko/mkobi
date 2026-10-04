"""Dashboard filter binding routes.

This module provides endpoints for binding and unbinding filters to dashboards.
All operations require admin role.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    CurrentUser,
    get_db_dependency,
    get_dashboard_filter_repository,
    get_filter_repository,
    require_dashboard_read_access,
)
from mkobi.api.schemas.responses import admin_responses
from mkobi.db.repositories.dashboard_filter_repo import DashboardFilterRepository
from mkobi.db.repositories.filter_repo import FilterRepository
from mkobi.models.enums import ErrorCode
from mkobi.models.user import UserRead
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

# No prefix - this router is mounted under /dashboards
router = APIRouter(tags=["dashboards"])


@router.post(
    "/{dashboard_id}/filters",
    status_code=status.HTTP_200_OK,
    summary="Bind filter to dashboard",
    description="Binds a filter to a dashboard. Requires admin role.",
    responses=admin_responses,
)
async def bind_filter_endpoint(
    dashboard_id: UUID,
    filter_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    filter_repo: FilterRepository = Depends(get_filter_repository),
    dashboard_filter_repo: DashboardFilterRepository = Depends(get_dashboard_filter_repository),
) -> dict[str, Any]:
    """Bind a filter to a dashboard."""
    logger.info(
        "Binding filter to dashboard: dashboard_id=%s, filter_id=%s",
        dashboard_id,
        filter_id,
    )
    try:
        filter_obj = await filter_repo.get(filter_id, db)
        if not filter_obj:
            raise AppException(
                code=ErrorCode.FILTER_NOT_FOUND,
                detail="Filter not found",
            )

        result = await dashboard_filter_repo.bind_filter(
            dashboard_id=dashboard_id, filter_id=filter_id, db=db
        )
        await db.commit()
        return {"message": "Filter bound to dashboard", "bound": result}
    except AppException:
        raise
    except Exception as e:
        logger.error(
            "Error binding filter to dashboard dashboard_id=%s, filter_id=%s: %s",
            dashboard_id,
            filter_id,
            e,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error binding filter",
        ) from None


@router.delete(
    "/{dashboard_id}/filters/{filter_id}",
    status_code=status.HTTP_200_OK,
    summary="Unbind filter from dashboard",
    description="Unbinds a filter from a dashboard. Requires admin role.",
    responses=admin_responses,
)
async def unbind_filter_endpoint(
    dashboard_id: UUID,
    filter_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    dashboard_filter_repo: DashboardFilterRepository = Depends(get_dashboard_filter_repository),
) -> dict[str, Any]:
    """Unbind a filter from a dashboard."""
    logger.info(
        "Unbinding filter from dashboard: dashboard_id=%s, filter_id=%s",
        dashboard_id,
        filter_id,
    )
    try:
        result = await dashboard_filter_repo.unbind_filter(
            dashboard_id=dashboard_id, filter_id=filter_id, db=db
        )
        await db.commit()
        if result:
            return {"message": "Filter unbound from dashboard"}
        else:
            raise AppException(
                code=ErrorCode.FILTER_NOT_FOUND,
                detail="Filter not bound to this dashboard",
            )
    except AppException:
        raise
    except Exception as e:
        logger.error(
            "Error unbinding filter from dashboard dashboard_id=%s, filter_id=%s: %s",
            dashboard_id,
            filter_id,
            e,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error unbinding filter",
        ) from None


@router.get(
    "/{dashboard_id}/filters",
    response_model=list[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List dashboard filters",
    description="Returns all filters bound to a dashboard.",
    responses=admin_responses,
)
async def get_dashboard_filters_endpoint(
    dashboard_id: UUID,
    current_user: UserRead = Depends(require_dashboard_read_access),
    db: AsyncSession = Depends(get_db_dependency),
    dashboard_filter_repo: DashboardFilterRepository = Depends(get_dashboard_filter_repository),
) -> list[dict[str, Any]]:
    """Get all filters bound to a dashboard."""
    logger.info("Getting filters for dashboard: dashboard_id=%s", dashboard_id)
    try:
        filter_ids = await dashboard_filter_repo.get_dashboard_filters(
            dashboard_id=dashboard_id, db=db
        )
        return [{"filter_id": str(fid)} for fid in filter_ids]
    except Exception as e:
        logger.error(
            "Error getting filters for dashboard dashboard_id=%s: %s",
            dashboard_id,
            e,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting dashboard filters",
        ) from e