"""Dashboard graph routes.

This module provides endpoints for managing graphs within a dashboard.
Create operations require an `admin` permission on the target dashboard, or the
`admin` role, which bypasses the per-dashboard check. Read operations use
dashboard read access control.
"""

import logging
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    get_db_dependency,
    get_graph_repository,
    require_dashboard_admin_access,
    require_dashboard_read_access,
)
from mkobi.api.schemas.responses import (
    error_401,
    error_403,
    error_404,
    error_409,
    error_422,
    error_429,
    error_500,
)
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.models.enums import ErrorCode
from mkobi.models.graph import GraphCreate, GraphRead
from mkobi.models.user import UserRead
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

# No prefix - this router is mounted under /dashboards
router = APIRouter(tags=["dashboards"])


@router.post(
    "/{dashboard_id}/graphs",
    response_model=GraphRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new graph for a dashboard",
    description=(
        "Creates a new graph for a specific dashboard. Requires an `admin` "
        "permission on the dashboard, or the `admin` role, which bypasses the "
        "per-dashboard check."
    ),
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        409: error_409,
        422: error_422,
        500: error_500,
    },
)
async def create_dashboard_graph_endpoint(
    dashboard_id: UUID,
    graph: GraphCreate,
    current_user: UserRead = Depends(require_dashboard_admin_access),
    db: AsyncSession = Depends(get_db_dependency),
    graph_repo: GraphRepository = Depends(get_graph_repository),
) -> GraphRead:
    """Create a new graph for a dashboard.

    Args:
        dashboard_id: Dashboard ID.
        graph: Model with graph data.
        current_user: Current authenticated user who passed the dashboard
            admin-access gate.
        db: Database session.

    Returns:
        GraphRead: Model of the created graph.

    Raises:
        AppException 403: If the caller holds no admin grant on the dashboard
            and is not an administrator.
        AppException 404: If dashboard not found.
        AppException 422: If data validation failed.
        AppException 500: On database error.
    """
    logger.info(
        "Creating graph for dashboard: name=%s, dashboard_id=%s, user_id=%s",
        graph.name,
        dashboard_id,
        current_user.id,
    )

    try:
        result = await graph_repo.create(
            db=db,
            name=graph.name,
            type=graph.type,
            dashboard_id=dashboard_id,
            config=graph.config,
            dimensions=graph.dimensions,
            metrics=graph.metrics,
        )
        await db.commit()
        return cast(GraphRead, GraphRead.model_validate(result))
    except ValueError as e:
        logger.warning("Validation error creating graph: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail="Invalid graph data",
        ) from e
    except AppException:
        raise
    except IntegrityError:
        await db.rollback()
        logger.error(
            "Integrity error creating graph name=%s dashboard_id=%s",
            graph.name,
            dashboard_id,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.DUPLICATE_RESOURCE,
            detail="Conflict: graph creation failed",
        ) from None
    except Exception:
        await db.rollback()
        logger.error(
            "Error creating graph name=%s dashboard_id=%s",
            graph.name,
            dashboard_id,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Internal server error",
        ) from None


@router.get(
    "/{dashboard_id}/graphs",
    response_model=list[GraphRead],
    status_code=status.HTTP_200_OK,
    summary="List graphs for a dashboard",
    description="Returns a list of all graphs for a specific dashboard.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def get_dashboard_graphs_endpoint(
    dashboard_id: UUID,
    current_user: UserRead = Depends(require_dashboard_read_access),
    db: AsyncSession = Depends(get_db_dependency),
    graph_repo: GraphRepository = Depends(get_graph_repository),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of records (max. 1000)",
    ),
) -> list[GraphRead]:
    """Get all graphs for a dashboard.

    Args:
        dashboard_id: Dashboard ID.
        current_user: Current authenticated user.
        db: Database session.
        skip: Number of records to skip (offset).
        limit: Maximum number of records.

    Returns:
        list[GraphRead]: List of graph models.

    Raises:
        AppException 403: If user has no access to dashboard.
        AppException 500: On database error.
    """
    logger.info("Getting graphs for dashboard: dashboard_id=%s", dashboard_id)

    try:
        graphs = await graph_repo.get_by_dashboard_id(
            dashboard_id=dashboard_id, db=db, limit=limit, skip=skip
        )
        return [GraphRead.model_validate(g) for g in graphs]
    except Exception as e:
        logger.error("Error getting graphs for dashboard %s: %s", dashboard_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting graphs",
        ) from e