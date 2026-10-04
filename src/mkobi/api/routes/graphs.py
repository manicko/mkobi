"""Routes for managing dashboard graphs.

This module provides endpoints for CRUD operations on graphs.
Access to most operations is restricted and requires authentication.
Create, update, and delete operations are admin-only.
"""

from typing import Any, cast

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    get_db_dependency as get_db,
    get_graph_repository,
    get_accessible_dashboard_ids,
    CurrentUser,
    check_dashboard_access,
)
from mkobi.api.schemas.responses import (
    auth_protected_responses,
    error_401,
    error_403,
    error_404,
    error_409,
    error_422,
    error_429,
    error_500,
)
from mkobi.models.graph import (
    GraphCreate,
    GraphRead,
    GraphUpdate,
)
from mkobi.models.enums import DashboardPermission, ErrorCode
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graphs", tags=["graphs"])


# --- Global graph endpoints ---


@router.post(
    "/",
    response_model=GraphRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new graph",
    description="Creates a new graph. Requires admin role and dashboard access.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        409: error_409,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def create_graph_endpoint(
    graph: GraphCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> GraphRead:
    """Create a new graph with dashboard access control.

    IDOR protection: verifies user has admin access to the dashboard
    specified in the request body.

    Args:
        graph: Model with data for creating the graph.
        current_user: Current authenticated user.
        db: Database session.

    Returns:
        GraphRead: Model of the created graph.

    Raises:
        AppException 403: If user has no admin access to the dashboard.
        AppException 422: If data validation failed.
        AppException 500: On database error.
    """
    logger.info(
        "Creating graph: name=%s, dashboard_id=%s, user_id=%s",
        graph.name,
        graph.dashboard_id,
        current_user.id,
    )

    try:
        # IDOR protection: verify user has admin access to the dashboard
        if not await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=graph.dashboard_id,
            db=db,
            required_permission=DashboardPermission.ADMIN,
        ):
            logger.warning(
                "Admin access denied to create graph: user_id=%s, dashboard_id=%s",
                current_user.id,
                graph.dashboard_id,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="You do not have admin access to this dashboard",
            )

        graph_repo = get_graph_repository()
        result = await graph_repo.create(
            db=db,
            name=graph.name,
            type=graph.type,
            dashboard_id=graph.dashboard_id,
            config=graph.config,
            dimensions=graph.dimensions,
            metrics=graph.metrics,
        )
        await db.commit()
        return cast(GraphRead, GraphRead.model_validate(result))
    except AppException:
        raise
    except ValueError as e:
        await db.rollback()
        logger.warning("Validation error creating graph: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except IntegrityError:
        # A flush-time integrity error leaves the transaction aborted, so the
        # next statement on this session would raise PendingRollbackError.
        await db.rollback()
        logger.error(
            "Integrity error creating graph name=%s dashboard_id=%s",
            graph.name,
            graph.dashboard_id,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.DUPLICATE_RESOURCE,
            detail="Conflict: graph creation failed",
        ) from None
    except Exception as e:
        await db.rollback()
        logger.error("Error creating graph name=%s: %s", graph.name, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error creating graph",
        ) from e


@router.get(
    "/",
    response_model=list[GraphRead],
    status_code=status.HTTP_200_OK,
    summary="List all graphs",
    description="Returns a list of graphs available to the user.",
    responses=auth_protected_responses,
)
async def get_graphs_endpoint(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    accessible_dashboards: list[UUID] | None = Depends(
        get_accessible_dashboard_ids
    ),
) -> list[GraphRead]:
    """Get graphs accessible to current user.

    Non-admin users only see graphs from dashboards they have access to.
    Admins see all graphs.

    Args:
        current_user: Current authenticated user.
        db: Database session.
        accessible_dashboards: Dashboard filter, or ``None`` for an admin.

    Returns:
        list[GraphRead]: List of graph models.

    Raises:
        AppException 500: On database error.
    """
    logger.info("Getting graphs for user_id=%s", current_user.id)

    try:
        graph_repo = get_graph_repository()
        # None means the caller holds the admin role and is unrestricted;
        # an empty list means no grant and yields no graphs.
        graphs = (
            await graph_repo.get_all(db=db)
            if accessible_dashboards is None
            else await graph_repo.get_by_dashboard_ids(accessible_dashboards, db)
        )
        return [GraphRead.model_validate(g) for g in graphs]
    except Exception as e:
        logger.error("Error getting graphs: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting graphs",
        ) from e


@router.get(
    "/{graph_id}",
    response_model=GraphRead,
    status_code=status.HTTP_200_OK,
    summary="Get graph by ID",
    description="Returns graph data by its ID.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def get_graph_endpoint(
    graph_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> GraphRead:
    """Get graph by ID with access control.

    IDOR protection: verifies user has read access to the graph's dashboard.

    Args:
        graph_id: Graph ID.
        current_user: Current authenticated user.
        db: Database session.

    Returns:
        GraphRead: Graph model.

    Raises:
        AppException 404: If graph not found.
        AppException 403: If user has no read access to the dashboard.
        AppException 500: On database error.
    """
    logger.info("Requesting graph: graph_id=%s, user_id=%s", graph_id, current_user.id)

    try:
        graph_repo = get_graph_repository()
        graph = await graph_repo.get(id=graph_id, db=db)
        if graph is None:
            logger.warning("Graph not found: id=%s", graph_id)
            raise AppException(
                code=ErrorCode.GRAPH_NOT_FOUND,
                detail="Graph not found",
            )

        # IDOR protection: verify user has read access to the graph's dashboard
        if not await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=graph.dashboard_id,
            db=db,
            required_permission=DashboardPermission.VIEW,
        ):
            logger.warning(
                "Access denied to graph: user_id=%s, graph_id=%s, dashboard_id=%s",
                current_user.id,
                graph_id,
                graph.dashboard_id,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="You do not have read access to this graph",
            )

        return cast(GraphRead, GraphRead.model_validate(graph))
    except AppException:
        raise
    except Exception as e:
        logger.error("Error getting graph id=%s: %s", graph_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting graph",
        ) from e


@router.put(
    "/{graph_id}",
    response_model=GraphRead,
    status_code=status.HTTP_200_OK,
    summary="Update graph",
    description="Updates graph data. Requires admin role and dashboard access.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        409: error_409,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def update_graph_endpoint(
    graph_id: UUID,
    graph_update: GraphUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> GraphRead:
    """Update graph with dashboard access control.

    IDOR protection: verifies user is admin (already enforced by dependency)
    and has access to the graph's dashboard.

    Args:
        graph_id: Graph ID to update.
        graph_update: Model with new data.
        current_user: Current authenticated user.
        db: Database session.

    Returns:
        GraphRead: Updated graph model.

    Raises:
        AppException 404: If graph not found.
        AppException 403: If user has no admin access to the dashboard.
        AppException 422: If data validation failed.
        AppException 500: On database error.
    """
    logger.info(
        "Updating graph: graph_id=%s, user_id=%s",
        graph_id,
        current_user.id,
    )

    try:
        graph_repo = get_graph_repository()
        # Fetch graph first to get dashboard_id
        existing_graph = await graph_repo.get(id=graph_id, db=db)
        if existing_graph is None:
            logger.warning("Graph not found for update: id=%s", graph_id)
            raise AppException(
                code=ErrorCode.GRAPH_NOT_FOUND,
                detail="Graph not found",
            )

        # IDOR protection: verify user has admin access to the graph's dashboard
        if not await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=existing_graph.dashboard_id,
            db=db,
            required_permission=DashboardPermission.ADMIN,
        ):
            logger.warning(
                "Admin access denied to graph: user_id=%s, graph_id=%s, dashboard_id=%s",
                current_user.id,
                graph_id,
                existing_graph.dashboard_id,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="You do not have admin access to this graph",
            )

        # Prepare update data
        update_data: dict[str, Any] = {}
        if graph_update.name is not None:
            update_data["name"] = graph_update.name
        if graph_update.type is not None:
            update_data["type"] = graph_update.type
        if graph_update.config is not None:
            update_data["config"] = graph_update.config
        if graph_update.dimensions is not None:
            update_data["dimensions"] = graph_update.dimensions
        if graph_update.metrics is not None:
            update_data["metrics"] = graph_update.metrics

        result = await graph_repo.update(
            graph_id, db, **update_data
        )
        if result is None:
            logger.warning("Graph not found for update: id=%s", graph_id)
            raise AppException(
                code=ErrorCode.GRAPH_NOT_FOUND,
                detail="Graph not found",
            )
        await db.commit()
        return cast(GraphRead, GraphRead.model_validate(result))
    except ValueError as e:
        logger.warning("Validation error updating graph: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except AppException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Error updating graph id=%s: %s", graph_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error updating graph",
        ) from e


@router.delete(
    "/{graph_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete graph",
    description="Deletes a graph. Requires admin role and dashboard access.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def delete_graph_endpoint(
    graph_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete graph with dashboard access control.

    IDOR protection: verifies user is admin (already enforced by dependency)
    and has access to the graph's dashboard.

    Args:
        graph_id: Graph ID to delete.
        current_user: Current authenticated user.
        db: Database session.

    Raises:
        AppException 404: If graph not found.
        AppException 403: If user has no admin access to the dashboard.
        AppException 500: On database error.
    """
    logger.info(
        "Deleting graph: graph_id=%s, user_id=%s",
        graph_id,
        current_user.id,
    )

    try:
        graph_repo = get_graph_repository()
        # Fetch graph first to get dashboard_id
        existing_graph = await graph_repo.get(id=graph_id, db=db)
        if existing_graph is None:
            logger.warning("Graph not found for deletion: id=%s", graph_id)
            raise AppException(
                code=ErrorCode.GRAPH_NOT_FOUND,
                detail="Graph not found",
            )

        # IDOR protection: verify user has admin access to the graph's dashboard
        if not await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=existing_graph.dashboard_id,
            db=db,
            required_permission=DashboardPermission.ADMIN,
        ):
            logger.warning(
                "Admin access denied to graph: user_id=%s, graph_id=%s, dashboard_id=%s",
                current_user.id,
                graph_id,
                existing_graph.dashboard_id,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="You do not have admin access to this graph",
            )

        result = await graph_repo.delete(graph_id, db)
        if not result:
            logger.warning("Graph not found for deletion: id=%s", graph_id)
            raise AppException(
                code=ErrorCode.GRAPH_NOT_FOUND,
                detail="Graph not found",
            )
        await db.commit()
    except AppException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Error deleting graph id=%s: %s", graph_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error deleting graph",
        ) from e