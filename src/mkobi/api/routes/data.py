"""Routes for getting dashboard aggregated data.

This module provides endpoints for:
- Getting aggregated data for dashboards
- Getting data for specific charts
- Applying filters to data

All operations require authentication and appropriate permissions.
"""

import json
import logging
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    CurrentUser,
    get_data_service,
    get_db_dependency,
    get_graph_repository,
)
from mkobi.api.schemas.responses import (
    auth_protected_responses,
)
from mkobi.core.permissions import check_dashboard_access, DashboardPermissionError
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.models.data import ProcessingResultData, AggregatedDataResponse, GraphDataResponse
from mkobi.models.enums import DashboardPermission, ErrorCode
from mkobi.services.data_service import DataService
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])


@router.get(
    "/aggregated",
    response_model=AggregatedDataResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard aggregated data",
    description="Returns data for all dashboard charts with applied filters.",
    responses=auth_protected_responses,
)
async def get_aggregated_data_endpoint(
    current_user: CurrentUser,
    data_service: DataService = Depends(get_data_service),
    db: AsyncSession = Depends(get_db_dependency),
    graph_repo: GraphRepository = Depends(get_graph_repository),
    dashboard_id: UUID = Query(..., description="Dashboard ID"),
    graph_id: UUID | None = Query(default=None, description="Graph ID (optional, returns all dashboard graphs if absent)"),
    filters: str | None = Query(default=None, description="JSON string with filters"),
) -> AggregatedDataResponse:
    """Get aggregated data for dashboard.

    Applies filters to JSONB field dims and groups data by graph_id.
    Response format: {"graphs": [{"graph_id": "...", "type": "...", "name": "...", "data": [...]}]}

    When graph_id is provided, returns data for a single graph.
    When graph_id is absent, returns data for all graphs in the dashboard.

    Args:
        dashboard_id: Dashboard ID.
        graph_id: Graph ID (optional). If absent, returns all dashboard graphs.
        filters: JSON string with filters (optional).
        current_user: Current authenticated user.
        data_service: Data service (dependency injection).
        graph_repo: Graph repository for fetching graphs (dependency injection).

    Returns:
        AggregatedDataResponse: Data for charts in React (Plotly.js) format.

    Raises:
        AppException 403: If user has no read access to dashboard.
        AppException 404: If dashboard or graph not found.
        AppException 500: On server error.
    """
    logger.info(
        "Aggregated data request: dashboard_id=%s, user_id=%s, filters=%s",
        dashboard_id,
        current_user.id,
        filters,
    )

    # Check that user has access to the dashboard
    if not await check_dashboard_access(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        required_permission=DashboardPermission.VIEW,
        db=db,
    ):
        logger.warning(
            "Access denied to dashboard: dashboard_id=%s, user_id=%s",
            dashboard_id,
            current_user.id,
        )
        raise AppException(
            code=ErrorCode.ACCESS_DENIED,
            detail="You do not have access to this dashboard",
        )

    try:
        # Parse filters from JSON string
        parsed_filters: dict[str, Any] | None = None
        if filters:
            try:
                parsed_filters = json.loads(filters)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON in filters")
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    detail="Invalid JSON in filters",
                ) from e

        # When graph_id is provided, return data for single graph
        if graph_id is not None:
            # Get graph to retrieve type and name using repository
            single_graph = await graph_repo.get(id=graph_id, db=db)

            if single_graph is None:
                logger.warning("Graph not found: graph_id=%s", graph_id)
                raise AppException(
                    code=ErrorCode.GRAPH_NOT_FOUND,
                    detail="Graph not found",
                )

            # Get data through service
            single_result: list[ProcessingResultData] = await data_service.get_aggregated_data(
                dashboard_id=dashboard_id,
                graph_id=graph_id,
                db=db,
                filters=parsed_filters,
            )

            logger.info(
                "Aggregated data retrieved: dashboard_id=%s, graph_id=%s, records_count=%d",
                dashboard_id,
                graph_id,
                len(single_result),
            )

            # Build response with graph metadata
            single_data_points: list[dict[str, int | float | str]] = []
            for item in single_result:
                if item.get("preview"):
                    single_data_points.extend(cast(list[dict[str, int | float | str]], item["preview"]))

            return AggregatedDataResponse(
                graphs=[
                    GraphDataResponse(
                        graph_id=str(graph_id),
                        type=single_graph.type,
                        name=single_graph.name,
                        data=single_data_points,
                        config=single_graph.config,
                    )
                ]
            )

        # When graph_id is absent, return data for all graphs in dashboard
        graphs = await graph_repo.get_by_dashboard_id(dashboard_id, db)
        graph_responses: list[GraphDataResponse] = []

        for graph_item in graphs:
            graph_data: list[ProcessingResultData] = await data_service.get_aggregated_data(
                dashboard_id=dashboard_id,
                graph_id=graph_item.id,
                db=db,
                filters=parsed_filters,
            )

            logger.info(
                "Aggregated data retrieved: dashboard_id=%s, graph_id=%s, records_count=%d",
                dashboard_id,
                graph_item.id,
                len(graph_data),
            )

            # Build response with graph metadata
            item_data_points: list[dict[str, int | float | str]] = []
            for item in graph_data:
                if item.get("preview"):
                    item_data_points.extend(cast(list[dict[str, int | float | str]], item["preview"]))

            graph_responses.append(
                GraphDataResponse(
                    graph_id=str(graph_item.id),
                    type=graph_item.type,
                    name=graph_item.name,
                    data=item_data_points,
                    config=graph_item.config,
                )
            )

        return AggregatedDataResponse(graphs=graph_responses)

    except ValueError as e:
        logger.warning("Error getting data: %s", e)
        raise AppException(
            code=ErrorCode.NOT_FOUND,
            detail=str(e),
        ) from e
    except DashboardPermissionError as e:
        logger.warning("Access denied: %s", e)
        raise AppException(
            code=ErrorCode.ACCESS_DENIED,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "Error getting aggregated data for dashboard id=%s: %s",
            dashboard_id,
            e,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting data",
        ) from e